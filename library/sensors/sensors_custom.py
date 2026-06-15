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
import platform
import socket
import subprocess
import time
from abc import ABC, abstractmethod
from typing import List

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


# Helper: queries nvidia-smi once per cycle and caches clock + fan
# (GPUtil does not expose these two values for NVIDIA GPUs)
class _NvidiaSmi:
    _ts = 0.0
    _clock = "N/A"
    _fan = "N/A"

    @classmethod
    def refresh(cls):
        now = time.time()
        if cls._ts != 0.0 and (now - cls._ts) < 1.5:
            return  # data still fresh: avoid back-to-back calls from the two sensors
        cls._ts = now
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=clocks.gr,fan.speed",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2,
            )
            clock, fan = out.stdout.strip().split(",")
            cls._clock = clock.strip()
            cls._fan = fan.strip()
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
