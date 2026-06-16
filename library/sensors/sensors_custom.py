# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays like Turing Smart Screen or XuanFang
# https://github.com/mathoudebine/turing-smart-screen-python/
#
# Copyright (C) 2021 Matthieu Houdebine (mathoudebine)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# This file allows to add custom data source as sensors and display them in System Monitor themes
# There is no limitation on how much custom data source classes can be added to this file
# See CustomDataExample theme for the theme implementation part

import math
import os
import platform
import re
import socket
import subprocess
import time
from abc import ABC, abstractmethod
from typing import List

import psutil
import requests


# Custom data classes must be implemented in this file, inherit the CustomDataSource and implement its 2 methods
class CustomDataSource(ABC):
    @abstractmethod
    def as_numeric(self) -> float:
        # Numeric value will be used for graph and radial progress bars
        # If there is no numeric value, keep this function empty
        pass

    @abstractmethod
    def as_string(self) -> str:
        # Text value will be used for text display and radial progress bar inner text
        # Numeric value can be formatted here to be displayed as expected
        # It is also possible to return a text unrelated to the numeric value
        # If this function is empty, the numeric value will be used as string without formatting
        pass

    @abstractmethod
    def last_values(self) -> List[float]:
        # List of last numeric values will be used for plot graph
        # If you do not want to draw a line graph or if your custom data has no numeric values, keep this function empty
        pass


# Example for a custom data class that has numeric and text values
class ExampleCustomNumericData(CustomDataSource):
    # This list is used to store the last 10 values to display a line graph
    last_val = [math.nan] * 10  # By default, it is filed with math.nan values to indicate there is no data stored

    def as_numeric(self) -> float:
        # Numeric value will be used for graph and radial progress bars
        # Here a Python function from another module can be called to get data
        # Example: self.value = my_module.get_rgb_led_brightness() / audio.system_volume() ...
        self.value = 75.845

        # Store the value to the history list that will be used for line graph
        self.last_val.append(self.value)
        # Also remove the oldest value from history list
        self.last_val.pop(0)

        return self.value

    def as_string(self) -> str:
        # Text value will be used for text display and radial progress bar inner text.
        # Numeric value can be formatted here to be displayed as expected
        # It is also possible to return a text unrelated to the numeric value
        # If this function is empty, the numeric value will be used as string without formatting
        # Example here: format numeric value: add unit as a suffix, and keep 1 digit decimal precision
        return f'{self.value:>5.1f}%'
        # Important note! If your numeric value can vary in size, be sure to display it with a default size.
        # E.g. if your value can range from 0 to 9999, you need to display it with at least 4 characters every time.
        # --> return f'{self.as_numeric():>4}%'
        # Otherwise, part of the previous value can stay displayed ("ghosting") after a refresh

    def last_values(self) -> List[float]:
        # List of last numeric values will be used for plot graph
        return self.last_val


# Example for a custom data class that only has text values
class ExampleCustomTextOnlyData(CustomDataSource):
    def as_numeric(self) -> float:
        # If there is no numeric value, keep this function empty
        pass

    def as_string(self) -> str:
        # If a custom data class only has text values, it won't be possible to display graph or radial bars
        return "Python: " + platform.python_version()

    def last_values(self) -> List[float]:
        # If a custom data class only has text values, it won't be possible to display line graph
        pass


# Local IP address (LAN) - detected from the default route, without sending traffic
class LocalIP(CustomDataSource):
    def as_numeric(self) -> float:
        # Text only: no numeric value
        pass

    def as_string(self) -> str:
        ip = "N/A"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.3)
            # No packet is actually sent: it only selects the outbound interface
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            ip = "N/A"
        # Fixed-width padding (monospace font) to avoid ghosting
        return f"{ip:<15}"

    def last_values(self) -> List[float]:
        pass


# Public IP address (WAN) - queried online and cached (refreshed every 5 min)
class PublicIP(CustomDataSource):
    _cached_ip = "..."
    _last_fetch = 0.0
    _refresh_interval = 300  # seconds between refreshes

    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        now = time.time()
        if PublicIP._last_fetch == 0.0 or (now - PublicIP._last_fetch) >= PublicIP._refresh_interval:
            try:
                ip = requests.get("https://api.ipify.org", timeout=2).text.strip()
                if ip:
                    PublicIP._cached_ip = ip
                    PublicIP._last_fetch = now
                else:
                    raise ValueError("empty response")
            except Exception:
                # On error, retry in ~30s instead of waiting the whole interval
                PublicIP._last_fetch = now - PublicIP._refresh_interval + 30
                if PublicIP._cached_ip == "...":
                    PublicIP._cached_ip = "N/A"
        return f"{PublicIP._cached_ip:<15}"

    def last_values(self) -> List[float]:
        pass


# Helper: queries nvidia-smi once per cycle and caches several values
# (GPUtil does not expose clock/fan/power/pstate for NVIDIA GPUs)
class _NvidiaSmi:
    _ts = 0.0
    _clock = "N/A"      # core clock (MHz)
    _fan = "N/A"        # fan speed (%)
    _power = "N/A"      # power draw (W)
    _memclk = "N/A"     # memory clock (MHz)
    _pstate = "N/A"     # performance state (P0-P12)
    _vram = "N/A"       # VRAM used/total (GB)

    _FIELDS = "clocks.gr,fan.speed,power.draw,clocks.mem,pstate,memory.used,memory.total"

    @classmethod
    def refresh(cls):
        now = time.time()
        if cls._ts != 0.0 and (now - cls._ts) < 1.5:
            return  # data still fresh: avoid back-to-back calls from the sensors
        cls._ts = now
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=" + cls._FIELDS,
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2,
            )
            clock, fan, power, memclk, pstate, vram_used, vram_total = \
                [v.strip() for v in out.stdout.strip().split(",")]
            cls._clock = clock
            cls._fan = fan
            cls._power = str(round(float(power)))
            cls._memclk = memclk
            cls._pstate = pstate
            cls._vram = f"{float(vram_used) / 1024:.1f}/{float(vram_total) / 1024:.0f} GB"
        except Exception:
            pass


# GPU core clock (MHz) read from nvidia-smi
class GpuClock(CustomDataSource):
    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        _NvidiaSmi.refresh()
        return f"{_NvidiaSmi._clock:>4}"

    def last_values(self) -> List[float]:
        pass


# GPU fan speed (%) read from nvidia-smi
class GpuFan(CustomDataSource):
    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        _NvidiaSmi.refresh()
        return f"{_NvidiaSmi._fan:>3}%"

    def last_values(self) -> List[float]:
        pass


# GPU power draw (W) read from nvidia-smi
class GpuPower(CustomDataSource):
    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        _NvidiaSmi.refresh()
        return f"{_NvidiaSmi._power:>3} W"

    def last_values(self) -> List[float]:
        pass


# GPU memory clock (MHz) read from nvidia-smi
class GpuMemClock(CustomDataSource):
    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        _NvidiaSmi.refresh()
        return f"{_NvidiaSmi._memclk:>4}"

    def last_values(self) -> List[float]:
        pass


# GPU performance state (P0-P12) read from nvidia-smi
class GpuPstate(CustomDataSource):
    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        _NvidiaSmi.refresh()
        return f"{_NvidiaSmi._pstate:>3}"

    def last_values(self) -> List[float]:
        pass


# GPU VRAM used/total (GB) read from nvidia-smi
class GpuVram(CustomDataSource):
    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        _NvidiaSmi.refresh()
        return _NvidiaSmi._vram

    def last_values(self) -> List[float]:
        pass


# Helper: current weather from Open-Meteo (free, no API key). Location is
# auto-detected from the public IP via ip-api.com. Both are cached and the
# weather is refreshed every 15 minutes.
class _Weather:
    _ts = 0.0
    _interval = 900  # seconds between refreshes (15 min)
    _lat = None
    _lon = None
    _temp = "--"
    _desc = "..."
    _code = -1  # latest WMO weather code

    # WMO weather codes -> short text description
    _CODES = {
        0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Rime fog",
        51: "Drizzle", 53: "Drizzle", 55: "Drizzle",
        56: "Freezing drizzle", 57: "Freezing drizzle",
        61: "Rain", 63: "Rain", 65: "Heavy rain",
        66: "Freezing rain", 67: "Freezing rain",
        71: "Snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
        80: "Showers", 81: "Showers", 82: "Heavy showers",
        85: "Snow showers", 86: "Snow showers",
        95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
    }

    @classmethod
    def refresh(cls):
        now = time.time()
        if cls._ts != 0.0 and (now - cls._ts) < cls._interval:
            return  # data still fresh
        try:
            if cls._lat is None:
                geo = requests.get("http://ip-api.com/json", timeout=2).json()
                cls._lat, cls._lon = geo["lat"], geo["lon"]
            r = requests.get(
                "https://api.open-meteo.com/v1/forecast"
                f"?latitude={cls._lat}&longitude={cls._lon}"
                "&current=temperature_2m,weather_code",
                timeout=2,
            ).json()
            cur = r["current"]
            cls._temp = f"{round(cur['temperature_2m'])}°C"
            cls._code = cur["weather_code"]
            cls._desc = cls._CODES.get(cls._code, "")
            cls._ts = now
        except Exception:
            # Retry in ~1 min on error instead of waiting the whole interval
            cls._ts = now - cls._interval + 60


# Current outside temperature (Open-Meteo)
class WeatherTemp(CustomDataSource):
    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        _Weather.refresh()
        return _Weather._temp

    def last_values(self) -> List[float]:
        pass


# Current weather description (Open-Meteo)
class WeatherDesc(CustomDataSource):
    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        _Weather.refresh()
        return _Weather._desc

    def last_values(self) -> List[float]:
        pass


# Weather condition as a color emoji icon (rendered via NotoColorEmoji).
# Maps the WMO weather code to a representative emoji.
class WeatherIcon(CustomDataSource):
    _SUN = "☀️"
    _SUN_CLOUD = "\U0001f324️"
    _PARTLY = "⛅"
    _CLOUD = "☁️"
    _FOG = "\U0001f32b️"
    _DRIZZLE = "\U0001f326️"
    _RAIN = "\U0001f327️"
    _SNOW = "\U0001f328️"
    _STORM = "⛈️"

    _ICONS = {
        0: _SUN, 1: _SUN_CLOUD, 2: _PARTLY, 3: _CLOUD,
        45: _FOG, 48: _FOG,
        51: _DRIZZLE, 53: _DRIZZLE, 55: _DRIZZLE, 56: _DRIZZLE, 57: _DRIZZLE,
        61: _RAIN, 63: _RAIN, 65: _RAIN, 66: _RAIN, 67: _RAIN,
        71: _SNOW, 73: _SNOW, 75: _SNOW, 77: _SNOW,
        80: _DRIZZLE, 81: _RAIN, 82: _RAIN,
        85: _SNOW, 86: _SNOW,
        95: _STORM, 96: _STORM, 99: _STORM,
    }

    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        _Weather.refresh()
        return WeatherIcon._ICONS.get(_Weather._code, self._SUN)

    def last_values(self) -> List[float]:
        pass


# RAM usage as absolute values "used/total GB" (the native MEMORY sensor only exposes MB)
class RamUsage(CustomDataSource):
    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        try:
            m = psutil.virtual_memory()
            return f"{m.used / 1024 ** 3:.1f}/{m.total / 1024 ** 3:.0f} GB"
        except Exception:
            return "--"

    def last_values(self) -> List[float]:
        pass


# Root filesystem usage as absolute values "used/total GB"
class DiskUsage(CustomDataSource):
    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        try:
            d = psutil.disk_usage("/")
            return f"{d.used / 1000 ** 3:.0f}/{d.total / 1000 ** 3:.0f} GB"
        except Exception:
            return "--"

    def last_values(self) -> List[float]:
        pass


# System uptime in compact form (e.g. "3d 5h", "5h 12m", "12m")
class Uptime(CustomDataSource):
    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        try:
            secs = int(time.time() - psutil.boot_time())
        except Exception:
            return "--"
        days, rem = divmod(secs, 86400)
        hours, rem = divmod(rem, 3600)
        mins = rem // 60
        if days > 0:
            return f"{days}d {hours}h"
        if hours > 0:
            return f"{hours}h {mins}m"
        return f"{mins}m"

    def last_values(self) -> List[float]:
        pass


# Network latency to 8.8.8.8 via the system 'ping' (no root needed, unlike raw ICMP).
# Cached and refreshed every ~2s so the blocking subprocess does not slow the custom cycle.
class PingLatency(CustomDataSource):
    _cached = "--"
    _last = 0.0

    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        now = time.time()
        if now - PingLatency._last >= 2:
            PingLatency._last = now
            try:
                out = subprocess.run(
                    ["ping", "-c", "1", "-W", "1", "8.8.8.8"],
                    capture_output=True, text=True, timeout=2,
                ).stdout
                m = re.search(r"time=([\d.]+)", out)
                PingLatency._cached = f"{round(float(m.group(1)))} ms" if m else "--"
            except Exception:
                PingLatency._cached = "--"
        return f"{PingLatency._cached:<7}"

    def last_values(self) -> List[float]:
        pass


# Helper: read a temperature by chip name + label from psutil (cached briefly)
def _temp_by_label(chip: str, label: str) -> str:
    try:
        for entry in psutil.sensors_temperatures().get(chip, []):
            if entry.label == label:
                return f"{round(entry.current)}°C"
    except Exception:
        pass
    return "--"


# SSD NVMe temperature (nvme / Composite)
class NvmeTemp(CustomDataSource):
    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        return _temp_by_label("nvme", "Composite")

    def last_values(self) -> List[float]:
        pass


# Motherboard / system temperature (nct6797 / SYSTIN)
class MoboTemp(CustomDataSource):
    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        return _temp_by_label("nct6797", "SYSTIN")

    def last_values(self) -> List[float]:
        pass


# CPU load average over 5 minutes
class LoadAvg5(CustomDataSource):
    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        try:
            return f"{os.getloadavg()[1]:.2f}"
        except Exception:
            return "--"

    def last_values(self) -> List[float]:
        pass


# CPU load average over 15 minutes
class LoadAvg15(CustomDataSource):
    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        try:
            return f"{os.getloadavg()[2]:.2f}"
        except Exception:
            return "--"

    def last_values(self) -> List[float]:
        pass


# Number of running processes
class ProcCount(CustomDataSource):
    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        try:
            return str(len(psutil.pids()))
        except Exception:
            return "--"

    def last_values(self) -> List[float]:
        pass


# Case fan speeds (RPM) from the nct6797 chip, only the spinning ones
class CaseFans(CustomDataSource):
    def as_numeric(self) -> float:
        pass

    def as_string(self) -> str:
        try:
            fans = psutil.sensors_fans().get("nct6797", [])
            rpms = [str(int(e.current)) for e in fans if e.current and e.current > 0]
            return " ".join(rpms) if rpms else "--"
        except Exception:
            return "--"

    def last_values(self) -> List[float]:
        pass
