"""Redraw the back catalogue in the current design.

Two hundred and twenty-three themed carousels were written before the design
was rebuilt, and none of them had been sent. The copy is fine - what dated them
was the drawing. A themed post is one type, a hook and five to eight
title/body beats, which is the shape the `section` layout already takes, so
each one converts into a post of the current kind without rewriting a word.

Two things the old drawing lost come back for free: the hook, which was written
for every post and never appeared on a slide, and the traits, which were
pasted into prose as `場を明るくする / 愛嬌がある` and are now chips.

Converted posts are filler: numbered in their own L series and sent only when
nothing freshly written is waiting.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from mbti_tiktok_bot.catalog import TYPE_DATA
from mbti_tiktok_bot.config import AppConfig
from mbti_tiktok_bot.formats.model import Card, Post

# Folders under out/ that are not a themed series.
SKIP = ("posts", "editorial_ikemen_bijo_20260703")
CHIP_LIMIT = 10
BODY_LIMIT = 90
# The longest heading in the catalogue is 18 characters, and the section layout
# shrinks a heading to fit rather than cutting it, so nothing needs an ellipsis.
HEADING_LIMIT = 18


def theme_slug(theme: str) -> str:
    """The published slug the poster used for a themed carousel, to read its send state."""
    return hashlib.sha1(theme.encode("utf-8")).hexdigest()[:10]


def _clip(text: object, limit: int) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


# The two separators the old copy used for a list: a spaced ASCII slash and a
# fullwidth one. Not "・", which it also used inside ordinary prose
# (世話焼き・励ます人が反応薄め).
LIST_SEPARATOR = re.compile(r"\s/\s|／")


def split_chips(body: str) -> tuple[tuple[str, ...], str]:
    """Lift a list of traits out of the front of a body and return it as chips.

    The old planner joined a type's traits and pasted them in front of the
    sentence that mattered - 先を読む / 感情より設計 / 必要な人には一途。雑談の… -
    which is a list pretending to be prose. It is the same information the
    current design sets as chips, so it goes back to being a list.
    """
    head, _, rest = body.partition("。")
    segments = [segment.strip() for segment in LIST_SEPARATOR.split(head)]
    if len(segments) < 2 or not rest.strip() or any(not (0 < len(segment) <= 14) for segment in segments):
        return (), body
    return tuple(segments), rest.strip()


# A stray space between two Japanese characters is a typo in the old copy, and
# the renderer has no reason to keep it.
STRAY_SPACE = re.compile(r"(?<=[^\x00-\x7f]) (?=[^\x00-\x7f])")


def packages(config: AppConfig, posted: set[str]) -> list[Path]:
    """Every themed package that was never sent, in the order it was written."""
    found: list[Path] = []
    root = config.output_dir
    if not root.is_dir():
        return found
    for theme_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        if theme_dir.name in SKIP or theme_dir.name.startswith("_"):
            continue
        slug = theme_slug(theme_dir.name)
        for post_dir in sorted(theme_dir.glob("post_*")):
            package = post_dir / "package.json"
            if package.exists() and f"{slug}/{post_dir.name}" not in posted:
                found.append(package)
    return found


def convert(package: dict, seq: int) -> Post:
    """One legacy package as a post of the current kind."""
    mbti = str(package["mbti_type"])
    title = str(package["title"])
    hook = _clip(package.get("hook"), 60)
    scenes = [scene for scene in package.get("scenes", []) if scene.get("title")]
    # The package never carried the traits as data - the planner pasted them
    # into prose - so they come from the type catalogue the prose was built from.
    chips = tuple(_clip(trait, CHIP_LIMIT) for trait in TYPE_DATA[mbti]["traits"][:4])

    cards = [Card("cover", title=title, body=hook, label=str(package.get("theme") or "MBTI"), types=(mbti,))]
    for index, scene in enumerate(scenes, start=1):
        own_chips, body = split_chips(STRAY_SPACE.sub("", " ".join(str(scene.get("body", "")).split())))
        # A list that runs into the middle of a sentence stays prose, with the
        # separator the sentence should have had.
        body = LIST_SEPARATOR.sub("、", body)
        cards.append(Card(
            "section",
            title=_clip(scene["title"], HEADING_LIMIT),
            body=_clip(body, BODY_LIMIT),
            label=title,
            number=index,
            total=len(scenes),
            chips=own_chips or (chips if index == 1 else ()),
            types=(mbti,),
        ))
    cards.append(Card("closer", title=f"周りの{mbti}に送ってみて",
                      body="当てはまったら保存。気になる人と答え合わせしてみて。", types=(mbti,)))

    return Post(
        seq=seq,
        format="manual",
        post_date=str(package.get("post_date", "")),
        title=title,
        hook=hook,
        focus=mbti,
        angle=str(package.get("theme", "")),
        hashtags=tuple(str(tag) for tag in package.get("hashtags", ())),
        cards=cards,
        source="legacy",
        filler=True,
    )


def load(package_path: Path) -> dict:
    return json.loads(package_path.read_text(encoding="utf-8"))
