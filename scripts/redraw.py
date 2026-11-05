"""Draw posts again from the copy that is already on disk.

`out/posts/<key>/post.json` holds everything a post says; the images are just
that copy drawn. So the images are disposable and this script remakes them:

    .venv-linux/bin/python scripts/redraw.py --dry-run         # what is missing its images
    .venv-linux/bin/python scripts/redraw.py --limit 10        # a batch (about 12s a post)
    .venv-linux/bin/python scripts/redraw.py                   # everything unsent that has no images
    .venv-linux/bin/python scripts/redraw.py --force           # draw again even if the images exist
    .venv-linux/bin/python scripts/redraw.py --sent            # include posts already sent

Two jobs:

  Moving to another PC. `out/` and `delivery/` are gitignored, so a fresh
  checkout has the post.json files only if they were copied across - 2MB, not
  12GB. Copy `out/posts/*/post.json` and `state/`, then run this to rebuild the
  backlog's images.

  Changing the design. The copy stays as written and only the drawing changes,
  so the unsent backlog can be brought onto a new look without spending the LLM
  again.

Sent posts are left alone by default: they are published, and redrawing them
would only churn `docs/media`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mbti_tiktok_bot.config import load_config  # noqa: E402
from mbti_tiktok_bot.formats.model import Post  # noqa: E402
from mbti_tiktok_bot.formats.produce import META, handoff_root, make_post, posts_root  # noqa: E402

POSTED = "posted.json"


def sent_keys(config) -> set[str]:
    try:
        data = json.loads((config.state_dir / POSTED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    records = data.get("records") if isinstance(data, dict) else None
    keys = set()
    for record in records or []:
        key = (record or {}).get("key") if isinstance(record, dict) else None
        if key:
            keys.add(str(key).split("/")[-1])
    return keys


def has_images(config, key: str) -> bool:
    """True when the poster's copy of the slides is there and whole.

    The handoff folder is what gets published, so that is what counts; the
    out/ copy is dropped for filler to save the space.
    """
    folder = handoff_root(config) / key
    return (folder / META).is_file() and any(folder.glob("slide_*.png"))


def load_post(folder: Path) -> Post | None:
    try:
        data = json.loads((folder / META).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or "cards" not in data:
        return None  # a handoff stub, not a written post
    try:
        return Post.from_dict(data)
    except (KeyError, TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="Draw at most this many")
    parser.add_argument("--dry-run", action="store_true", help="List what would be drawn")
    parser.add_argument("--force", action="store_true", help="Draw again even if the images are there")
    parser.add_argument("--sent", action="store_true", help="Include posts already sent to TikTok")
    parser.add_argument("--only", help="Draw just this key, e.g. L0007-manual")
    args = parser.parse_args()

    config = load_config()
    root = posts_root(config)
    if not root.is_dir():
        print(f"No posts under {root}")
        return 1

    published = set() if args.sent else sent_keys(config)
    todo: list[Post] = []
    unreadable = 0
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or (args.only and folder.name != args.only):
            continue
        if folder.name in published:
            continue
        if not args.force and has_images(config, folder.name):
            continue
        post = load_post(folder)
        if post is None:
            unreadable += 1
            continue
        todo.append(post)

    if unreadable:
        print(f"{unreadable} folder(s) have no readable post.json; their copy is gone and they cannot be drawn")
    print(f"{len(todo)} post(s) to draw" + (f", doing {args.limit}" if args.limit else ""))
    todo = todo[: args.limit] if args.limit else todo
    if args.dry_run:
        for post in todo:
            print(f"  {post.key} {post.title} ({len(post.cards)} slides)")
        return 0

    for index, post in enumerate(todo, start=1):
        started = time.monotonic()
        make_post(config, post, keep_source=not post.filler)
        spent = time.monotonic() - started
        print(f"[{index}/{len(todo)}] {post.key} {post.title} ({len(post.cards)} slides) {spent:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
