from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tiktok_poster.catalog import load_manifest, manifest_path, scan
from tiktok_poster.cli import _run_post, _run_sync
from tiktok_poster.config import Config
from tiktok_poster.media import post_publish_dir
from tiktok_poster.pages import PagesError, wait_until_live
from tiktok_poster.state import load_state, save_state


class FakeHead:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def _sync_args(dry_run: bool = True) -> argparse.Namespace:
    return argparse.Namespace(dry_run=dry_run)


def _post_args(count=None, dry_run=False, no_push=True) -> argparse.Namespace:
    return argparse.Namespace(count=count, dry_run=dry_run, no_push=no_push)


def _authorize(config: Config) -> None:
    from tiktok_poster.tiktok import Tokens, save_tokens

    expiry = datetime.now(timezone.utc) + timedelta(hours=5)
    save_tokens(config, Tokens("access-1", "refresh-1", expiry.isoformat(timespec="seconds")))


def _synced(config: Config) -> None:
    """Put the fixture through sync so a manifest exists, as CI would find it."""
    with patch("tiktok_poster.cli.load_config", return_value=config):
        assert _run_sync(_sync_args(dry_run=True)) == 0


def test_sync_publishes_every_carousel_and_records_it(config: Config) -> None:
    _synced(config)

    uploads = load_manifest(manifest_path(config.publish_dir))
    assert len(uploads) == len(scan(config.source_dir))
    for upload, post in zip(uploads, scan(config.source_dir)):
        assert upload.key == post.key
        assert post_publish_dir(config, post).exists()
        assert len(upload.images) == len(post.slides)
        assert all(url.startswith(config.pages_base_url) for url in upload.images)


def test_post_runs_without_the_source_images(config: Config) -> None:
    # CI has the repo but never the OneDrive folder, so posting must not touch it.
    _synced(config)
    shutil.rmtree(config.source_dir)
    _authorize(config)

    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.wait_until_live"
    ), patch("tiktok_poster.cli.tiktok.send_to_drafts", return_value="id-1") as send_mock:
        assert _run_post(_post_args(count=1)) == 0

    assert send_mock.call_count == 1
    assert len(load_state(config.state_path).records) == 1


def test_post_sends_a_day_worth_and_records_each(config: Config) -> None:
    _synced(config)
    _authorize(config)

    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.wait_until_live"
    ), patch("tiktok_poster.cli.tiktok.send_to_drafts", side_effect=["a", "b", "c", "d"]) as send_mock:
        assert _run_post(_post_args()) == 0

    # The fixture holds four carousels, so stock caps the day's batch.
    assert send_mock.call_count == 4
    assert len(load_state(config.state_path).records) == 4


def test_post_does_not_resend_what_is_already_recorded(config: Config) -> None:
    _synced(config)
    _authorize(config)
    state = load_state(config.state_path)
    state.add(load_manifest(manifest_path(config.publish_dir))[0].key, "already", "id-0")
    save_state(config.state_path, state)

    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.wait_until_live"
    ), patch("tiktok_poster.cli.tiktok.send_to_drafts", side_effect=["a", "b", "c"]) as send_mock:
        _run_post(_post_args())

    assert send_mock.call_count == 3


def test_post_titles_and_hashtags_reach_the_api(config: Config) -> None:
    _synced(config)
    _authorize(config)

    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.wait_until_live"
    ), patch("tiktok_poster.cli.tiktok.send_to_drafts", return_value="id") as send_mock:
        _run_post(_post_args(count=1))

    _, title, description, urls = send_mock.call_args.args
    assert title == "INTJがしんどい時に出るサイン"
    assert description == "#恋愛 #MBTI #INTJ"
    assert len(urls) == 7


def test_a_failed_send_leaves_the_carousel_pending(config: Config) -> None:
    from tiktok_poster.tiktok import TikTokError

    _synced(config)
    _authorize(config)

    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.wait_until_live"
    ), patch("tiktok_poster.cli.tiktok.send_to_drafts", side_effect=TikTokError("boom")):
        assert _run_post(_post_args(count=1)) == 1

    # Nothing recorded means the next run picks it up again.
    assert load_state(config.state_path).records == []


def test_a_url_that_never_serves_is_not_sent(config: Config) -> None:
    _synced(config)
    _authorize(config)

    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.wait_until_live", side_effect=PagesError("404")
    ), patch("tiktok_poster.cli.tiktok.send_to_drafts") as send_mock:
        assert _run_post(_post_args(count=1)) == 1

    send_mock.assert_not_called()
    assert load_state(config.state_path).records == []


def test_dry_run_does_not_call_tiktok(config: Config) -> None:
    _synced(config)

    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.tiktok.send_to_drafts"
    ) as send_mock:
        assert _run_post(_post_args(dry_run=True)) == 0

    send_mock.assert_not_called()
    assert load_state(config.state_path).records == []


def test_post_without_a_manifest_explains_what_to_run(config: Config) -> None:
    _authorize(config)

    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.tiktok.send_to_drafts"
    ) as send_mock:
        assert _run_post(_post_args()) == 1

    send_mock.assert_not_called()


def test_wait_until_live_gives_up_rather_than_sending_a_dead_url() -> None:
    # A 404 here would make TikTok fail the pull asynchronously, long after the call.
    with patch("tiktok_poster.pages.requests.head", return_value=FakeHead(404)):
        with pytest.raises(PagesError):
            wait_until_live(["https://example.com/a.jpg"], attempts=2, delay=0)


def test_wait_until_live_returns_once_pages_serves() -> None:
    with patch("tiktok_poster.pages.requests.head", return_value=FakeHead(200)):
        wait_until_live(["https://example.com/a.jpg"], attempts=1, delay=0)
