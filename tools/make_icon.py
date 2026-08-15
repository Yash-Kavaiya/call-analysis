#!/usr/bin/env python
"""Generate the Call Analysis app icon (NVIDIA-green waveform) as a multi-size .ico.

Usage:
    python tools/make_icon.py            # writes electron/assets/icon.ico
    python tools/make_icon.py --out x.ico
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

GREEN_TOP = (166, 255, 0)
GREEN_BOTTOM = (76, 107, 0)
BG = (11, 15, 20)
SIZES = [16, 24, 32, 48, 64, 128, 256]


def make_icon(size: int) -> Image.Image:
    """Rounded NVIDIA-green tile with a stylized waveform."""
    scale = size / 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background tile
    radius = int(44 * scale)
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    td.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=BG)

    # Vertical green gradient inside the tile
    grad = Image.new("RGBA", (1, size))
    for y in range(size):
        t = y / max(1, size - 1)
        r = round(GREEN_TOP[0] + (GREEN_BOTTOM[0] - GREEN_TOP[0]) * t)
        g = round(GREEN_TOP[1] + (GREEN_BOTTOM[1] - GREEN_TOP[1]) * t)
        b = round(GREEN_TOP[2] + (GREEN_BOTTOM[2] - GREEN_TOP[2]) * t)
        grad.putpixel((0, y), (r, g, b, 255))
    grad = grad.resize((size, size))
    tile.paste(grad, (0, 0), tile)
    img.paste(tile, (0, 0), tile)

    # Waveform polyline (mirror-vertical bars around center)
    cx = size / 2
    bar_w = max(1, round(10 * scale))
    gap = max(1, round(6 * scale))
    x = cx - (bar_w * 4 + gap * 3) / 2
    heights = [0.22, 0.5, 0.78, 0.55, 0.34]  # fraction of half-height
    half = size * 0.34
    for h in heights:
        amp = half * h
        draw.rounded_rectangle(
            [x, size / 2 - amp, x + bar_w, size / 2 + amp],
            radius=bar_w / 2,
            fill=(11, 15, 20, 255),
        )
        x += bar_w + gap
    return img


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "electron" / "assets" / "icon.ico"))
    parser.add_argument("--png", help="Also write a single-size PNG here")
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Pillow's ICO writer only keeps sizes <= the base image's size, so the
    # base must be the largest frame and the rest follow as append_images.
    images = [make_icon(s) for s in sorted(SIZES, reverse=True)]
    images[0].save(
        out,
        format="ICO",
        sizes=[(s, s) for s in sorted(SIZES)],
        append_images=images[1:],
    )
    print(f"Wrote {out} ({len(SIZES)} sizes)")

    if args.png:
        png_path = Path(args.png)
        make_icon(256).save(png_path, format="PNG")
        print(f"Wrote {png_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
