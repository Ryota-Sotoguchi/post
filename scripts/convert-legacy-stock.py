"""Redraw every unsent themed carousel in the current design.

The copy is reused as written; only the drawing changes. Converted posts are
filler: they go out after everything freshly written. Safe to stop and rerun -
the L number a package was given is remembered, and anything already converted
is skipped.

    scripts/convert-legacy-stock.py --dry-run     # what would be converted
    scripts/convert-legacy-stock.py --limit 10    # a batch
    scripts/convert-legacy-stock.py               # the lot (about 30 minutes)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mbti_tiktok_bot.config import load_config  # noqa: E402
from mbti_tiktok_bot.formats import legacy  # noqa: E402
from mbti_tiktok_bot.formats.produce import handoff_root, make_post, posts_root  # noqa: E402

INDEX = "legacy_converted.json"


def load_index(config) -> dict[str, int]:
    path = config.state_dir / INDEX
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(key): int(value) for key, value in data.items()}


def save_index(config, index: dict[str, int]) -> None:
    path = config.state_dir / INDEX
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def sent_keys(config) -> set[str]:
    """What the poster has already sent, read straight from its state file."""
    path = config.project_root / "state" / "posted.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {str(record.get("key", "")) for record in data.get("records", [])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="Convert at most this many")
    parser.add_argument("--dry-run", action="store_true", help="List what would be converted")
    parser.add_argument("--redraw", action="store_true", help="Draw again even if it was converted before")
    args = parser.parse_args()

    config = load_config(Path.cwd())
    index = load_index(config)
    pending: list[tuple[Path, int]] = []
    next_number = max(index.values(), default=0) + 1

    # Each old theme is a series: its posts share a look, a palette and an
    # arrangement, and they go out one after another.
    themes: dict[str, int] = {}
    positions: dict[str, int] = {}
    for package in legacy.packages(config, sent_keys(config)):
        theme = package.parent.parent.name
        name = f"{theme}/{package.parent.name}"
        number = index.get(name)
        if number is None:
            number, next_number = next_number, next_number + 1
            index[name] = number
        series_index = themes.setdefault(theme, len(themes) + 1)
        positions[theme] = positions.get(theme, 0) + 1
        pending.append((package, number, series_index, positions[theme]))

    done = [item for item in pending if (handoff_root(config) / f"L{item[1]:04d}-manual" / "post.json").exists()]
    todo = pending if args.redraw else [item for item in pending if item not in done]
    print(f"{len(pending)} unsent themed carousel(s); {len(done)} already converted, {len(todo)} to draw")
    if args.limit:
        todo = todo[: args.limit]

    if args.dry_run:
        for package, number, _, _ in todo[:20]:
            print(f"  L{number:04d} <- {package.parent.parent.name}/{package.parent.name}")
        if len(todo) > 20:
            print(f"  ... and {len(todo) - 20} more")
        return 0

    save_index(config, index)
    started = time.perf_counter()
    for step, (package, number, series_index, position) in enumerate(todo, start=1):
        post = legacy.convert(legacy.load(package), number, series_index, position)
        make_post(config, post, keep_source=False)
        elapsed = time.perf_counter() - started
        print(f"[{step}/{len(todo)}] {post.key} {post.title} ({len(post.cards)} slides) "
              f"{elapsed / step:.1f}s each", flush=True)
    print(f"done in {(time.perf_counter() - started) / 60:.1f} min")
    print(f"out/{posts_root(config).name}, handoff {handoff_root(config)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
