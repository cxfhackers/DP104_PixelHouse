"""Small hand-drawn characters and looping scenes for an 8 x 24 pixel screen."""

from __future__ import annotations

import math

from .effects import COLS, ROWS
from .image_import import rgb_hex_to_hsv_pixel

SCENES = (
    ("霓虹小猫", "粉蓝小猫与闪烁爱心", 8, 16),
    ("兔兔跳跳", "兔子左右跳跃", 8, 24),
    ("兔兔晚安", "睡着的兔子与月亮", 6, 12),
    ("小猫追球", "小猫追着彩球跑", 8, 24),
    ("小猫眨眼", "小猫歪头眨眼", 6, 12),
    ("幽灵飘飘", "小幽灵上下漂浮", 8, 16),
    ("幽灵捉迷藏", "小幽灵左右躲闪", 8, 24),
)

_PALETTE = {
    ".": b"\0\0\0",
    "W": rgb_hex_to_hsv_pixel("#fff0d9"),
    "P": rgb_hex_to_hsv_pixel("#ff8cae"),
    "D": rgb_hex_to_hsv_pixel("#41345c"),
    "Y": rgb_hex_to_hsv_pixel("#ffda73"),
    "C": rgb_hex_to_hsv_pixel("#85e7e4"),
    "B": rgb_hex_to_hsv_pixel("#8cb8ff"),
    "M": rgb_hex_to_hsv_pixel("#ff62da"),
    "N": rgb_hex_to_hsv_pixel("#56ebff"),
}

_RABBIT = (
    "..W...W..",
    "..WP.WPW.",
    "..WW.WW..",
    ".WWWWWWW.",
    ".WDWWWDW.",
    ".WWWPWWW.",
    "W.WWWWW.W",
)
_CAT = (
    "W.......W",
    "WW.....WW",
    "WWWWWWWWW",
    "WWDWWWDWW",
    "WWWWPWWWW",
    ".WWWWWWW.",
    "..WW.WW..",
)
_GHOST = (
    "..WWWWW..",
    ".WWWWWWW.",
    "WWDWWWDWW",
    "WWWWPWWWW",
    "WWWWWWWWW",
    "W.WW.WW.W",
)


def _stamp(grid: list[list[str]], sprite: tuple[str, ...], left: int, top: int,
           *, blink: bool = False) -> None:
    for y, row in enumerate(sprite):
        for x, char in enumerate(row):
            if char == "." or not 0 <= left + x < COLS or not 0 <= top + y < ROWS:
                continue
            if blink and char == "D":
                char = "W"
            grid[top + y][left + x] = char
    if blink:
        for x in (left + 2, left + 6):
            y = top + 3
            if 0 <= x < COLS and 0 <= y < ROWS:
                grid[y][x] = "D"


def make_scene(name: str) -> tuple[list[bytes], int]:
    metadata = next((scene for scene in SCENES if scene[0] == name), None)
    if metadata is None:
        raise ValueError("未知像素宠物场景")
    _, _, fps, count = metadata
    frames: list[bytes] = []
    for phase in range(count):
        grid = [["." for _ in range(COLS)] for _ in range(ROWS)]
        cycle = phase / count
        if name == "霓虹小猫":
            def put(points, color):
                for x, y in points:
                    if 0 <= x < COLS and 0 <= y < ROWS:
                        grid[y][x] = color
            # An actual 8×24 scene: the preview and uploaded LEDs use the same pixels.
            put([(8, 0), (9, 1), (15, 1), (16, 0), (8, 1), (16, 1)], "M")
            put([(x, 2) for x in range(7, 18)], "M")
            put([(7, y) for y in range(3, 6)] + [(17, y) for y in range(3, 6)], "M")
            put([(x, 6) for x in range(8, 17)], "M")
            put([(x, 7) for x in range(6, 20)], "N")
            put([(6, 5), (6, 6), (18, 5), (18, 6), (19, 6), (20, 5)], "N")
            put([(9, 4), (15, 4)] if phase not in (6, 7) else [(9, 5), (15, 5)], "N")
            put([(12, 5), (11, 6), (13, 6)], "M")
            heart = [(2, 2), (4, 2), (1, 3), (3, 3), (5, 3), (2, 4), (4, 4), (3, 5)]
            put(heart, "M" if phase < 8 else "P")
            put([(21, 1), (21, 3), (20, 2), (22, 2)], "N")
            if phase in (0, 4, 8, 12):
                put([(3, 1), (22, 5)], "W")
        elif name == "兔兔跳跳":
            travel = phase if phase <= 12 else 24 - phase
            _stamp(grid, _RABBIT, 2 + travel, -1 if phase % 6 in (2, 3) else 1)
            grid[7][2 + travel] = "P"
        elif name == "兔兔晚安":
            _stamp(grid, _RABBIT, 7, 1, blink=True)
            for x, y in ((19, 1), (20, 1), (18, 2), (20, 2), (19, 3)):
                grid[y][x] = "Y"
            grid[phase % 3][21] = "Y"
        elif name == "小猫追球":
            travel = phase if phase <= 12 else 24 - phase
            _stamp(grid, _CAT, 1 + travel, 1 if phase % 4 < 2 else 0)
            ball_x = min(COLS - 1, 11 + travel)
            grid[6 if phase % 4 < 2 else 5][ball_x] = "P"
        elif name == "小猫眨眼":
            _stamp(grid, _CAT, 8, 1, blink=phase in (4, 5))
            if phase in (2, 8):
                grid[0][19 if phase == 2 else 18] = "Y"
        elif name == "幽灵飘飘":
            _stamp(grid, _GHOST, 8, 0 if phase % 8 < 4 else 2)
            grid[phase % 6][3] = "C"
        else:
            left = 2 + round(12 * (1 + math.sin(cycle * math.tau - math.pi / 2)) / 2)
            _stamp(grid, _GHOST, left, phase % 6 == 3)
            grid[1][21] = "Y"
        pixels = bytearray()
        for row in grid:
            for char in row:
                pixels.extend(_PALETTE[char])
        frames.append(bytes(pixels))
    return frames, fps
