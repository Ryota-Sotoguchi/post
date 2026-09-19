"""Named typefaces for the slide designs.

The styles ask for a role - "jp-black", "display", "serif" - not a file. Each
role lists candidates in order; the bundled fonts in assets/fonts come first,
system fonts after, so a checkout without the bundle still renders, only
plainer.

Everything is resolved at the logical size. ScaledDraw re-opens the same file
at render scale when it draws, and measurement always happens at 1x.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from mbti_tiktok_bot.fonts import load_font

FONT_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"
NOTO = Path("/usr/share/fonts/opentype/noto")

# (path, face index). Noto CJK collections carry the JP face at index 0.
FACES: dict[str, tuple[tuple[Path, int], ...]] = {
    "jp-black": ((FONT_DIR / "ZenKakuGothicNew-Black.ttf", 0), (NOTO / "NotoSansCJK-Black.ttc", 0)),
    "jp-bold": ((FONT_DIR / "ZenKakuGothicNew-Bold.ttf", 0), (NOTO / "NotoSansCJK-Bold.ttc", 0)),
    "jp-medium": ((FONT_DIR / "ZenKakuGothicNew-Medium.ttf", 0), (NOTO / "NotoSansCJK-Medium.ttc", 0)),
    "jp-light": ((NOTO / "NotoSansCJK-DemiLight.ttc", 0), (FONT_DIR / "ZenKakuGothicNew-Medium.ttf", 0)),
    "serif-black": ((NOTO / "NotoSerifCJK-Black.ttc", 0), (FONT_DIR / "ZenKakuGothicNew-Black.ttf", 0)),
    "serif": ((NOTO / "NotoSerifCJK-SemiBold.ttc", 0), (FONT_DIR / "ZenKakuGothicNew-Bold.ttf", 0)),
    "serif-light": ((NOTO / "NotoSerifCJK-Regular.ttc", 0), (FONT_DIR / "ZenKakuGothicNew-Medium.ttf", 0)),
    "display": ((FONT_DIR / "Anton-Regular.ttf", 0), (NOTO / "NotoSansCJK-Black.ttc", 0)),
    "label": ((FONT_DIR / "BebasNeue-Regular.ttf", 0), (FONT_DIR / "Anton-Regular.ttf", 0)),
}
BOLD_ROLES = {"jp-black", "jp-bold", "serif-black", "serif", "display", "label"}


@lru_cache(maxsize=512)
def face(role: str, size: int) -> ImageFont.FreeTypeFont:
    """The font for a role at a logical size."""
    for path, index in FACES[role]:
        if path.exists():
            return ImageFont.truetype(str(path), size=size, index=index)
    return load_font(size, bold=role in BOLD_ROLES)


def has_bundled_fonts() -> bool:
    return (FONT_DIR / "ZenKakuGothicNew-Black.ttf").exists()
