from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SLIDE_RE = re.compile(r"^slide_(\d+)\.(png|jpg|jpeg|webp)$", re.IGNORECASE)

# TikTok caps a carousel at 35 images.
MAX_SLIDES = 35

# The generator hands every post off here, one folder per post, each titled and
# captioned by the generator itself. The themed carousels that used to sit
# beside it - one topic drawn across sixteen types, over several days - are no
# longer made; what was left of them was redrawn in the current design and now
# arrives through this folder too, marked as filler.
FRESH_DIR = "_posts"
FRESH_PREFIX = "posts"
FRESH_META = "post.json"


@dataclass(frozen=True, slots=True)
class FreshPost:
    """A post in one of the generator's formats: complete on its own.

    Unlike a themed carousel it needs no theme to be drawn to the end before it
    may go out, and its title and caption come from the generator.
    """

    name: str
    format: str
    title: str
    description: str
    source_dir: Path
    slides: tuple[Path, ...]
    filler: bool = False

    @property
    def key(self) -> str:
        return f"{FRESH_PREFIX}/{self.name}"

    @property
    def theme(self) -> str:
        return self.format


def is_fresh(key: str) -> bool:
    return key.startswith(f"{FRESH_PREFIX}/")


def _slides_in(post_dir: Path) -> tuple[Path, ...]:
    numbered: list[tuple[int, Path]] = []
    for child in post_dir.iterdir():
        match = SLIDE_RE.match(child.name)
        if match and child.is_file():
            numbered.append((int(match.group(1)), child))
    numbered.sort()
    return tuple(path for _, path in numbered)


def scan_fresh(source_dir: Path) -> list[FreshPost]:
    """Every finished post in the generator's formats, oldest first.

    Folder names start with the post's number, so name order is the order they
    were made in. A folder without its post.json is still being written.
    """
    root = source_dir / FRESH_DIR
    if not root.is_dir():
        return []
    posts: list[FreshPost] = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            meta = json.loads((folder / FRESH_META).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        slides = _slides_in(folder)
        if not slides or not isinstance(meta, dict) or not meta.get("title"):
            continue
        posts.append(
            FreshPost(
                name=folder.name,
                format=str(meta.get("format", "")),
                title=str(meta["title"]),
                description=str(meta.get("description", "")),
                source_dir=folder,
                slides=slides[:MAX_SLIDES],
                filler=bool(meta.get("filler", False)),
            )
        )
    return posts


MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True, slots=True)
class Upload:
    """One carousel, resolved to the URLs TikTok will pull.

    The source images are generated on a PC and are gitignored, so a CI runner
    only ever sees what was committed under docs/media. The posting step works
    from this rather than from the source folders: everything it needs is the
    title, the caption and URLs that are already published.
    """

    key: str
    theme: str
    title: str
    description: str
    images: tuple[str, ...]
    filler: bool = False


def manifest_path(publish_dir: Path) -> Path:
    return publish_dir / MANIFEST_NAME


def write_manifest(path: Path, uploads: list[Upload], base_url: str) -> Path:
    """Write the manifest, unless the carousels in it are unchanged.

    sync runs at every scheduled slot and at logon, and most of those runs find
    nothing new. Stamping a fresh generated_at regardless turned each of them
    into a commit, a push and a Pages build that changed one line. Leaving the
    file alone also keeps generated_at meaning "when the carousel list last
    changed", which is what the staleness warning in status is really asking.
    """
    posts = [
        {
            "key": upload.key,
            "theme": upload.theme,
            "title": upload.title,
            "description": upload.description,
            "images": list(upload.images),
            **({"filler": True} if upload.filler else {}),
        }
        for upload in uploads
    ]
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        existing = None
    if isinstance(existing, dict) and existing.get("base_url") == base_url and existing.get("posts") == posts:
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "base_url": base_url,
                "posts": posts,
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
            filler=bool(entry.get("filler", False)),
        )
        for entry in payload.get("posts", [])
    ]


def send_order(uploads: list[Upload], posted: list[str]) -> list[Upload]:
    """What to send next: the day's own posts in the order they were made, then filler.

    Filler is the back catalogue, redrawn in the current design. Ten posts are
    written a day and ten are sent, so filler only comes up when a day's
    writing did not happen - the PC was off, or the API was down - which is
    exactly what it is kept for.
    """
    already = set(posted)
    waiting = [upload for upload in uploads if upload.key not in already]
    return sorted(waiting, key=lambda upload: (upload.filler, upload.key))
