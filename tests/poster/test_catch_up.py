from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from tiktok_poster.cli import _run_catch_up
from tiktok_poster.config import Config
from tiktok_poster.state import load_state, save_state


def _args(dry_run: bool = False) -> argparse.Namespace:
    return argparse.Namespace(dry_run=dry_run)


def _approved_for(config: Config, hours: float) -> None:
    marker = config.publish_dir.parent / "authorized.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    expires = datetime.now(timezone.utc) + timedelta(hours=hours)
    marker.write_text(json.dumps({"expires_at": expires.isoformat()}), encoding="utf-8")


def _sent_today(config: Config, count: int) -> None:
    state = load_state(config.state_path)
    for number in range(count):
        state.add(f"slug/post_{number:02d}_INTJ", "title", "pid")
    save_state(config.state_path, state)


def _catch_up(config: Config, **kwargs):
    with patch("tiktok_poster.cli.load_config", return_value=config), \
         patch("tiktok_poster.cli.subprocess.run") as run, \
         patch("tiktok_poster.cli.shutil.which", return_value="powershell.exe"):
        run.return_value.returncode = 0
        code = _run_catch_up(_args(**kwargs))
    return code, run


def _dispatched(run) -> bool:
    return any(call.args[0][:3] == ["gh", "workflow", "run"] for call in run.call_args_list)


def _opened_browser(run) -> bool:
    return any(call.args[0][0] == "powershell.exe" for call in run.call_args_list)


def test_starts_the_posting_workflow_when_today_is_short(config: Config) -> None:
    _approved_for(config, hours=10)
    _sent_today(config, 2)

    code, run = _catch_up(config)
    assert code == 0
    assert _dispatched(run)
    assert not _opened_browser(run)


def test_does_nothing_once_the_day_is_complete(config: Config) -> None:
    _approved_for(config, hours=10)
    _sent_today(config, config.posts_per_day)

    code, run = _catch_up(config)
    assert code == 0
    assert not run.called


def test_asks_for_approval_instead_of_starting_a_run_that_would_fail(config: Config) -> None:
    # The sandbox app cannot refresh its token, so a run without today's
    # approval dies at the send step. Opening the approval page is the one
    # thing that actually unblocks it.
    _approved_for(config, hours=-3)

    code, run = _catch_up(config)
    assert code == 0
    assert not _dispatched(run)
    assert _opened_browser(run)


def test_a_token_about_to_expire_counts_as_missing(config: Config) -> None:
    _approved_for(config, hours=0.2)

    _, run = _catch_up(config)
    assert not _dispatched(run)


def test_opens_the_approval_page_at_most_once_a_day(config: Config) -> None:
    # The task fires four times a day plus at logon; one prompt is enough.
    _approved_for(config, hours=-3)

    _, first = _catch_up(config)
    _, second = _catch_up(config)
    assert _opened_browser(first)
    assert not _opened_browser(second)


def test_dry_run_acts_on_nothing(config: Config) -> None:
    _approved_for(config, hours=10)
    _, run = _catch_up(config, dry_run=True)
    assert not run.called
