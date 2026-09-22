from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tiktok_poster.catalog import load_manifest, manifest_path, scan_fresh
from tiktok_poster.cli import _queue, _run_post, _run_sync
from tiktok_poster.config import Config
from tiktok_poster.media import post_publish_dir
from tiktok_poster.pages import PagesError, wait_until_live
from tiktok_poster.state import load_state, save_state


class FakeHead:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def _sync_args(dry_run: bool = True) -> argparse.Namespace:
    return argparse.Namespace(dry_run=dry_run)


def _post_args(count=None, dry_run=False, no_push=True, daily_limit=0) -> argparse.Namespace:
    return argparse.Namespace(count=count, dry_run=dry_run, no_push=no_push, delay=0, daily_limit=daily_limit)


def _authorize(config: Config) -> None:
    from tiktok_poster.tiktok import Tokens, save_tokens

    expiry = datetime.now(timezone.utc) + timedelta(hours=5)
    save_tokens(config, Tokens("access-1", "refresh-1", expiry.isoformat(timespec="seconds")))


def _synced(config: Config) -> None:
    """Put the fixture through sync so a manifest exists, as CI would find it."""
    with patch("tiktok_poster.cli.load_config", return_value=config):
        assert _run_sync(_sync_args(dry_run=True)) == 0


def test_sync_publishes_the_written_posts_and_records_them(config: Config) -> None:
    _synced(config)

    uploads = {upload.key: upload for upload in load_manifest(manifest_path(config.publish_dir))}
    written = [post for post in scan_fresh(config.source_dir) if not post.filler]
    for post in written:
        assert post.key in uploads
        assert post_publish_dir(config, post).exists()
        assert len(uploads[post.key].images) == len(post.slides)
        assert all(url.startswith(config.pages_base_url) for url in uploads[post.key].images)


def test_sync_publishes_only_the_filler_the_queue_will_reach(config: Config) -> None:
    # Filler is hundreds of posts that may never be needed; publishing them all
    # would put a quarter of a gigabyte of JPEG into the repository for nothing.
    _synced(config)

    uploads = load_manifest(manifest_path(config.publish_dir))
    filler = [upload.key for upload in uploads if upload.filler]
    assert filler == ["posts/L0001-manual"]  # publish_filler=1 in the fixture
    assert not (config.publish_dir / "posts" / "L0002-manual").exists()


def test_post_runs_without_the_source_images(config: Config) -> None:
    # source_dir is gitignored, so CI never sees it; posting must not touch it.
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

    # The fixture publishes two written posts and one piece of filler.
    assert send_mock.call_count == 3
    assert len(load_state(config.state_path).records) == 3


def test_post_does_not_resend_what_is_already_recorded(config: Config) -> None:
    _synced(config)
    _authorize(config)
    state = load_state(config.state_path)
    state.add(load_manifest(manifest_path(config.publish_dir))[0].key, "already", "id-0")
    save_state(config.state_path, state)

    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.wait_until_live"
    ), patch("tiktok_poster.cli.tiktok.send_to_drafts", side_effect=["a", "b"]) as send_mock:
        _run_post(_post_args())

    assert send_mock.call_count == 2


def test_post_titles_and_hashtags_reach_the_api(config: Config) -> None:
    _synced(config)
    _authorize(config)

    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.wait_until_live"
    ), patch("tiktok_poster.cli.tiktok.send_to_drafts", return_value="id") as send_mock:
        _run_post(_post_args(count=1))

    _, title, description, urls = send_mock.call_args.args
    assert title == "既読スルーされた時の16タイプ"
    assert description == "既読スルーされた時の16タイプのフック\n\n#MBTI #gallery"
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


@pytest.mark.parametrize(
    "pasted",
    [
        "https://ryota-sotoguchi.github.io/post/?code=abc%2Av%215320.s1&state=xyz",
        "code=abc%2Av%215320.s1&scopes=user.info.basic%2Cvideo.upload&state=xyz",
        "abc%2Av%215320.s1",
        "abc*v!5320.s1",
    ],
)
def test_the_pasted_redirect_is_decoded_however_it_arrives(pasted: str) -> None:
    """The code is percent-encoded in the address bar; pasting it raw must work."""
    from tiktok_poster.cli import _extract_code

    assert _extract_code(pasted) == "abc*v!5320.s1"


def test_a_full_draft_inbox_stops_the_batch(config: Config) -> None:
    """TikTok caps pending drafts, so the rest of a batch cannot succeed either.

    Sending a long backlog into a full inbox produced one refusal per carousel
    and hammered the endpoint for nothing.
    """
    from tiktok_poster.tiktok import DraftBacklogFull

    _synced(config)
    _authorize(config)

    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.wait_until_live"
    ), patch(
        "tiktok_poster.cli.tiktok.send_to_drafts",
        side_effect=["ok-1", DraftBacklogFull("full"), "never"],
    ) as send_mock:
        _run_post(_post_args())

    # Stopped at the refusal rather than trying what was behind it.
    assert send_mock.call_count == 2
    records = load_state(config.state_path).records
    assert len(records) == 1


def test_the_days_quota_survives_frequent_slots(config: Config) -> None:
    """Slots fire every half hour; the quota is what stops that flooding.

    Without it, a run every 30 minutes would send far more than the day's
    target as soon as the account published enough to free up room.
    """
    _synced(config)
    _authorize(config)

    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.wait_until_live"
    ), patch("tiktok_poster.cli.tiktok.send_to_drafts", side_effect=["a", "b"]) as send_mock:
        assert _run_post(_post_args(count=5, daily_limit=2)) == 0
    assert send_mock.call_count == 2

    # A later slot the same day finds the quota already spent.
    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.wait_until_live"
    ), patch("tiktok_poster.cli.tiktok.send_to_drafts") as send_mock:
        assert _run_post(_post_args(count=5, daily_limit=2)) == 0
    send_mock.assert_not_called()


def test_a_blocked_carousel_stays_at_the_head_of_the_queue(config: Config) -> None:
    """A full inbox must delay a carousel, never pass over it."""
    from tiktok_poster.tiktok import DraftBacklogFull

    _synced(config)
    _authorize(config)
    first = load_manifest(manifest_path(config.publish_dir))[0]

    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.wait_until_live"
    ), patch("tiktok_poster.cli.tiktok.send_to_drafts", side_effect=DraftBacklogFull("full")):
        assert _run_post(_post_args(count=1)) == 0
    assert load_state(config.state_path).records == []

    # The next slot offers the very same carousel, not the one after it.
    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.wait_until_live"
    ), patch("tiktok_poster.cli.tiktok.send_to_drafts", return_value="ok") as send_mock:
        assert _run_post(_post_args(count=1)) == 0
    assert send_mock.call_args.args[1] == first.title


def _sent(config: Config, *keys: str) -> None:
    state = load_state(config.state_path)
    for key in keys:
        state.add(key, key, f"id-{key}")
    save_state(config.state_path, state)


def test_filler_goes_out_only_once_the_written_posts_are_gone(config: Config) -> None:
    """Ten posts are written a day and ten are sent, so filler is for the days
    that did not happen: the PC was off, or the API was down."""
    _synced(config)
    _authorize(config)
    _sent(config, "posts/00001-gallery", "posts/00002-manual")

    with patch("tiktok_poster.cli.load_config", return_value=config), patch(
        "tiktok_poster.cli.pages.wait_until_live"
    ), patch("tiktok_poster.cli.tiktok.send_to_drafts", return_value="ok") as send_mock:
        assert _run_post(_post_args(count=1)) == 0

    assert send_mock.call_args.args[1] == "INFPが本命だけに見せる距離の縮め方"


def test_sync_commits_the_generator_state_with_the_media(config: Config) -> None:
    # The generator's progress is only ever committed here. Losing it on a
    # fresh clone restarts the series and redraws topics already sent.
    state_dir = config.project_root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "series_state.json").write_text('{"next_post_index": 244}', encoding="utf-8")
    (state_dir / "phone_export_daemon_state.json").write_text('{"completed_slots": []}', encoding="utf-8")
    (state_dir / "format_state.json").write_text('{"next_seq": 12}', encoding="utf-8")
    (state_dir / "legacy_converted.json").write_text('{"theme/post_01_INTJ": 1}', encoding="utf-8")

    with patch("tiktok_poster.cli.load_config", return_value=config), \
         patch("tiktok_poster.cli.pages.push", return_value=True) as push:
        assert _run_sync(_sync_args(dry_run=False)) == 0

    pushed = {str(path) for path in push.call_args.args[2:]}
    assert str(config.publish_dir) in pushed
    assert str(state_dir / "series_state.json") in pushed
    assert str(state_dir / "phone_export_daemon_state.json") in pushed
    assert str(state_dir / "format_state.json") in pushed
    assert str(state_dir / "legacy_converted.json") in pushed
    # Actions writes this one; sync committing a stale local copy would race it.
    assert str(config.state_path) not in pushed
