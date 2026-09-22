from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from tiktok_poster.retention import (
    converted_index,
    expired_posts,
    expired_themes,
    purge,
    purge_posts,
    purge_superseded,
    superseded_posts,
    theme_slug,
)
from tiktok_poster.state import State

NOW = datetime(2026, 12, 1, tzinfo=timezone.utc)


def _theme(root: Path, theme: str, posts: int, with_package: bool = False) -> None:
    for number in range(1, posts + 1):
        post = root / theme / f"post_{number:02d}_INTJ"
        slides = post / "slides" if with_package else post
        slides.mkdir(parents=True, exist_ok=True)
        (slides / "slide_01.png").write_bytes(b"x" * 100)
        if with_package:
            (post / "package.json").write_text("{}", encoding="utf-8")


def _sent(state: State, theme: str, numbers: range, days_ago: int) -> None:
    for number in numbers:
        state.add(f"{theme_slug(theme)}/post_{number:02d}_INTJ", theme, "pid")
        state.records[-1].posted_at = (NOW - timedelta(days=days_ago)).isoformat()


def _dirs(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "delivery" / "phone", tmp_path / "out"


def test_a_theme_sent_long_ago_loses_its_images_but_keeps_its_copy(tmp_path: Path) -> None:
    source, output = _dirs(tmp_path)
    _theme(source, "古いネタ", 2)
    _theme(output, "古いネタ", 2, with_package=True)
    state = State()
    _sent(state, "古いネタ", range(1, 3), days_ago=90)

    themes = expired_themes(source, output, state, keep_days=60, now=NOW)
    assert [t.theme for t in themes] == ["古いネタ"]
    assert purge(source, output, themes) > 0

    assert not (source / "古いネタ").exists()
    assert not (output / "古いネタ" / "post_01_INTJ" / "slides").exists()
    # The overlap guard reads these, so they have to survive.
    assert (output / "古いネタ" / "post_01_INTJ" / "package.json").exists()


def test_a_theme_with_anything_unsent_is_left_alone(tmp_path: Path) -> None:
    source, output = _dirs(tmp_path)
    _theme(source, "途中のネタ", 3)
    state = State()
    _sent(state, "途中のネタ", range(1, 3), days_ago=90)  # post 3 never went out

    assert expired_themes(source, output, state, keep_days=60, now=NOW) == []


def test_a_recently_finished_theme_is_left_alone(tmp_path: Path) -> None:
    source, output = _dirs(tmp_path)
    _theme(source, "最近のネタ", 2)
    state = State()
    _sent(state, "最近のネタ", range(1, 2), days_ago=90)
    _sent(state, "最近のネタ", range(2, 3), days_ago=10)  # the last send decides

    assert expired_themes(source, output, state, keep_days=60, now=NOW) == []


def test_no_send_history_means_nothing_expires(tmp_path: Path) -> None:
    # A fresh clone with an empty state file must not read as "all sent".
    source, output = _dirs(tmp_path)
    _theme(source, "何かのネタ", 2)
    assert expired_themes(source, output, State(), keep_days=0, now=NOW) == []


def test_dry_run_reports_without_deleting(tmp_path: Path) -> None:
    source, output = _dirs(tmp_path)
    _theme(source, "古いネタ", 1)
    state = State()
    _sent(state, "古いネタ", range(1, 2), days_ago=90)

    themes = expired_themes(source, output, state, keep_days=60, now=NOW)
    assert purge(source, output, themes, dry_run=True) == 100
    assert (source / "古いネタ").exists()


def _fresh(source: Path, output: Path, name: str) -> None:
    handoff = source / "_posts" / name
    handoff.mkdir(parents=True, exist_ok=True)
    (handoff / "slide_01.png").write_bytes(b"x" * 100)
    slides = output / "posts" / name / "slides"
    slides.mkdir(parents=True, exist_ok=True)
    (slides / "slide_01.png").write_bytes(b"x" * 100)
    (output / "posts" / name / "post.json").write_text("{}", encoding="utf-8")


def _sent_fresh(state: State, name: str, days_ago: int) -> None:
    state.add(f"posts/{name}", name, "pid")
    state.records[-1].posted_at = (NOW - timedelta(days=days_ago)).isoformat()


def test_a_new_format_post_expires_on_its_own_and_keeps_its_post_json(tmp_path: Path) -> None:
    source, output = _dirs(tmp_path)
    _fresh(source, output, "00001-gallery")
    _fresh(source, output, "00002-manual")
    _fresh(source, output, "00003-ranking")
    state = State()
    _sent_fresh(state, "00001-gallery", days_ago=90)
    _sent_fresh(state, "00002-manual", days_ago=10)  # too recent; 00003 never sent

    posts = expired_posts(source, output, state, keep_days=60, now=NOW)
    assert [post.name for post in posts] == ["00001-gallery"]
    assert purge_posts(source, output, posts) == 200

    assert not (source / "_posts" / "00001-gallery").exists()
    assert not (output / "posts" / "00001-gallery" / "slides").exists()
    # The generator counts a day's posts by this file.
    assert (output / "posts" / "00001-gallery" / "post.json").exists()
    assert (source / "_posts" / "00002-manual").exists()
    # Already purged: nothing left to report next time.
    assert expired_posts(source, output, state, keep_days=60, now=NOW) == []


def test_the_old_drawing_of_a_redrawn_post_is_dead_weight(tmp_path: Path) -> None:
    # A redrawn post goes out in the current design, so the images the old
    # renderer left will never be sent - but the copy has to survive.
    source, output = _dirs(tmp_path)
    _theme(source, "古いネタ", 2)
    _theme(output, "古いネタ", 2, with_package=True)
    converted = {"古いネタ/post_01_INTJ": 1, "古いネタ/post_02_INTJ": 2}

    posts = superseded_posts(source, output, converted)
    assert [(post.theme, post.post) for post in posts] == [
        ("古いネタ", "post_01_INTJ"), ("古いネタ", "post_02_INTJ"),
    ]
    assert purge_superseded(source, output, posts) == 400

    assert not (source / "古いネタ").exists()
    assert not (output / "古いネタ" / "post_01_INTJ" / "slides").exists()
    assert (output / "古いネタ" / "post_01_INTJ" / "package.json").exists()
    # Nothing left to report on a second run.
    assert superseded_posts(source, output, converted) == []


def test_a_post_that_was_never_redrawn_is_left_alone(tmp_path: Path) -> None:
    source, output = _dirs(tmp_path)
    _theme(source, "まだのネタ", 1)

    assert superseded_posts(source, output, {}) == []


def test_a_missing_conversion_index_reads_as_nothing_converted(tmp_path: Path) -> None:
    assert converted_index(tmp_path) == {}
