#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# systemd system-sleep hook for the Turing Smart Screen monitor.
#
# Turns the screen OFF cleanly before the machine suspends and brings the
# monitor back UP at resume. Without this, on Linux the running process keeps a
# now-dead serial handle open across suspend: at resume the rev C data port has
# re-enumerated (it disappears for several seconds) and the next blocking serial
# write hangs forever, leaving the display frozen until a manual restart. Worse,
# a write that hits the screen at the wrong moment can wedge its internal SoC
# into a hard hang where the data port is enumerated but never drains writes;
# the only recovery is a USB-level reset (verified) or unplugging the cable.
#
# Strategy:
#   pre  -> stop the user service so it calls ScreenOff while the device is
#           still healthy (no stale writes survive into the suspend window).
#   post -> USB-reset the screen (recovers any hung SoC; harmless on a healthy
#           one) and start the service, which then re-runs the proven startup
#           path (auto-detect -> wake via /dev/ttyACM1 -> redraw).
#
# Install (as root):
#   sudo install -m 0755 tools/turing-smart-screen-sleep-hook.sh \
#       /usr/lib/systemd/system-sleep/turing-smart-screen
#
# systemd calls this with: $1 = pre|post, $2 = suspend|hibernate|hybrid-sleep|...

# User running the turing-smart-screen.service user unit. Change if needed.
SERVICE_USER="gpm"
SERVICE_UNIT="turing-smart-screen.service"

# USB id of the Turing rev C data interface (the screen's internal SoC).
SCREEN_VID="1d6b"
SCREEN_PID="0106"

USER_UID="$(id -u "$SERVICE_USER" 2>/dev/null)"
[ -z "$USER_UID" ] && exit 0

# Run systemctl --user against the target user's manager (we are root here).
sc() {
    runuser -u "$SERVICE_USER" -- \
        env "XDG_RUNTIME_DIR=/run/user/$USER_UID" \
        systemctl --user "$@"
}

# Issue a USBDEVFS_RESET to the screen if it is currently enumerated. This
# un-wedges a hung SoC; on a healthy device it just forces a clean
# re-enumeration. No-op (exit 0) if the device or python3 is absent.
reset_screen_usb() {
    command -v python3 >/dev/null 2>&1 || return 0
    python3 - "$SCREEN_VID" "$SCREEN_PID" <<'PY'
import fcntl, os, sys, glob
vid, pid = sys.argv[1], sys.argv[2]
USBDEVFS_RESET = (ord('U') << 8) | 20
for d in glob.glob('/sys/bus/usb/devices/*'):
    try:
        if open(d + '/idVendor').read().strip() != vid:
            continue
        if open(d + '/idProduct').read().strip() != pid:
            continue
        b = int(open(d + '/busnum').read())
        n = int(open(d + '/devnum').read())
    except OSError:
        continue
    node = '/dev/bus/usb/%03d/%03d' % (b, n)
    try:
        fd = os.open(node, os.O_WRONLY)
        try:
            fcntl.ioctl(fd, USBDEVFS_RESET, 0)
        finally:
            os.close(fd)
    except OSError:
        pass
PY
}

case "$1" in
    pre)
        # Block suspend until the screen has been turned off cleanly.
        sc stop "$SERVICE_UNIT"
        ;;
    post)
        # Recover a possibly-hung screen, then start fresh. Type=simple unit:
        # start returns as soon as the process is forked; the program itself
        # waits for the display to re-enumerate.
        reset_screen_usb
        sleep 1
        sc start "$SERVICE_UNIT"
        ;;
esac

exit 0
