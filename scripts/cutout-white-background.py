"""Turn the four white-background MBTI illustrations into cutouts.

Twelve of the sixteen provided illustrations are transparent PNGs. The other
four (entp, estp, infp, intp) are the same low-poly style on a plain white
field, saved as JPEG, and the renderer had to give them a framed "photo card"
treatment of their own. Removing the white makes all sixteen cutouts, so every
type can be treated the same way.

Only white connected to the edge of the image is removed. White inside the
figure - a collar, a highlight - is surrounded by colour and stays opaque.

Run once:
    .venv-linux/bin/python scripts/cutout-white-background.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "images"
MARKER = (255, 0, 255)
# JPEG ringing leaves the field at 240-255 rather than a clean 255.
THRESHOLD = 28


def cutout(source: Path) -> Image.Image:
    rgb = Image.open(source).convert("RGB")
    width, height = rgb.size
    flooded = rgb.copy()

    edge_points = (
        [(x, 0) for x in range(0, width, 16)]
        + [(x, height - 1) for x in range(0, width, 16)]
        + [(0, y) for y in range(0, height, 16)]
        + [(width - 1, y) for y in range(0, height, 16)]
    )
    for point in edge_points:
        if flooded.getpixel(point) == MARKER:
            continue
        if min(rgb.getpixel(point)) < 255 - THRESHOLD:
            continue
        ImageDraw.floodfill(flooded, point, MARKER, thresh=THRESHOLD)

    # Background is exactly where the flood wrote the marker colour.
    marker = Image.new("RGB", rgb.size, MARKER)
    difference = ImageChops.difference(flooded, marker).convert("L")
    alpha = difference.point(lambda value: 255 if value > 0 else 0)
    # Soften the stair-stepped edge the flood leaves, without eating into the
    # figure: shrink by a pixel, then feather back out.
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))

    result = rgb.convert("RGBA")
    result.putalpha(alpha)
    return result


def main() -> int:
    sources = sorted(IMAGES.glob("*.jpg"))
    if not sources:
        print("No JPEG illustrations left to convert.")
        return 0
    for source in sources:
        image = cutout(source)
        histogram = image.getchannel("A").histogram()
        transparent = sum(histogram[:56]) / (image.size[0] * image.size[1])
        destination = source.with_suffix(".png")
        image.save(destination, optimize=True)
        print(f"{source.name} -> {destination.name}  transparent {transparent:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
