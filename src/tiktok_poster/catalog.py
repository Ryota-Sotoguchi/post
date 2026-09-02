from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

POST_DIR_RE = re.compile(r"^post_(\d+)_([A-Z]{4})$")
SLIDE_RE = re.compile(r"^slide_(\d+)\.(png|jpg|jpeg|webp)$", re.IGNORECASE)

# TikTok caps a carousel at 35 images.
MAX_SLIDES = 35
FIXED_HASHTAGS = ("#恋愛", "#MBTI")


@dataclass(frozen=True, slots=True)
class Post:
    theme: str
    mbti: str
    order: int
    source_dir: Path
    slides: tuple[Path, ...]

    @property
    def theme_slug(self) -> str:
        """ASCII stand-in for the Japanese theme name.

        Theme names are Japanese, and a PULL_FROM_URL target must be a plain
        https URL that TikTok can fetch without redirects, so the path stays
        ASCII rather than relying on percent-encoding round-tripping.
        """
        return hashlib.sha1(self.theme.encode("utf-8")).hexdigest()[:10]

    @property
    def key(self) -> str:
        return f"{self.theme_slug}/{self.source_dir.name}"

    @property
    def title(self) -> str:
        # Theme names are written to follow the type: "が本命だけに見せる…"
        # reads as "INTJが本命だけに見せる…".
        return f"{self.mbti}{self.theme}"

    @property
    def hashtags(self) -> tuple[str, ...]:
        return (*FIXED_HASHTAGS, f"#{self.mbti}")

    @property
    def description(self) -> str:
        return " ".join(self.hashtags)


def _slides_in(post_dir: Path) -> tuple[Path, ...]:
    numbered: list[tuple[int, Path]] = []
    for child in post_dir.iterdir():
        match = SLIDE_RE.match(child.name)
        if match and child.is_file():
            numbered.append((int(match.group(1)), child))
    numbered.sort()
    return tuple(path for _, path in numbered)


def scan(source_dir: Path) -> list[Post]:
    """Every complete carousel under source_dir, in posting order."""
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    posts: list[Post] = []
    for theme_dir in sorted(p for p in source_dir.iterdir() if p.is_dir()):
        for post_dir in sorted(p for p in theme_dir.iterdir() if p.is_dir()):
            match = POST_DIR_RE.match(post_dir.name)
            if match is None:
                continue
            slides = _slides_in(post_dir)
            if not slides:
                continue
            posts.append(
                Post(
                    theme=theme_dir.name,
                    mbti=match.group(2),
                    order=int(match.group(1)),
                    source_dir=post_dir,
                    slides=slides[:MAX_SLIDES],
                )
            )
    posts.sort(key=lambda post: (post.theme, post.order))
    return posts
