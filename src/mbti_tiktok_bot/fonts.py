"""Cross-platform Japanese font resolution.

The renderers run on Windows locally and on Linux in CI, so font lookup has to
work in both places. Falling back to Pillow's bitmap default silently drops
every Japanese glyph, so an unresolvable font raises here instead.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

BOLD_FONT_ENV = "MBTI_FONT_BOLD"
REGULAR_FONT_ENV = "MBTI_FONT_REGULAR"

# Entries are "<path>" or "<path>#<face index>" for TrueType collections.
# Face 0 of every Noto Sans CJK collection is the JP face.
BOLD_FONTS = (
    "C:/Windows/Fonts/yu gothic ui semibold.ttf",
    "C:/Windows/Fonts/YuGothB.ttc",
    "C:/Windows/Fonts/meiryob.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc#0",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc#0",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
)
REGULAR_FONTS = (
    "C:/Windows/Fonts/yu gothic ui.ttf",
    "C:/Windows/Fonts/YuGothM.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc#0",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
)


def _split_face_index(candidate: str) -> tuple[str, int]:
    path, separator, index = candidate.rpartition("#")
    if separator and index.isdigit():
        return path, int(index)
    return candidate, 0


def font_candidates(bold: bool = False) -> list[str]:
    override = os.environ.get(BOLD_FONT_ENV if bold else REGULAR_FONT_ENV)
    preferred, fallback = (BOLD_FONTS, REGULAR_FONTS) if bold else (REGULAR_FONTS, BOLD_FONTS)
    return ([override] if override else []) + [*preferred, *fallback]


@lru_cache(maxsize=256)
def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for candidate in font_candidates(bold):
        path, face_index = _split_face_index(candidate)
        if Path(path).exists():
            return ImageFont.truetype(path, size=size, index=face_index)
    raise FileNotFoundError(
        "No Japanese font found. Install fonts-noto-cjk, or point "
        f"{BOLD_FONT_ENV}/{REGULAR_FONT_ENV} at a font file."
    )
