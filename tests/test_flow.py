from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tiktok_poster.catalog import scan
from tiktok_poster.cli import _run_post
from tiktok_poster.config import Config
from tiktok_poster.media import post_publish_dir
from tiktok_poster.pages import PagesError, wait_until_live
from tiktok_poster.state import load_state, save_state
from tiktok_poster.tiktok import Tokens, save_tokens


class FakeHead:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def _args(count=None, dry_run=False) -> argparse.Namespace:
    return argparse.Namespace(count=count, dry_run=dry_run)


def _authorize(config: Config) -> None:
    expiry = datetime.now(timezone.utc) + timedelta(hours=5)
    save_tokens(config, Tokens("access-1", "refresh-1", expiry.isoformat(timespec="seconds")))


def test_wait_until_live_gives_up_rather_than_sending_a_dead_url() -> None:
    # A 404 here would make TikTok fail the pull asynchronously, long after the call.
    with patch("tiktok_poster.pages.requests.head", return_value=FakeHead(404)):
        with pytest.raises(PagesError):
            wait_until_live(["https://example.com/a.jpg"], attempts=2, delay=0)


def test_wait_until_live_returns_once_pages_serves() -> None:
    with patch("tiktok_poster.pages.requests.head", return_value=FakeHead(200)):
        wait_until_live(["https://example.com/a.jpg"], attempts=1, delay=0)


def test_post_sends_a_day_worth_and_records_each(config: Config) -> None:
    _authorize(config)
    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.push", return_value=True
    ), patch("tiktok_poster.cli.pages.wait_until_live"), patch(
        "tiktok_poster.cli.tiktok.send_to_drafts", side_effect=["id-1", "id-2", "id-3", "id-4"]
    ) as send_mock:
        assert _run_post(_args()) == 0

    # Only four carousels exist in the fixture, so the day's batch is capped by stock.
    assert send_mock.call_count == 4
    assert len(load_state(config.state_path).records) == 4


def test_post_does_not_resend_what_is_already_recorded(config: Config) -> None:
    _authorize(config)
    state = load_state(config.state_path)
    state.add(scan(config.source_dir)[0].key, "already", "id-0")
    save_state(config.state_path, state)

    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.push", return_value=True
    ), patch("tiktok_poster.cli.pages.wait_until_live"), patch(
        "tiktok_poster.cli.tiktok.send_to_drafts", side_effect=["id-1", "id-2", "id-3"]
    ) as send_mock:
        _run_post(_args())

    assert send_mock.call_count == 3


def test_post_titles_and_hashtags_reach_the_api(config: Config) -> None:
    _authorize(config)
    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.push", return_value=True
    ), patch("tiktok_poster.cli.pages.wait_until_live"), patch(
        "tiktok_poster.cli.tiktok.send_to_drafts", return_value="id"
    ) as send_mock:
        _run_post(_args(count=1))

    _, title, description, urls = send_mock.call_args.args
    assert title == "INTJがしんどい時に出るサイン"
    assert description == "#恋愛 #MBTI #INTJ"
    assert len(urls) == 7


def test_a_failed_send_leaves_the_carousel_pending(config: Config) -> None:
    from tiktok_poster.tiktok import TikTokError

    _authorize(config)
    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.push", return_value=True
    ), patch("tiktok_poster.cli.pages.wait_until_live"), patch(
        "tiktok_poster.cli.tiktok.send_to_drafts", side_effect=TikTokError("boom")
    ):
        assert _run_post(_args(count=1)) == 1

    # Nothing recorded means the next run picks it up again.
    assert load_state(config.state_path).records == []


def test_dry_run_touches_neither_git_nor_tiktok(config: Config) -> None:
    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.push"
    ) as push_mock, patch("tiktok_poster.cli.tiktok.send_to_drafts") as send_mock:
        assert _run_post(_args(dry_run=True)) == 0

    push_mock.assert_not_called()
    send_mock.assert_not_called()
    # It still converts, so the URLs printed are the ones that would be sent.
    assert post_publish_dir(config, scan(config.source_dir)[0]).exists()


def test_recently_sent_carousels_stay_reachable_after_pruning(config: Config) -> None:
    # TikTok pulls the images asynchronously; dropping them immediately would 404.
    _authorize(config)
    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.push", return_value=True
    ), patch("tiktok_poster.cli.pages.wait_until_live"), patch(
        "tiktok_poster.cli.tiktok.send_to_drafts", side_effect=["id-1", "id-2"]
    ):
        _run_post(_args(count=1))
        _run_post(_args(count=1))

    posts = scan(config.source_dir)
    assert post_publish_dir(config, posts[0]).exists()
    assert post_publish_dir(config, posts[1]).exists()


def test_a_publish_failure_sends_nothing_and_keeps_the_batch_pending(config: Config) -> None:
    _authorize(config)
    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.push", side_effect=PagesError("no upstream")
    ), patch("tiktok_poster.cli.tiktok.send_to_drafts") as send_mock:
        assert _run_post(_args()) == 1

    send_mock.assert_not_called()
    assert load_state(config.state_path).records == []
