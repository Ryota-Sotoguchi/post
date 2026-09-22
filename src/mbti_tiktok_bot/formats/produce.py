"""Write, draw and hand off the day's posts.

A slot does not make a fixed number of posts. It makes however many the day
should have by now - POSTS_PER_DAY spread evenly over the day's slots - less
what is already on disk for that date. A rerun, or the logon catch-up after the
PC was off, therefore draws exactly what is missing and nothing twice.

Each post lives in two places, like the themed carousels before it:

    out/posts/<key>/                 post.json, caption.txt, slides/
    <PHONE_EXPORT_DIR>/_posts/<key>/ slide_NN.png and post.json for the poster

post.json is written last in both, so its presence means the post is complete.
"""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime
from pathlib import Path

from mbti_tiktok_bot.config import AppConfig
from mbti_tiktok_bot.design.engine import render_post
from mbti_tiktok_bot.formats import planner, writer
from mbti_tiktok_bot.formats.model import Post

POSTS_DIR = "posts"
HANDOFF_DIR = "_posts"
META = "post.json"


def posts_root(config: AppConfig) -> Path:
    return config.output_dir / POSTS_DIR


def handoff_root(config: AppConfig) -> Path:
    return config.phone_export_dir / HANDOFF_DIR


def _read_meta(folder: Path) -> dict | None:
    try:
        data = json.loads((folder / META).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def produced_on(config: AppConfig, target: date) -> list[Path]:
    """The finished posts written for a date."""
    root = posts_root(config)
    if not root.is_dir():
        return []
    stamp = target.isoformat()
    return [
        folder
        for folder in sorted(root.iterdir())
        if folder.is_dir() and (_read_meta(folder) or {}).get("post_date") == stamp
    ]


def due_by(target: date, times: list[str], now: datetime, per_day: int) -> int:
    """How many posts the date should have once every slot up to now has run."""
    if not times:
        return per_day
    if target < now.date():
        passed = len(times)
    elif target > now.date():
        passed = 0
    else:
        passed = sum(1 for slot in times if now >= datetime.strptime(f"{target.isoformat()} {slot}", "%Y-%m-%d %H:%M"))
    return per_day * passed // len(times)


def _highest_seq(config: AppConfig) -> int:
    highest = 0
    root = posts_root(config)
    if root.is_dir():
        for folder in root.iterdir():
            head = folder.name.partition("-")[0]
            if folder.is_dir() and head.isdigit():
                highest = max(highest, int(head))
    return highest


def _export(config: AppConfig, post: Post, slides: list[Path]) -> Path:
    # Imported here: phone_export pulls in the legacy pipeline, which is heavy
    # and not otherwise needed to draw a post.
    from mbti_tiktok_bot.phone_export import _write_phone_safe_png

    destination = handoff_root(config) / post.key
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    size = (config.video_width, config.video_height)
    for slide in slides:
        _write_phone_safe_png(slide, destination / slide.name, size)
    meta = {
        "key": post.key,
        "format": post.format,
        "post_date": post.post_date,
        "title": post.title,
        "description": post.description,
        "filler": post.filler,
    }
    (destination / META).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def make_post(config: AppConfig, post: Post, keep_source: bool = True) -> Path:
    """Render one written post and hand it to the poster. Returns its out/ folder.

    keep_source=False drops the out/ copy of the images once the handoff has
    them. Converted back-catalogue posts may sit for weeks before they are
    needed, and two copies of a few thousand slides is gigabytes; post.json
    stays, so any of them can be drawn again.
    """
    folder = posts_root(config) / post.key
    (folder / META).unlink(missing_ok=True)
    render_post(post, config, folder / "slides")
    slides = sorted((folder / "slides").glob("slide_*.png"))
    (folder / "caption.txt").write_text(post.description + "\n", encoding="utf-8")
    _export(config, post, slides)
    if not keep_source:
        shutil.rmtree(folder / "slides", ignore_errors=True)
    (folder / META).write_text(writer.dumps(post), encoding="utf-8")
    return folder


def produce(config: AppConfig, target: date, count: int) -> list[Path]:
    """Write and draw the next `count` posts in the pattern.

    State is saved after every post, so a failure part way keeps what was
    already made and the next run continues from the post that failed.
    """
    state = planner.load_state(config)
    # A lost or stale state file must not reuse a number: the key is what the
    # poster remembers a post by, and a reused one would count as already sent.
    state.next_seq = max(state.next_seq, _highest_seq(config) + 1)
    made: list[Path] = []
    for _ in range(count):
        spec = planner.next_spec(config, state)
        post = planner.write(config, spec, target)
        folder = make_post(config, post)
        planner.advance(state, spec)
        planner.save_state(config, state)
        made.append(folder)
        print(f"Made {post.key} [{post.source}] {post.title} ({len(post.cards)} slides)")
    return made
