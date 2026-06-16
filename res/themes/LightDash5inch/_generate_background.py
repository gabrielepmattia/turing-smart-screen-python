#!/usr/bin/env python3
# Generates the "light clean" 800x480 background for the LightDash5inch theme.
# Static labels (CPU, GPU, NETWORK, field labels, HW model names) are "baked" in
# here; dynamic values are drawn on top by theme.yaml.
# Run from the project root folder:
#   venv/bin/python res/themes/LightDash5inch/_generate_background.py

import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "..", "..", "fonts")

W, H = 800, 480

# --- Light clean palette ---
BG          = (236, 239, 245)
CARD        = (255, 255, 255)
BORDER      = (223, 228, 238)
SHADOW      = (214, 219, 230)
INK         = (33, 43, 58)
SUB         = (132, 142, 158)
CPU_C       = (37, 125, 246)   # blue
GPU_C       = (22, 179, 100)   # green
DOWN_C      = (14, 165, 233)   # cyan
UP_C        = (139, 92, 246)   # violet
WARM_C      = (239, 100, 72)   # temperature
IP_C        = (245, 158, 11)   # amber
TRACK       = (227, 232, 240)

def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)

F_TITLE  = lambda s: font("roboto/Roboto-Bold.ttf", s)
F_MED    = lambda s: font("roboto/Roboto-Medium.ttf", s)
F_REG    = lambda s: font("roboto/Roboto-Regular.ttf", s)

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

def card(box, accent=None, radius=14):
    x0, y0, x1, y1 = box
    # soft shadow
    d.rounded_rectangle((x0+2, y0+3, x1+2, y1+3), radius=radius, fill=SHADOW)
    d.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=CARD, outline=BORDER, width=1)
    if accent:
        # vertical accent bar on the left
        d.rounded_rectangle((x0, y0+8, x0+5, y1-8), radius=2, fill=accent)

def label(xy, text, color=SUB, f=None):
    d.text(xy, text, font=f or F_MED(11), fill=color)

# ===================== HEADER =====================
label((16, 12), "SYSTEM MONITOR", color=INK, f=F_TITLE(20))
label((16, 36), "Ryzen 9 3900XT  ·  RTX 4080", color=SUB, f=F_REG(12))
# divider before the weather widget (weather, date and time are drawn dynamically)
d.line((282, 12, 282, 48), fill=BORDER, width=1)
# divider + SSD / motherboard temperature labels (values drawn dynamically)
d.line((524, 12, 524, 48), fill=BORDER, width=1)
label((532, 13), "SSD", color=SUB, f=F_MED(10))
label((532, 33), "MB", color=SUB, f=F_MED(10))

# ===================== CPU CARD =====================
card((12, 60, 396, 262), accent=CPU_C)
label((28, 70), "CPU", color=CPU_C, f=F_TITLE(22))
label((78, 77), "AMD Ryzen 9 3900XT", color=SUB, f=F_REG(13))
label((30, 158), "USAGE", color=SUB, f=F_MED(11))
# divider
d.line((26, 176, 382, 176), fill=BORDER, width=1)
# 4 cells at the bottom
for cx, lab in ((28, "TEMP"), (120, "FREQ GHz"), (212, "FAN %"), (304, "LOAD")):
    label((cx, 184), lab, color=SUB, f=F_MED(10))

# ===================== GPU CARD =====================
card((404, 60, 788, 262), accent=GPU_C)
label((420, 70), "GPU", color=GPU_C, f=F_TITLE(22))
label((470, 77), "NVIDIA GeForce RTX 4080", color=SUB, f=F_REG(13))
label((422, 158), "USAGE", color=SUB, f=F_MED(11))
d.line((418, 176, 774, 176), fill=BORDER, width=1)
for cx, lab in ((420, "TEMP"), (512, "CLOCK MHz"), (604, "FAN"), (696, "VRAM")):
    label((cx, 184), lab, color=SUB, f=F_MED(10))

# ===================== NETWORK CARD =====================
card((12, 270, 788, 388))
label((28, 282), "NETWORK", color=INK, f=F_TITLE(18))
label((140, 287), "enp39s0", color=SUB, f=F_REG(13))
# uptime / ping labels (values drawn dynamically)
label((250, 287), "UPTIME", color=SUB, f=F_MED(10))
label((560, 287), "PING", color=SUB, f=F_MED(10))
d.line((400, 282, 400, 380), fill=BORDER, width=1)

def arrow(cx, cy, up, color):
    s = 6
    if up:
        d.polygon([(cx, cy-s), (cx-s, cy+s), (cx+s, cy+s)], fill=color)
    else:
        d.polygon([(cx-s, cy-s), (cx+s, cy-s), (cx, cy+s)], fill=color)

# DOWNLOAD (left)
arrow(34, 312, up=False, color=DOWN_C)
label((46, 304), "DOWNLOAD", color=DOWN_C, f=F_MED(13))
label((28, 360), "TOTAL", color=SUB, f=F_MED(10))
# UPLOAD (right)
arrow(424, 312, up=True, color=UP_C)
label((436, 304), "UPLOAD", color=UP_C, f=F_MED(13))
label((418, 360), "TOTAL", color=SUB, f=F_MED(10))

# ===================== IP CARD =====================
card((12, 396, 396, 470), accent=IP_C)
label((28, 405), "IP ADDRESS", color=IP_C, f=F_TITLE(15))
label((28, 430), "LOCAL", color=SUB, f=F_MED(10))
label((210, 430), "PUBLIC", color=SUB, f=F_MED(10))

# ===================== SYS CARD (RAM/DISK) =====================
card((404, 396, 788, 470))
label((420, 405), "MEMORY / STORAGE", color=INK, f=F_TITLE(14))
label((420, 428), "RAM", color=SUB, f=F_MED(11))
label((420, 448), "DISK", color=SUB, f=F_MED(11))
# bar tracks (background) - the colored fill is drawn on top by the theme
# shortened to leave room for the absolute used/total GB values on the right
d.rounded_rectangle((470, 430, 620, 438), radius=4, fill=TRACK)
d.rounded_rectangle((470, 450, 620, 458), radius=4, fill=TRACK)

img.save(os.path.join(HERE, "background.png"))
print("background.png saved:", os.path.join(HERE, "background.png"))
