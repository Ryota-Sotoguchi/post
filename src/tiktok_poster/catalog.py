from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
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


MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True, slots=True)
class Upload:
    """One carousel, resolved to the URLs TikTok will pull.

    The source images live on a personal OneDrive that CI cannot reach, so the
    posting step works from this instead of from `scan`: everything it needs is
    the title, the hashtags and URLs that are already published.
    """

    key: str
    title: str
    description: str
    images: tuple[str, ...]


def manifest_path(publish_dir: Path) -> Path:
    return publish_dir / MANIFEST_NAME


def write_manifest(path: Path, uploads: list[Upload], base_url: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "base_url": base_url,
                "posts": [
                    {
                        "key": upload.key,
                        "title": upload.title,
                        "description": upload.description,
                        "images": list(upload.images),
                    }
                    for upload in uploads
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def load_manifest(path: Path) -> list[Upload]:
    if not path.exists():
        raise FileNotFoundError(
            f"No manifest at {path}. Run `tiktok-poster sync` on the machine that has the source images."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        Upload(
            key=str(entry["key"]),
            title=str(entry["title"]),
            description=str(entry["description"]),
            images=tuple(str(url) for url in entry["images"]),
        )
        for entry in payload.get("posts", [])
    ]
