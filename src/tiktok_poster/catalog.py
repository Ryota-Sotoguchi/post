from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

POST_DIR_RE = re.compile(r"^post_(\d+)_([A-Z]{4})$")
SLIDE_RE = re.compile(r"^slide_(\d+)\.(png|jpg|jpeg|webp)$", re.IGNORECASE)

# TikTok caps a carousel at 35 images.
MAX_SLIDES = 35
FIXED_HASHTAGS = ("#恋愛", "#MBTI")

# A theme is drawn once per MBTI type, over several days rather than in one go.
# Publishing one mid-draw put four of its sixteen carousels in the queue and
# sent the poster on to the next theme, so half a theme is the least that may
# be published and the rest arrives as the same theme's continuation.
THEME_SIZE = 16
THEME_MIN_POSTS = 8


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


def ready_themes(
    posts: list[Post], minimum: int = THEME_MIN_POSTS
) -> tuple[list[Post], dict[str, int]]:
    """Split the scan into what may be published and the themes still too thin.

    Returns the publishable posts and the themes held back, each mapped to how
    many of it have been drawn so far.
    """
    drawn = Counter(post.theme for post in posts)
    held = {theme: count for theme, count in drawn.items() if count < minimum}
    return [post for post in posts if post.theme not in held], held


MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True, slots=True)
class Upload:
    """One carousel, resolved to the URLs TikTok will pull.

    The source images live on a personal OneDrive that CI cannot reach, so the
    posting step works from this instead of from `scan`: everything it needs is
    the title, the hashtags and URLs that are already published.
    """

    key: str
    theme: str
    title: str
    description: str
    images: tuple[str, ...]

    @property
    def slot(self) -> int:
        """Which of the theme's MBTI slots this fills, or 0 if the key is odd."""
        match = POST_DIR_RE.match(self.key.partition("/")[2])
        return int(match.group(1)) if match else 0


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
                        "theme": upload.theme,
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


def manifest_generated_at(path: Path) -> str | None:
    """When the manifest was last written, for spotting a sync that stopped running."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    stamp = payload.get("generated_at")
    return str(stamp) if stamp else None


def load_manifest(path: Path) -> list[Upload]:
    if not path.exists():
        raise FileNotFoundError(
            f"No manifest at {path}. Run `tiktok-poster sync` on the machine that has the source images."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        Upload(
            key=str(entry["key"]),
            theme=str(entry.get("theme", "")),
            title=str(entry["title"]),
            description=str(entry["description"]),
            images=tuple(str(url) for url in entry["images"]),
        )
        for entry in payload.get("posts", [])
    ]


def send_order(
    uploads: list[Upload], posted: list[str], size: int = THEME_SIZE
) -> tuple[list[Upload], tuple[str, int] | None]:
    """What to send next, strictly in order, and the slot the queue waits on.

    `posted` is the keys already sent, in the order they went out, so the order
    a theme was started in is the order it is finished in.

    A theme is walked slot by slot and the whole queue stops at the first slot
    that has not been published yet: skipping ahead to the next type - or worse,
    to the next theme - is what put four carousels of one theme in the drafts
    and then moved on, which is the gap this exists to prevent. The queue picks
    up again by itself once `sync` publishes the missing slot.
    """
    published: dict[str, dict[int, Upload]] = {}
    for upload in uploads:
        theme, _, _ = upload.key.partition("/")
        if upload.slot:
            published.setdefault(theme, {})[upload.slot] = upload

    # A slot already in the drafts is never waited on, even if its images have
    # since left the manifest, so a retired theme cannot block the queue.
    sent: dict[str, set[int]] = {}
    started: dict[str, int] = {}
    for key in posted:
        theme, _, name = key.partition("/")
        started.setdefault(theme, len(started))
        match = POST_DIR_RE.match(name)
        if match:
            sent.setdefault(theme, set()).add(int(match.group(1)))

    untouched = len(started)
    manifest_order = {theme: index for index, theme in enumerate(published)}
    themes = sorted(published, key=lambda theme: (started.get(theme, untouched), manifest_order[theme]))

    queue: list[Upload] = []
    for theme in themes:
        slots, done = published[theme], sent.get(theme, set())
        for slot in range(1, size + 1):
            if slot in done:
                continue
            upload = slots.get(slot)
            if upload is None:
                return queue, (theme, slot)
            queue.append(upload)
    return queue, None
