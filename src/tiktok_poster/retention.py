"""Drop local slide images for themes that were sent long ago.

The generator writes every carousel twice on this PC - the full package under
out/ and the slides under the handoff folder - at roughly half a gigabyte a
day, and nothing removed either. docs/media is already pruned by sync; this is
the same idea for the two local copies.

The unit is the theme, not the post. A theme is only touched once every post of
it has been sent and the last send is older than the keep window, so nothing
still queued can lose its images, and ready_themes never sees a theme shrink
below its publishing threshold.

Under out/ only the slides go. package.json, the caption and the script stay:
the generator's overlap guard compares new copy against every package.json it
can find, and deleting those would let a topic from months ago come back.

Posts in the new formats are complete on their own, so they expire one by one:
the handoff folder goes, and under out/posts only the slides, because the
generator counts a date's posts by the post.json it leaves there.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tiktok_poster.state import State

POST_DIR_RE = re.compile(r"^post_\d+_[A-Z]{4}$")


def theme_slug(theme: str) -> str:
    return hashlib.sha1(theme.encode("utf-8")).hexdigest()[:10]


def _sent_at(state: State) -> dict[str, datetime]:
    stamps: dict[str, datetime] = {}
    for record in state.records:
        try:
            stamp = datetime.fromisoformat(record.posted_at)
        except ValueError:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        stamps[record.key] = stamp
    return stamps


def _post_dirs(theme_dir: Path) -> list[Path]:
    if not theme_dir.is_dir():
        return []
    return [child for child in theme_dir.iterdir() if child.is_dir() and POST_DIR_RE.match(child.name)]


@dataclass(frozen=True, slots=True)
class ExpiredTheme:
    theme: str
    last_sent: datetime
    posts: int


def expired_themes(
    source_dir: Path,
    output_dir: Path,
    state: State,
    keep_days: int,
    now: datetime | None = None,
) -> list[ExpiredTheme]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=keep_days)
    sent = _sent_at(state)

    themes: set[str] = set()
    for root in (source_dir, output_dir):
        if root.is_dir():
            themes.update(child.name for child in root.iterdir() if child.is_dir())

    expired: list[ExpiredTheme] = []
    for theme in sorted(themes):
        names = {post.name for root in (source_dir, output_dir) for post in _post_dirs(root / theme)}
        if not names:
            continue
        slug = theme_slug(theme)
        stamps = [sent.get(f"{slug}/{name}") for name in names]
        if any(stamp is None for stamp in stamps):
            continue
        last = max(stamps)
        if last <= cutoff:
            expired.append(ExpiredTheme(theme, last, len(names)))
    return expired


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())


def purge(source_dir: Path, output_dir: Path, themes: list[ExpiredTheme], dry_run: bool = False) -> int:
    """Remove the images for these themes. Returns the bytes freed."""
    freed = 0
    for expired in themes:
        handoff = source_dir / expired.theme
        if handoff.is_dir():
            freed += _size(handoff)
            if not dry_run:
                shutil.rmtree(handoff)
        for post in _post_dirs(output_dir / expired.theme):
            slides = post / "slides"
            if slides.is_dir():
                freed += _size(slides)
                if not dry_run:
                    shutil.rmtree(slides)
    return freed


FRESH_HANDOFF = "_posts"
FRESH_OUTPUT = "posts"
FRESH_PREFIX = "posts"


@dataclass(frozen=True, slots=True)
class ExpiredPost:
    name: str
    last_sent: datetime


def expired_posts(
    source_dir: Path,
    output_dir: Path,
    state: State,
    keep_days: int,
    now: datetime | None = None,
) -> list[ExpiredPost]:
    """New-format posts sent more than keep_days ago that still have images."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=keep_days)
    sent = _sent_at(state)
    names: set[str] = set()
    for root in (source_dir / FRESH_HANDOFF, output_dir / FRESH_OUTPUT):
        if root.is_dir():
            names.update(child.name for child in root.iterdir() if child.is_dir())
    expired: list[ExpiredPost] = []
    for name in sorted(names):
        stamp = sent.get(f"{FRESH_PREFIX}/{name}")
        if stamp is None or stamp > cutoff:
            continue
        if (source_dir / FRESH_HANDOFF / name).is_dir() or (output_dir / FRESH_OUTPUT / name / "slides").is_dir():
            expired.append(ExpiredPost(name, stamp))
    return expired


def purge_posts(source_dir: Path, output_dir: Path, posts: list[ExpiredPost], dry_run: bool = False) -> int:
    """Remove the images for these posts. Returns the bytes freed."""
    freed = 0
    for post in posts:
        for path in (source_dir / FRESH_HANDOFF / post.name, output_dir / FRESH_OUTPUT / post.name / "slides"):
            if path.is_dir():
                freed += _size(path)
                if not dry_run:
                    shutil.rmtree(path)
    return freed
