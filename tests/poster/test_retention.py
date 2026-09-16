from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from tiktok_poster.retention import expired_themes, purge, theme_slug
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
