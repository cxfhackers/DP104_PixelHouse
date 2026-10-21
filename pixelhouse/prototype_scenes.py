"""8×24 uploadable scenes sampled from the approved PixelHouse gallery artwork.

The gallery cards and the keyboard preview share these exact HSV frames. Sampling
the included artwork avoids maintaining a second, hand-drawn approximation.
"""
from __future__ import annotations

import colorsys
from functools import lru_cache
from pathlib import Path

from PIL import Image

SCENES = (
    "可爱猫咪", "心动爱心", "像素星空", "游戏手柄", "音符律动", "赛博城市", "像素火焰",
    "海浪流动", "山川日出", "彩虹路径", "太空火箭", "像素植物", "雪花飘落", "数字时钟",
)

_CARD_X = (78, 271, 456, 640, 825, 1009, 1194)
_CARD_Y = (739, 879)


@lru_cache(maxsize=1)
def _artwork() -> Image.Image:
    with Image.open(Path(__file__).parent / "assets" / "prototype-skin.png") as source:
        return source.convert("RGB")


@lru_cache(maxsize=14)
def _base_frame(name: str) -> bytes:
    index = SCENES.index(name)
    origin_x = _CARD_X[index % 7]
    origin_y = _CARD_Y[index // 7]
    image = _artwork()
    frame = bytearray()
    for y in range(8):
        for x in range(24):
            center_x = round(origin_x + 18 + x * 6.07)
            center_y = round(origin_y + 20 + y * 7.6)
            samples = (image.getpixel((center_x + dx, center_y + dy))
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            red, green, blue = max(samples, key=max)
            if max(red, green, blue) <= 145:
                frame.extend(b"\0\0\0")
            else:
                hue, saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
                frame.extend((round(hue * 255) & 255, round(saturation * 255), round(value * 255)))
    return bytes(frame)


def make_scene(name: str) -> tuple[list[bytes], int]:
    """Return the same 8×24 pixels used in each card and in device uploads."""
    base = _base_frame(name)
    frames = [base]
    for phase in range(1, 8):
        frame = bytearray(base)
        for y in range(8):
            for x in range(24):
                offset = (y * 24 + x) * 3
                if frame[offset + 2] and (x * 5 + y * 7) % 19 == phase:
                    frame[offset + 2] = max(1, round(frame[offset + 2] * 0.72))
        frames.append(bytes(frame))
    return frames, 8
