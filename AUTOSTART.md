# Running the Turing Smart Screen monitor

Quick guide to start the system monitor and make it run automatically.

## Configuration (already done)

In `config.yaml`:

- `REVISION: C` — the connected display is a Turing rev. C (VID:PID `1a86:ca21`, serial `CT21INCH`)
- `THEME: LightDash5inch` — custom light/clean 5" landscape theme
- `ETH: enp39s0` — active Ethernet interface (for network stats)
- `CPU_FAN: nct6797/fan2` — CPU fan source (best guess; change if the value looks wrong)

## Manual start

From the project folder:

```bash
venv/bin/python main.py
```

It runs in the foreground. To stop it: `Ctrl+C`.

To run it in the background:

```bash
cd /home/gpm/Applications/turing-smart-screen-python && venv/bin/python main.py &
```

---

## Auto-start with systemd (user service)

> NOTE: run these commands yourself in a terminal (or in the Claude Code prompt
> using the `!` prefix). The tray icon will not appear if the service starts
> before the graphical session, but the physical display still works.

### 1) Create the service file

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/turing-smart-screen.service <<'EOF'
[Unit]
Description=Turing Smart Screen - System Monitor
Documentation=https://github.com/mathoudebine/turing-smart-screen-python
After=default.target
# Keep retrying without ever hitting the start-rate limiter: on a rev C 5"
# the data port /dev/ttyACM0 disappears for several seconds on every restart
# (USB re-enumeration), so a few quick attempts may fail before the display is
# woken back up via /dev/ttyACM1 and the port reappears.
StartLimitIntervalSec=0

[Service]
Type=simple
WorkingDirectory=/home/gpm/Applications/turing-smart-screen-python
ExecStart=/home/gpm/Applications/turing-smart-screen-python/venv/bin/python main.py
# always (not on-failure): when the COM port is missing the program exits 0,
# which on-failure would NOT catch, leaving the service dead after a restart.
Restart=always
RestartSec=8

[Install]
WantedBy=default.target
EOF
```

> **Note (rev C 5").** With `Restart=on-failure` a restart could leave the
> service dead: closing the old process makes `/dev/ttyACM0` re-enumerate, the
> new process finds the port missing and exits with code 0 (not a failure).
> `Restart=always` + `StartLimitIntervalSec=0` let systemd keep retrying until
> the display is back (typically one extra attempt, ~20 s), with no manual step.

### 2) Enable and start the service

```bash
systemctl --user daemon-reload
systemctl --user enable --now turing-smart-screen.service
```

### 3) (Optional) Start even before login

Requires root privileges (it will ask for your password):

```bash
sudo loginctl enable-linger gpm
```

If you skip this step the service still starts, but only at first login.

---

## Turn the screen off on suspend / back on at resume

On Linux there is no built-in suspend/resume handling (the Windows build has it,
but it does not apply here). Without it, when the PC goes to standby the running
process keeps a now-dead serial handle open: at resume the rev C data port has
re-enumerated (it disappears for several seconds) and the next blocking serial
write hangs forever, leaving the **display frozen** until a manual restart. Worse,
a write that hits the screen at the wrong moment can wedge its internal SoC into
a hard hang where `/dev/ttyACM0` is enumerated but never drains writes — only a
USB-level reset or unplugging the cable recovers it.

The fix is a systemd `system-sleep` hook (shipped in `tools/`) that:

- **before sleep** stops the user service, so it calls `ScreenOff` while the
  device is still healthy (no stale writes survive into the suspend window);
- **at resume** issues a USB reset to the screen (un-wedges a hung SoC; harmless
  on a healthy one) and starts the service again, reusing the proven startup
  path (auto-detect → wake via `/dev/ttyACM1` → redraw).

The hook runs as root (system-sleep hooks always do), which is why it can do the
USB reset directly.

Install it once (needs root):

```bash
sudo install -m 0755 \
  /home/gpm/Applications/turing-smart-screen-python/tools/turing-smart-screen-sleep-hook.sh \
  /usr/lib/systemd/system-sleep/turing-smart-screen
```

> The script targets the `gpm` user's service manager. If you run the service as
> a different user, edit `SERVICE_USER` at the top of the script before installing.

Test it without a real suspend:

```bash
# Should turn the screen off (service stops)
sudo /usr/lib/systemd/system-sleep/turing-smart-screen pre suspend
# Should bring it back on (service starts, ~10-20 s for the rev C to re-enumerate)
sudo /usr/lib/systemd/system-sleep/turing-smart-screen post suspend
```

To remove it: `sudo rm /usr/lib/systemd/system-sleep/turing-smart-screen`.

---

## Useful commands

```bash
# Service status
systemctl --user status turing-smart-screen.service

# Live logs
journalctl --user -u turing-smart-screen.service -f

# Stop / restart
systemctl --user stop turing-smart-screen.service
systemctl --user restart turing-smart-screen.service

# Disable auto-start completely
systemctl --user disable --now turing-smart-screen.service
```

## Notes

- Do not run two instances of `main.py` at the same time: they fight over the
  same serial port. Close any manual launches before starting the service.
- The user must be in the `uucp` group to access `/dev/ttyACM*` without `sudo`
  (already verified: OK).

## Custom theme: LightDash5inch

A custom "light clean" 5" landscape theme is included under
`res/themes/LightDash5inch/`. It shows CPU / GPU usage (with history graphs),
temperatures, clocks, fans, VRAM, network up/down (with graphs and totals),
local and public IP, plus RAM/disk bars.

- `theme.yaml` — layout and dynamic values
- `background.png` — generated static background
- `_generate_background.py` — regenerate the background after editing the layout:
  ```bash
  venv/bin/python res/themes/LightDash5inch/_generate_background.py
  ```

The local/public IP, GPU clock/fan and weather values come from custom data
sources added to `library/sensors/sensors_custom.py` (`LocalIP`, `PublicIP`,
`GpuClock`, `GpuFan`, `WeatherTemp`, `WeatherDesc`). The public IP is fetched
from `api.ipify.org` and cached (refreshed every 5 minutes). The weather comes
from Open-Meteo (free, no API key) with the location auto-detected from the
public IP; it is refreshed every 15 minutes.
