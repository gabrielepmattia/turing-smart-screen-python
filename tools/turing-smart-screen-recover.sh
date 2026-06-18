#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Preventive recovery for the Turing Smart Screen rev C 5".
#
# The rev C firmware's rendering engine can silently freeze under refresh load:
# the USB stays enumerated, nothing is logged and the monitor process keeps
# writing into the void, so the freeze is UNDETECTABLE from outside (no USB
# re-enumeration, no non-zero exit, no log activity -- note that the data port's
# mtime keeps advancing simply because writes touch the tty, so it is NOT a
# freeze signal). systemd Restart= therefore never fires on its own.
#
# This script performs a full recover that works for both the soft (rendering)
# freeze and a hard SoC hang:
#   stop the user service  (clean ScreenOff while the device may still be healthy)
#   -> USB-reset the SoC    (un-wedges a hard hang; harmless on a healthy device)
#   -> start the service    (proven startup path: auto-detect -> wake -> redraw).
#
# Run on a timer for preventive recovery (see turing-smart-screen-recover.timer),
# or by hand any time the screen looks frozen:
#   sudo tools/turing-smart-screen-recover.sh
#
# Must run as root (the USB reset needs it). Uses runuser to drive the --user
# unit, same as tools/turing-smart-screen-sleep-hook.sh.

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

# Only act if the unit is up: respect a deliberate manual stop. A frozen service
# is still "active" (the process never dies), so this still fires on a real freeze.
state="$(sc show -p ActiveState --value "$SERVICE_UNIT" 2>/dev/null)"
if [ "$state" != "active" ]; then
    echo "turing-smart-screen-recover: service is '$state', skipping"
    exit 0
fi

echo "turing-smart-screen-recover: stop -> USB reset -> start"
sc stop "$SERVICE_UNIT"
sleep 1
reset_screen_usb
sleep 2
sc start "$SERVICE_UNIT"
exit 0
