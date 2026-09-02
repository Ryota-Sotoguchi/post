from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tiktok_poster.config import Config
from tiktok_poster.tiktok import (
    Tokens,
    TikTokError,
    access_token,
    load_tokens,
    refresh_tokens,
    save_tokens,
    send_to_drafts,
    tokens_path,
)

URLS = [f"https://example.github.io/tiktok/media/ab/post_01_INTJ/{i:02d}.jpg" for i in range(1, 8)]


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


def _ok(publish_id: str = "p_pub_url~v2.1") -> FakeResponse:
    return FakeResponse({"data": {"publish_id": publish_id}, "error": {"code": "ok", "message": ""}})


def _fresh_tokens(config: Config) -> None:
    expiry = datetime.now(timezone.utc) + timedelta(hours=5)
    save_tokens(config, Tokens("access-1", "refresh-1", expiry.isoformat(timespec="seconds")))


def test_draft_request_matches_the_photo_schema(config: Config) -> None:
    _fresh_tokens(config)
    with patch("tiktok_poster.tiktok.requests.post", return_value=_ok()) as post_mock:
        publish_id = send_to_drafts(config, "INTJがしんどい時に出るサイン", "#恋愛 #MBTI #INTJ", URLS)

    assert publish_id == "p_pub_url~v2.1"
    body = post_mock.call_args.kwargs["json"]
    assert body["media_type"] == "PHOTO"
    assert body["post_mode"] == "MEDIA_UPLOAD"
    assert body["source_info"]["source"] == "PULL_FROM_URL"
    assert body["source_info"]["photo_cover_index"] == 0
    assert body["source_info"]["photo_images"] == URLS
    assert body["post_info"]["title"] == "INTJがしんどい時に出るサイン"
    assert body["post_info"]["description"] == "#恋愛 #MBTI #INTJ"


def test_title_is_trimmed_to_the_documented_limit(config: Config) -> None:
    _fresh_tokens(config)
    with patch("tiktok_poster.tiktok.requests.post", return_value=_ok()) as post_mock:
        send_to_drafts(config, "あ" * 200, "d", URLS)

    assert len(post_mock.call_args.kwargs["json"]["post_info"]["title"]) == 90


def test_non_https_urls_are_refused_before_the_call(config: Config) -> None:
    _fresh_tokens(config)
    with patch("tiktok_poster.tiktok.requests.post") as post_mock:
        with pytest.raises(TikTokError, match="https"):
            send_to_drafts(config, "t", "d", ["http://example.com/1.jpg"])
    post_mock.assert_not_called()


def test_more_than_thirty_five_images_is_refused(config: Config) -> None:
    _fresh_tokens(config)
    with pytest.raises(TikTokError, match="35"):
        send_to_drafts(config, "t", "d", [f"https://e.com/{i}.jpg" for i in range(36)])


def test_api_error_payload_is_surfaced(config: Config) -> None:
    _fresh_tokens(config)
    failure = FakeResponse({"error": {"code": "url_ownership_unverified", "message": "unverified"}})
    with patch("tiktok_poster.tiktok.requests.post", return_value=failure):
        with pytest.raises(TikTokError, match="url_ownership_unverified"):
            send_to_drafts(config, "t", "d", URLS)


def test_refresh_persists_the_rotated_token(config: Config) -> None:
    # TikTok returns a new refresh token each time; losing it means redoing consent.
    payload = FakeResponse(
        {"access_token": "access-2", "refresh_token": "refresh-2", "expires_in": 86400, "error": {"code": "ok"}}
    )
    with patch("tiktok_poster.tiktok.requests.post", return_value=payload):
        tokens = refresh_tokens(config)

    assert tokens.refresh_token == "refresh-2"
    assert load_tokens(config).refresh_token == "refresh-2"


def test_stored_token_file_is_not_world_readable(config: Config) -> None:
    _fresh_tokens(config)
    assert tokens_path(config).stat().st_mode & 0o077 == 0


def test_a_fresh_access_token_is_reused(config: Config) -> None:
    _fresh_tokens(config)
    with patch("tiktok_poster.tiktok.requests.post") as post_mock:
        assert access_token(config) == "access-1"
    post_mock.assert_not_called()


def test_an_expired_access_token_triggers_a_refresh(config: Config) -> None:
    stale = datetime.now(timezone.utc) - timedelta(hours=1)
    save_tokens(config, Tokens("access-old", "refresh-1", stale.isoformat(timespec="seconds")))
    payload = FakeResponse(
        {"access_token": "access-new", "refresh_token": "refresh-2", "expires_in": 86400, "error": {"code": "ok"}}
    )
    with patch("tiktok_poster.tiktok.requests.post", return_value=payload):
        assert access_token(config) == "access-new"


def test_an_oauth_style_error_is_reported_not_crashed(config):
    """The OAuth endpoints return `error` as a string, not as an object.

    Treating it like the content API's nested error raised AttributeError and
    buried the real reason a refresh had failed.
    """
    from unittest.mock import patch

    from tiktok_poster.tiktok import TikTokError, refresh_tokens

    response = FakeResponse(
        {"error": "invalid_grant", "error_description": "Refresh token is invalid or expired."},
        status_code=400,
    )
    with patch("tiktok_poster.tiktok.requests.post", return_value=response):
        with pytest.raises(TikTokError) as excinfo:
            refresh_tokens(config)

    assert "invalid_grant" in str(excinfo.value)
    assert "invalid or expired" in str(excinfo.value)


def test_a_rotated_token_survives_a_broken_response(config):
    """The new refresh token is saved before the response is validated.

    TikTok kills the old token the moment it issues a new one, so a rotation
    followed by an error must not lose the replacement — that strands the
    account until someone re-runs the browser consent by hand.
    """
    from unittest.mock import patch

    from tiktok_poster.tiktok import TikTokError, load_tokens, refresh_tokens

    response = FakeResponse(
        {"refresh_token": "rotated-token", "error": "internal_error", "error_description": "boom"},
        status_code=500,
    )
    with patch("tiktok_poster.tiktok.requests.post", return_value=response):
        with pytest.raises(TikTokError):
            refresh_tokens(config)

    assert load_tokens(config).refresh_token == "rotated-token"


def test_photo_posts_ask_tiktok_to_pick_the_music(config: Config) -> None:
    """No API field names a track, so the recommendation is the only option.

    Without it every carousel arrives silent and the music has to be chosen by
    hand before each one can be published.
    """
    _fresh_tokens(config)
    with patch("tiktok_poster.tiktok.requests.post", return_value=_ok()) as post_mock:
        send_to_drafts(config, "t", "d", URLS)

    assert post_mock.call_args.kwargs["json"]["post_info"]["auto_add_music"] is True
