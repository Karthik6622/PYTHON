"""Raju Bhai - shared art, audio and render helpers (Pillow + numpy + ffmpeg + edge-tts). Output size 1080x1920 (YouTube Shorts)."""

from __future__ import annotations

import asyncio
import math
import random
import re
import subprocess
import wave
from pathlib import Path

import numpy as np
import truststore
from PIL import Image, ImageDraw, ImageFilter, ImageFont

truststore.inject_into_ssl()  # corporate proxies re-sign TLS; use the system certificate store
import edge_tts  # noqa: E402
import imageio_ffmpeg  # noqa: E402

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FPS, VW, VH = 30, 1080, 1920
W, H = VW * 2, VH * 2  # scenes are painted at 2x and scaled down per frame (free anti-aliasing)
SR = 44100
FONTS = Path("C:/Windows/Fonts")

# ---- the fixed character design (never change between scenes) ----
ORANGE, ORANGE_DK, CREAM = (232, 115, 26), (190, 85, 15), (246, 238, 224)
AMBER, BLACK = (255, 176, 0), (14, 12, 12)
JACKET, JACKET_DK, TEE, SILVER = (31, 61, 43), (20, 42, 29), (20, 20, 22), (200, 205, 212)


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def vgrad(size, top, bottom) -> Image.Image:
    w, h = size
    t = np.linspace(0, 1, h)[:, None, None]
    arr = (np.array(top)[None, None, :] * (1 - t) + np.array(bottom)[None, None, :] * t) * np.ones((1, w, 1))
    return Image.fromarray(arr.astype("uint8"), "RGB")


def glow(img: Image.Image, box, color, radius=120, alpha=170) -> Image.Image:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(box, fill=(*color, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(radius))
    out = img.convert("RGBA")
    out.alpha_composite(layer)
    return out.convert("RGB")


def light_cast(img: Image.Image, left=(255, 120, 20), right=(30, 110, 255), strength=0.35) -> Image.Image:
    """Orange key light from the left, blue rim light from the right: the series' signature grade."""
    x = np.linspace(0, 1, img.width)[None, :, None]
    tint = np.array(left)[None, None, :] * (1 - x) + np.array(right)[None, None, :] * x
    arr = np.asarray(img).astype("float32")
    arr = arr * (1 - strength * 0.5) + tint * strength * 0.5 + arr * strength * 0.25
    return Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))


# ----------------------------------------------------------------------------------------
# the tiger
# ----------------------------------------------------------------------------------------
def draw_tiger(img: Image.Image, cx: int, cy: int, r: int, mood: str = "calm", body: bool = True) -> None:
    """Raju Bhai: orange Bengal tiger, strong black stripes, white cheeks, amber eyes, scar over the right eyebrow,
    forest-green jacket, black tee, silver RB pendant."""
    d = ImageDraw.Draw(img, "RGBA")
    if body:
        sh = [(cx - 2.1 * r, cy + 3.2 * r), (cx - 1.9 * r, cy + 1.25 * r), (cx - 0.8 * r, cy + 0.85 * r), (cx + 0.8 * r, cy + 0.85 * r), (cx + 1.9 * r, cy + 1.25 * r), (cx + 2.1 * r, cy + 3.2 * r)]
        d.polygon(sh, fill=JACKET)
        d.polygon([(cx - 0.8 * r, cy + 0.85 * r), (cx, cy + 3.2 * r), (cx - 0.25 * r, cy + 3.2 * r), (cx - 1.0 * r, cy + 1.1 * r)], fill=JACKET_DK)
        d.polygon([(cx + 0.8 * r, cy + 0.85 * r), (cx, cy + 3.2 * r), (cx + 0.25 * r, cy + 3.2 * r), (cx + 1.0 * r, cy + 1.1 * r)], fill=JACKET_DK)
        d.polygon([(cx - 0.62 * r, cy + 0.9 * r), (cx + 0.62 * r, cy + 0.9 * r), (cx, cy + 2.3 * r)], fill=TEE)  # black T-shirt
        d.polygon([(cx - 0.5 * r, cy + 0.9 * r), (cx + 0.5 * r, cy + 0.9 * r), (cx, cy + 1.55 * r)], fill=CREAM)  # white chest fur
        d.polygon([(cx - 0.9 * r, cy + 0.7 * r), (cx + 0.9 * r, cy + 0.7 * r), (cx + 0.7 * r, cy + 1.1 * r), (cx - 0.7 * r, cy + 1.1 * r)], fill=ORANGE_DK)  # neck
        chain = [(cx - 0.42 * r, cy + 0.95 * r), (cx - 0.2 * r, cy + 1.6 * r), (cx, cy + 1.78 * r), (cx + 0.2 * r, cy + 1.6 * r), (cx + 0.42 * r, cy + 0.95 * r)]
        d.line(chain, fill=SILVER, width=max(4, int(r * 0.03)))
        px, py, pw = cx, cy + 1.95 * r, 0.2 * r  # RB pendant
        d.rounded_rectangle([px - pw, py - pw * 0.8, px + pw, py + pw * 0.8], radius=int(pw * 0.3), fill=SILVER, outline=(90, 95, 100), width=3)
        d.text((px, py), "RB", font=font("ariblk.ttf", max(14, int(pw * 0.95))), fill=(40, 44, 50), anchor="mm")
    for s in (-1, 1):  # ears
        d.ellipse([cx + s * 0.78 * r - 0.34 * r, cy - 0.95 * r - 0.34 * r, cx + s * 0.78 * r + 0.34 * r, cy - 0.95 * r + 0.34 * r], fill=ORANGE, outline=BLACK, width=max(4, int(r * 0.03)))
        d.ellipse([cx + s * 0.78 * r - 0.19 * r, cy - 0.95 * r - 0.19 * r, cx + s * 0.78 * r + 0.19 * r, cy - 0.95 * r + 0.19 * r], fill=(80, 40, 30))
    d.ellipse([cx - r, cy - 0.95 * r, cx + r, cy + 0.95 * r], fill=ORANGE, outline=BLACK, width=max(5, int(r * 0.035)))
    for s in (-1, 1):  # white cheeks and cheek stripes
        d.ellipse([cx + s * 0.55 * r - 0.52 * r, cy + 0.3 * r - 0.4 * r, cx + s * 0.55 * r + 0.52 * r, cy + 0.3 * r + 0.4 * r], fill=CREAM)
        for k, (dy, ln) in enumerate(((-0.05, 0.42), (0.17, 0.36), (0.38, 0.3))):
            y = cy + dy * r
            d.polygon([(cx + s * 0.99 * r, y - 0.05 * r), (cx + s * (0.99 - ln) * r, y + 0.02 * r), (cx + s * 0.99 * r, y + 0.07 * r)], fill=BLACK)
    for dx, ln in ((0, 0.5), (-0.28, 0.38), (0.28, 0.38), (-0.5, 0.28), (0.5, 0.28)):  # forehead stripes
        d.polygon([(cx + dx * r - 0.05 * r, cy - 0.93 * r + abs(dx) * 0.25 * r), (cx + dx * r + 0.05 * r, cy - 0.93 * r + abs(dx) * 0.25 * r), (cx + dx * r, cy - (0.93 - ln) * r + abs(dx) * 0.25 * r)], fill=BLACK)
    d.ellipse([cx - 0.44 * r, cy + 0.12 * r, cx + 0.44 * r, cy + 0.72 * r], fill=CREAM)  # muzzle
    d.polygon([(cx - 0.13 * r, cy + 0.2 * r), (cx + 0.13 * r, cy + 0.2 * r), (cx, cy + 0.34 * r)], fill=(60, 28, 26))
    open_mouth = mood in ("shock", "roar")
    if open_mouth:
        d.ellipse([cx - 0.2 * r, cy + 0.4 * r, cx + 0.2 * r, cy + 0.66 * r], fill=(70, 20, 25))
    else:
        d.line([(cx, cy + 0.34 * r), (cx, cy + 0.46 * r)], fill=BLACK, width=max(3, int(r * 0.02)))
        d.arc([cx - 0.2 * r, cy + 0.36 * r, cx, cy + 0.56 * r], 20, 160, fill=BLACK, width=max(3, int(r * 0.02)))
        d.arc([cx, cy + 0.36 * r, cx + 0.2 * r, cy + 0.56 * r], 20, 160, fill=BLACK, width=max(3, int(r * 0.02)))
    brow = {"calm": 0.0, "angry": 0.16, "shock": -0.12, "roar": 0.2}[mood]
    for s in (-1, 1):  # amber eyes with slit pupils
        ex, ey = cx + s * 0.4 * r, cy - 0.08 * r
        eh = 0.13 * r if mood != "shock" else 0.19 * r
        d.polygon([(ex - 0.24 * r, ey + 0.02 * r), (ex, ey - eh), (ex + 0.24 * r, ey + 0.02 * r), (ex, ey + eh * 0.8)], fill=AMBER, outline=BLACK)
        pw = 0.025 * r if mood != "shock" else 0.015 * r
        d.ellipse([ex - pw, ey - eh * 0.85, ex + pw, ey + eh * 0.7], fill=BLACK)
        d.ellipse([ex + 0.05 * r, ey - 0.07 * r, ex + 0.1 * r, ey - 0.02 * r], fill=(255, 255, 255, 230))
        inner_y, outer_y = ey - eh - 0.07 * r + brow * r * 1.6, ey - eh - 0.07 * r
        d.line([(ex - s * 0.27 * r, inner_y + 0.02 * r), (ex + s * 0.27 * r, outer_y - 0.0 * r)], fill=BLACK, width=max(8, int(r * 0.07)))
    d.line([(cx - 0.52 * r, cy - 0.34 * r), (cx - 0.38 * r, cy - 0.5 * r)], fill=CREAM, width=max(4, int(r * 0.028)))  # scar above the right eyebrow
    d.line([(cx - 0.47 * r, cy - 0.31 * r), (cx - 0.33 * r, cy - 0.47 * r)], fill=CREAM, width=max(3, int(r * 0.02)))
    for s in (-1, 1):
        for k in range(3):
            d.line([(cx + s * (0.16 + 0.04 * k) * r, cy + 0.42 * r + k * 0.03 * r), (cx + s * (0.55 + 0.05 * k) * r, cy + 0.36 * r + k * 0.06 * r)], fill=(60, 40, 30), width=2)  # whiskers


# ----------------------------------------------------------------------------------------
# scene backgrounds (2160 x 3840)
# ----------------------------------------------------------------------------------------
def city_night(seed: int = 3) -> Image.Image:
    rnd = random.Random(seed)
    img = vgrad((W, H), (6, 8, 26), (70, 38, 40))
    img = glow(img, (W // 2 - 900, 1500, W // 2 + 900, 2500), (255, 120, 30), 300, 150)
    d = ImageDraw.Draw(img, "RGBA")
    for layer, (col, base) in enumerate((((12, 14, 32), 2000), ((8, 10, 22), 2300))):  # two rows of skyline
        x = -100
        while x < W:
            bw, bh = rnd.randint(220, 420), rnd.randint(500, 1500) + (300 if layer == 0 else 0)
            d.rectangle([x, base - bh, x + bw, 2650], fill=col)
            for wy in range(base - bh + 60, 2600, 90):
                for wx in range(x + 30, x + bw - 40, 70):
                    if rnd.random() < 0.34:
                        d.rectangle([wx, wy, wx + 26, wy + 40], fill=rnd.choice([(255, 210, 120, 220), (255, 170, 80, 200), (120, 200, 255, 180)]))
            x += bw + rnd.randint(0, 25)
    for sx, sy, c, t in ((260, 1300, (255, 40, 120), "CHAI"), (1560, 1100, (0, 220, 255), "METRO"), (880, 1500, (255, 200, 0), "BAZAAR")):  # neon signs
        img = glow(img, (sx - 60, sy - 40, sx + 480, sy + 220), c, 70, 120)
        d = ImageDraw.Draw(img, "RGBA")
        d.rounded_rectangle([sx, sy, sx + 420, sy + 150], radius=24, outline=c, width=10)
        d.text((sx + 210, sy + 75), t, font=font("impact.ttf", 100), fill=(255, 255, 255), anchor="mm")
    d.rectangle([0, 2650, W, H], fill=(14, 14, 20))  # wet road with reflections
    for i in range(40):
        rx = rnd.randint(0, W)
        d.rectangle([rx, 2680, rx + rnd.randint(8, 40), H], fill=rnd.choice([(255, 120, 30, 45), (60, 140, 255, 45), (255, 60, 120, 40)]))
    d.polygon([(W // 2 - 60, 2650), (W // 2 + 60, 2650), (W // 2 + 520, H), (W // 2 - 520, H)], fill=(24, 24, 32, 255))
    for k in range(7):
        y0 = 2700 + k * 160
        w0 = 14 + k * 9
        d.polygon([(W // 2 - w0, y0), (W // 2 + w0, y0), (W // 2 + w0 + 8, y0 + 90), (W // 2 - w0 - 8, y0 + 90)], fill=(230, 220, 170, 230))
    return img


def draw_bus(img: Image.Image, cx: int, cy: int, s: float, rear: bool = False) -> Image.Image:
    d = ImageDraw.Draw(img, "RGBA")
    w, h = int(700 * s), int(560 * s)
    d.rounded_rectangle([cx - w // 2, cy - h, cx + w // 2, cy], radius=int(40 * s), fill=(222, 64, 36), outline=(20, 10, 10), width=max(3, int(8 * s)))
    d.rectangle([cx - w // 2 + int(30 * s), cy - h + int(60 * s), cx + w // 2 - int(30 * s), cy - h + int(300 * s)], fill=(20, 28, 48))
    d.rectangle([cx - w // 2, cy - int(150 * s), cx + w // 2, cy - int(120 * s)], fill=(255, 205, 40))
    for sx in (-1, 1):
        lx = cx + sx * int(w * 0.36)
        img = glow(img, (lx - int(150 * s), cy - int(250 * s), lx + int(150 * s), cy - int(20 * s)), (255, 20, 20) if rear else (255, 240, 180), int(60 * s), 220)
        d = ImageDraw.Draw(img, "RGBA")
        d.ellipse([lx - int(40 * s), cy - int(130 * s), lx + int(40 * s), cy - int(50 * s)], fill=(255, 40, 40) if rear else (255, 250, 220))
    if not rear:
        d.rectangle([cx - int(120 * s), cy - h + int(10 * s), cx + int(120 * s), cy - h + int(50 * s)], fill=(30, 30, 30))
        d.text((cx, cy - h + int(30 * s)), "NO DRIVER", font=font("arialbd.ttf", int(28 * s)), fill=(255, 60, 60), anchor="mm")
    return img


def scene_bus() -> Image.Image:
    img = city_night()
    img = draw_bus(img, W // 2, 3300, 2.0)
    return light_cast(img, strength=0.25)


def scene_chase() -> Image.Image:
    img = vgrad((W, H), (4, 6, 18), (40, 28, 40))
    img = glow(img, (W // 2 - 700, 1300, W // 2 + 700, 2000), (255, 90, 30), 280, 140)
    d = ImageDraw.Draw(img, "RGBA")
    vp = (W // 2, 1750)
    d.polygon([(0, H), (W, H), (W // 2 + 90, vp[1]), (W // 2 - 90, vp[1])], fill=(22, 22, 30))
    for side in (-1, 1):  # buildings leaning into the vanishing point
        for k in range(6):
            x0 = W // 2 + side * (150 + k * 150)
            xe = W // 2 + side * (1180 + k * 25)
            d.polygon([(x0, vp[1] - 150 - k * 10), (xe, 200 + k * 230), (xe, 3300), (x0, vp[1] + 40)], fill=(10 + k * 2, 12 + k * 3, 30 + k * 4, 255))
            for wy in range(300 + k * 230, 3200, 160):
                d.rectangle([xe - 120 * side - 30, wy, xe - 120 * side + 30, wy + 70], fill=(255, 200, 110, 200) if (wy // 160 + k) % 3 else (90, 180, 255, 180))
    for k in range(9):  # lane dashes in perspective
        t = k / 9
        y = vp[1] + (H - vp[1]) * t * t
        w0 = 10 + 60 * t * t
        d.polygon([(W // 2 - w0, y), (W // 2 + w0, y), (W // 2 + w0 * 1.3, y + 90 * t * t + 14), (W // 2 - w0 * 1.3, y + 90 * t * t + 14)], fill=(235, 225, 170, 235))
    img = draw_bus(img, W // 2, vp[1] + 40, 0.75, rear=True)
    d = ImageDraw.Draw(img, "RGBA")
    d.polygon([(W // 2 - 360, H), (W // 2 + 360, H), (W // 2 + 160, 2950), (W // 2 - 160, 2950)], fill=(255, 250, 200, 36))  # headlight beam
    d.rounded_rectangle([W // 2 - 520, 3290, W // 2 + 520, 3410], radius=60, fill=(16, 16, 18), outline=(70, 70, 76), width=6)  # handlebar and dash
    d.rectangle([W // 2 - 210, 3410, W // 2 + 210, H], fill=(12, 12, 14))
    d.ellipse([W // 2 - 150, 3440, W // 2 + 150, 3740], fill=(10, 30, 40), outline=(0, 220, 255), width=8)
    d.arc([W // 2 - 110, 3480, W // 2 + 110, 3700], 200, 340, fill=(0, 220, 255), width=10)
    d.line([(W // 2, 3590), (W // 2 + 70, 3530)], fill=(255, 80, 60), width=10)
    for s in (-1, 1):  # the tiger's paws gripping the handlebar
        px = W // 2 + s * 470
        d.ellipse([px - 170, 3170, px + 170, 3470], fill=ORANGE, outline=BLACK, width=10)
        for f in range(4):
            d.ellipse([px - 150 + f * 78, 3380, px - 78 + f * 78, 3500], fill=ORANGE_DK, outline=BLACK, width=6)
        d.polygon([(px - 120, 3190), (px - 70, 3190), (px - 100, 3300)], fill=BLACK)
        d.polygon([(px + 10, 3190), (px + 60, 3190), (px + 30, 3300)], fill=BLACK)
    return light_cast(img, strength=0.3)


def scene_interior() -> Image.Image:
    img = vgrad((W, H), (8, 12, 18), (22, 30, 36))
    d = ImageDraw.Draw(img, "RGBA")
    vp = (W // 2, 1500)
    d.polygon([(0, 700), (W, 700), (W // 2 + 200, 1450), (W // 2 - 200, 1450)], fill=(26, 34, 44))  # ceiling
    d.polygon([(0, H), (W, H), (W // 2 + 200, 1700), (W // 2 - 200, 1700)], fill=(30, 28, 32))  # floor
    for side in (-1, 1):
        for k in range(6):
            t = (k + 1) / 7
            x = W // 2 + side * (200 + 780 * (1 - t) ** 1.3 * 1.2)
            top = 1300 - 800 * (1 - t) ** 1.2
            bot = 1720 + 1250 * (1 - t) ** 1.6
            wid = 80 + 280 * (1 - t)
            d.rounded_rectangle([x - wid, top + (bot - top) * 0.35, x + wid, bot], radius=30, fill=(150, 40, 38) if k % 2 else (120, 34, 34), outline=(30, 10, 10), width=6)
            d.rounded_rectangle([x - wid * 0.9, top, x + wid * 0.9, top + (bot - top) * 0.5], radius=30, fill=(138, 38, 36), outline=(30, 10, 10), width=6)
    for k in range(5):  # flickering ceiling lights
        y = 760 + k * 120
        d.rectangle([W // 2 - 220 + k * 20, y, W // 2 + 220 - k * 20, y + 20], fill=(210, 235, 255, 200))
    img = glow(img, (W // 2 - 520, 2350, W // 2 + 520, 3250), (30, 255, 140), 200, 130)  # the box glows green
    d = ImageDraw.Draw(img, "RGBA")
    d.ellipse([W // 2 - 190, 1760, W // 2 + 190, 2020], fill=(236, 190, 150), outline=(40, 20, 10), width=6)  # the child's head
    d.polygon([(W // 2 - 190, 1840), (W // 2 + 190, 1840), (W // 2 + 210, 1760), (W // 2, 1640), (W // 2 - 210, 1760)], fill=(24, 18, 16))
    d.ellipse([W // 2 - 110, 1860, W // 2 - 60, 1910], fill=(20, 12, 10))
    d.ellipse([W // 2 + 60, 1860, W // 2 + 110, 1910], fill=(20, 12, 10))
    d.arc([W // 2 - 70, 1930, W // 2 + 70, 1990], 200, 340, fill=(60, 20, 20), width=8)
    d.polygon([(W // 2 - 360, 3400), (W // 2 + 360, 3400), (W // 2 + 300, 2050), (W // 2 - 300, 2050)], fill=(220, 70, 40))  # the child's jacket
    d.rounded_rectangle([W // 2 - 430, 2550, W // 2 + 430, 3140], radius=40, fill=(70, 76, 84), outline=(20, 22, 26), width=10)  # the metal box
    d.rectangle([W // 2 - 380, 2640, W // 2 + 380, 2670], fill=(40, 255, 150))
    d.rectangle([W // 2 - 380, 3030, W // 2 + 380, 3060], fill=(40, 255, 150))
    d.ellipse([W // 2 - 60, 2790, W // 2 + 60, 2910], fill=(40, 255, 150))
    return light_cast(img, strength=0.2)


def scene_closeup() -> Image.Image:
    img = vgrad((W, H), (10, 14, 34), (50, 24, 18))
    img = glow(img, (0, 1000, 1100, 2800), (255, 110, 20), 360, 150)
    img = glow(img, (1200, 900, W, 2700), (30, 110, 255), 360, 150)
    draw_tiger(img, W // 2, 1750, 880, "angry")
    return light_cast(img, strength=0.5)


def scene_shock() -> Image.Image:
    img = vgrad((W, H), (6, 10, 24), (30, 20, 26))
    img = glow(img, (200, 400, 1960, 1700), (255, 30, 40), 400, 120)
    draw_tiger(img, W // 2, 2750, 760, "shock")
    return light_cast(img, strength=0.4)


def scene_cobra() -> Image.Image:
    img = vgrad((W, H), (4, 6, 14), (14, 18, 26))
    img = glow(img, (W // 2 - 800, 2300, W // 2 + 800, 3300), (30, 255, 140), 260, 160)
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle([W // 2 - 480, 3100, W // 2 + 480, 3700], radius=40, fill=(70, 76, 84), outline=(20, 22, 26), width=10)
    d.polygon([(W // 2 - 480, 3100), (W // 2 - 620, 2850), (W // 2 - 380, 2800), (W // 2 - 300, 3100)], fill=(86, 92, 100), outline=(20, 22, 26))  # the open lid
    for i in range(22):  # segmented metal body rising and curling
        t = i / 21
        x = W // 2 + math.sin(t * 3.2) * 210
        y = 3150 - t * 1650
        rr = 150 - 50 * t
        d.ellipse([x - rr, y - rr * 0.8, x + rr, y + rr * 0.8], fill=(54 + i * 3, 60 + i * 3, 70 + i * 3), outline=(0, 230, 255, 255), width=6)
        d.arc([x - rr * 0.6, y - rr * 0.5, x + rr * 0.6, y + rr * 0.5], 200, 340, fill=(0, 230, 255), width=5)
    hx, hy = W // 2 + math.sin(3.2) * 210, 1500
    d.polygon([(hx - 560, hy + 260), (hx - 250, hy - 360), (hx, hy - 470), (hx + 250, hy - 360), (hx + 560, hy + 260), (hx, hy + 420)], fill=(48, 54, 64), outline=(0, 230, 255), width=10)  # hood
    for k in range(6):
        d.line([(hx, hy - 420 + k * 20), (hx + (k - 2.5) * 190, hy + 330)], fill=(0, 200, 230, 130), width=5)
    d.ellipse([hx - 190, hy - 190, hx + 190, hy + 210], fill=(60, 66, 78), outline=(0, 230, 255), width=8)
    for s in (-1, 1):
        img = glow(img, (hx + s * 90 - 90, hy - 70, hx + s * 90 + 90, hy + 70), (255, 20, 20), 40, 240)
        d = ImageDraw.Draw(img, "RGBA")
        d.ellipse([hx + s * 90 - 38, hy - 28, hx + s * 90 + 38, hy + 28], fill=(255, 40, 40))
    d.polygon([(hx - 40, hy + 130), (hx - 8, hy + 340), (hx + 8, hy + 340), (hx + 40, hy + 130)], fill=(255, 60, 60))  # fangs
    return light_cast(img, left=(30, 255, 140), right=(30, 110, 255), strength=0.3)


# ----------------------------------------------------------------------------------------
# camera, overlays, text
# ----------------------------------------------------------------------------------------
def camera(base: Image.Image, t: float, z0: float, z1: float, pan=(0.0, 0.0), shake: float = 0.0, seed: int = 0) -> Image.Image:
    z = z0 + (z1 - z0) * t
    cw, ch = W / z, H / z
    cx = W / 2 + pan[0] * W * (t - 0.5)
    cy = H / 2 + pan[1] * H * (t - 0.5)
    if shake:
        rnd = random.Random(seed)
        cx += rnd.uniform(-1, 1) * shake
        cy += rnd.uniform(-1, 1) * shake
    cx, cy = min(max(cx, cw / 2), W - cw / 2), min(max(cy, ch / 2), H - ch / 2)
    return base.resize((VW, VH), Image.LANCZOS, box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2))


def rain_layer(seed: int = 1) -> Image.Image:
    rnd = random.Random(seed)
    layer = Image.new("RGBA", (VW, VH * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(520):
        x, y, ln = rnd.randint(-100, VW), rnd.randint(0, VH * 2), rnd.randint(40, 130)
        a = rnd.randint(60, 150)
        d.line([(x, y), (x - ln * 0.18, y + ln)], fill=(190, 210, 255, a), width=rnd.choice([2, 2, 3]))
    return layer


def vignette() -> Image.Image:
    yy, xx = np.mgrid[0:VH, 0:VW]
    dist = np.sqrt(((xx - VW / 2) / (VW / 2)) ** 2 + ((yy - VH / 2) / (VH / 2)) ** 2)
    alpha = np.clip((dist - 0.55) * 210, 0, 190).astype("uint8")
    out = np.zeros((VH, VW, 4), "uint8")
    out[..., 3] = alpha
    return Image.fromarray(out, "RGBA")


def speed_lines(frame: Image.Image, vp, strength: float, rnd: random.Random) -> None:
    layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(int(46 * strength)):
        a = rnd.uniform(0, math.tau)
        r0, r1 = rnd.uniform(260, 760), rnd.uniform(900, 1700)
        d.line([(vp[0] + math.cos(a) * r0, vp[1] + math.sin(a) * r0), (vp[0] + math.cos(a) * r1, vp[1] + math.sin(a) * r1)], fill=(255, 235, 200, rnd.randint(40, 110)), width=rnd.choice([2, 3, 4]))
    frame.alpha_composite(layer)


def wrap(text: str, fnt, width: int, d: ImageDraw.ImageDraw) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        trial = (cur + " " + w_).strip()
        if d.textlength(trial, font=fnt) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = w_
    return lines + [cur] if cur else lines


def subtitle_image(text: str, speaker: str) -> Image.Image:
    layer = Image.new("RGBA", (VW, VH), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    fnt = font("Nirmala.ttc", 70) if re.search(r"[\u0900-\u097F\u0B80-\u0BFF]", text) else font("ariblk.ttf", 74)
    lines = wrap(text, fnt, VW - 140, d)
    colour = {"raju": (255, 214, 10), "child": (120, 235, 255), "narrator": (255, 255, 255)}[speaker]
    y = 1330 - (len(lines) - 1) * 46
    for line in lines:
        d.text((VW // 2, y), line, font=fnt, fill=colour, anchor="mm", stroke_width=10, stroke_fill=(0, 0, 0))
        y += 98
    return layer


def title_text(layer: Image.Image, text: str, y: int, size: int, colour=(255, 214, 10), stroke=12) -> None:
    ImageDraw.Draw(layer).text((VW // 2, y), text, font=font("impact.ttf", size), fill=colour, anchor="mm", stroke_width=stroke, stroke_fill=(0, 0, 0))


# ----------------------------------------------------------------------------------------
# audio
# ----------------------------------------------------------------------------------------
VOICES = {"narrator": ("en-US-ChristopherNeural", "-4%", "-6Hz"), "raju": ("en-US-GuyNeural", "-8%", "-14Hz"), "child": ("en-US-AnaNeural", "+0%", "+0Hz")}


def speak(text: str, speaker: str, out: Path) -> float:
    voice, rate, pitch = VOICES[speaker]
    mp3 = out.with_suffix(".mp3")
    asyncio.run(edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(mp3)))
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(mp3), "-ar", str(SR), "-ac", "1", str(out)], check=True)
    return len(read_wav(out)) / SR


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype("float32") / 32768


def write_wav(path: Path, data: np.ndarray) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(data, -1, 1) * 32767).astype("<i2").tobytes())


def noise(n: int, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(n).astype("float32")


def lowpass(x: np.ndarray, k: int) -> np.ndarray:
    return np.convolve(x, np.ones(k) / k, mode="same")


def tone(freq, n: int) -> np.ndarray:
    f = np.full(n, freq, "float32") if np.isscalar(freq) else freq
    return np.sin(np.cumsum(f) * math.tau / SR).astype("float32")


def envelope(n: int, attack: float, release: float) -> np.ndarray:
    e = np.ones(n, "float32")
    a, r = int(attack * SR), int(release * SR)
    if a:
        e[:a] = np.linspace(0, 1, a)
    if r:
        e[-r:] = np.linspace(1, 0, r)
    return e


def render_video(frames, audio: Path, out: Path) -> None:
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{VW}x{VH}", "-r", str(FPS), "-i", "-", "-i", str(audio),
           "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert p.stdin is not None
    for fr in frames:
        p.stdin.write(fr.convert("RGB").tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg failed")
