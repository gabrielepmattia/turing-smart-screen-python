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

[Service]
Type=simple
WorkingDirectory=/home/gpm/Applications/turing-smart-screen-python
ExecStart=/home/gpm/Applications/turing-smart-screen-python/venv/bin/python main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
```

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
