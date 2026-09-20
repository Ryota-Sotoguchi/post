"""The texture library: drawn once by an image model, recoloured here.

scripts/generate-backgrounds.py writes assets/backgrounds/<look>/NN.jpg. Nothing
in the daily run calls an image API - a post picks a file by its seed, so the
same post always gets the same one and a run never fails on a network call.

What is used from a file is its structure: light, grain, depth, shape. Each look
maps the luminance onto its own colours, so the twenty-four palettes keep
deciding what a slide looks like and a texture cannot drag a post off-palette.
The library is optional; with the folder empty every look falls back to what it
drew before.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image

from mbti_tiktok_bot.design import effects as fx
from mbti_tiktok_bot.design.core import Context
from mbti_tiktok_bot.visuals import _seed_choice

FOLDER = ("assets", "backgrounds")


def library(root: Path, look: str) -> list[Path]:
    folder = root.joinpath(*FOLDER, look)
    return sorted(path for path in folder.glob("*.jpg")) if folder.is_dir() else []


# One prepared texture is a full-size RGBA canvas, so the cache is kept small:
# a render uses one, and the next post usually wants a different palette anyway.
@lru_cache(maxsize=2)
def _prepared(path: str, size: tuple[int, int], dark: str, light: str) -> Image.Image:
    with Image.open(path) as opened:
        opened.load()
        return fx.tint_luminance(fx.cover(opened.convert("RGB"), size), dark, light)


def texture(ctx: Context, look: str, dark: str, light: str, alpha: int = 255) -> Image.Image | None:
    """This post's texture, cropped to the canvas and recoloured. None when the library is empty."""
    files = library(ctx.config.project_root, look)
    if not files:
        return None
    chosen = files[_seed_choice(ctx.seed, f"{look}.texture", len(files))]
    prepared = _prepared(str(chosen), ctx.device, dark, light)
    if alpha >= 255:
        return prepared.copy()
    faded = prepared.copy()
    faded.putalpha(alpha)
    return faded
