"""Build the PixelHouse macOS icon from the app's pixel-cat motif."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "pixelhouse" / "assets"
CAT = (
    "PP......PP",
    "PPP....PPP",
    "PPPPPPPPPP",
    "PWWWWWWWWP",
    "PWKWWWWKWP",
    "PWWWPWWWWP",
    ".PPPPPPPP.",
    "..P....P..",
)


def draw_icon() -> Image.Image:
    size = 1024
    icon = Image.new("RGBA", (size, size))
    fill = Image.new("RGBA", (size, size))
    pixels = fill.load()
    for y in range(size):
        for x in range(size):
            pixels[x, y] = (9 + y // 165, 18 + x // 130, 57 + y // 45, 255)
    mask = Image.new("L", (size, size))
    ImageDraw.Draw(mask).rounded_rectangle((60, 60, 964, 964), radius=205, fill=255)
    icon.paste(fill, (0, 0), mask)

    art = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(art)
    draw.rounded_rectangle((93, 93, 931, 931), radius=172, outline="#728bff", width=23)
    draw.rounded_rectangle((133, 133, 891, 891), radius=145, outline="#4a5bb4", width=7)
    for y in range(175, 850, 42):
        for x in range(175, 850, 42):
            draw.rectangle((x, y, x + 2, y + 2), fill="#283b85")
    for x, y, color in ((190, 205, "#50ddff"), (786, 230, "#ff7bd6"),
                        (216, 760, "#ff78d7"), (777, 775, "#60ddff")):
        draw.rectangle((x, y, x + 35, y + 35), fill=color)

    cell = 61
    left = (size - len(CAT[0]) * cell) // 2
    top = 245
    colors = {"P": "#fa8ddb", "W": "#ffe8fa", "K": "#1b2258"}
    for row, line in enumerate(CAT):
        for col, symbol in enumerate(line):
            if symbol in colors:
                x, y = left + col * cell, top + row * cell
                draw.rectangle((x + 3, y + 3, x + cell - 4, y + cell - 4), fill=colors[symbol])
    glow = art.filter(ImageFilter.GaussianBlur(25))
    icon.alpha_composite(glow)
    icon.alpha_composite(art)
    return icon


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    icon = draw_icon()
    icon.save(ASSETS / "pixelhouse-icon.png")
    with tempfile.TemporaryDirectory(prefix="pixelhouse-icon-") as directory:
        iconset = Path(directory) / "PixelHouse.iconset"
        iconset.mkdir()
        for points in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                size = points * scale
                suffix = "@2x" if scale == 2 else ""
                icon.resize((size, size), Image.Resampling.LANCZOS).save(
                    iconset / f"icon_{points}x{points}{suffix}.png"
                )
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o",
                        str(ASSETS / "pixelhouse.icns")], check=True)


if __name__ == "__main__":
    main()
