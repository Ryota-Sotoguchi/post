from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from tiktok_poster.config import Config

API_ROOT = "https://open.tiktokapis.com/v2"
TOKEN_URL = f"{API_ROOT}/oauth/token/"
CONTENT_INIT_URL = f"{API_ROOT}/post/publish/content/init/"
STATUS_URL = f"{API_ROOT}/post/publish/status/fetch/"

TITLE_LIMIT = 90
DESCRIPTION_LIMIT = 4000
MAX_PHOTOS = 35
REQUEST_TIMEOUT = 60
# Access tokens last 24h; refresh a little early so a long run cannot straddle
# the expiry.
EXPIRY_MARGIN = timedelta(minutes=10)


class DraftBacklogFull(RuntimeError):
    """TikTok is refusing new drafts until the pending ones are published.

    Drafts cannot be stockpiled: the inbox holds only a handful at a time, and
    capacity comes back only as the account publishes them.
    """


class TikTokError(RuntimeError):
    pass


@dataclass(slots=True)
class Tokens:
    access_token: str
    refresh_token: str
    expires_at: str

    @property
    def is_fresh(self) -> bool:
        try:
            expiry = datetime.fromisoformat(self.expires_at)
        except ValueError:
            return False
        return datetime.now(timezone.utc) + EXPIRY_MARGIN < expiry


def tokens_path(config: Config) -> Path:
    return config.state_path.parent / "tokens.json"


def load_tokens(config: Config) -> Tokens | None:
    path = tokens_path(config)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not payload.get("refresh_token"):
        return None
    return Tokens(
        access_token=str(payload.get("access_token", "")),
        refresh_token=str(payload["refresh_token"]),
        expires_at=str(payload.get("expires_at", "")),
    )


def save_tokens(config: Config, tokens: Tokens) -> Path:
    path = tokens_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "access_token": tokens.access_token,
                "refresh_token": tokens.refresh_token,
                "expires_at": tokens.expires_at,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def _payload(response: requests.Response, what: str) -> dict:
    try:
        return response.json()
    except ValueError as exc:
        raise TikTokError(f"{what}: non-JSON response ({response.status_code})") from exc


def _raise_for_error(payload: dict, response: requests.Response, what: str) -> None:
    # The two endpoints disagree on the shape of an error: /post/publish/
    # nests {"code", "message"}, while the OAuth endpoints follow RFC 6749 and
    # return a bare string with error_description beside it.
    error = payload.get("error")
    if isinstance(error, dict):
        code, message = error.get("code", ""), error.get("message", "")
    elif isinstance(error, str):
        code, message = error, payload.get("error_description", "")
    else:
        code, message = "", ""

    if str(code).lower() not in {"", "ok"}:
        if str(code) == "spam_risk_too_many_pending_share":
            raise DraftBacklogFull(f"{what}: {code}")
        raise TikTokError(f"{what}: {code} - {message}")
    if response.status_code >= 400:
        raise TikTokError(f"{what}: HTTP {response.status_code} - {response.text[:400]}")


def _check(response: requests.Response, what: str) -> dict:
    payload = _payload(response, what)
    _raise_for_error(payload, response, what)
    return payload


def refresh_tokens(config: Config) -> Tokens:
    """Exchange the stored refresh token for a fresh pair.

    TikTok rotates the refresh token on every exchange, so the new one is
    persisted immediately; losing it means re-running the browser consent flow.
    """
    if not (config.client_key and config.client_secret):
        raise TikTokError("TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET must be set")

    stored = load_tokens(config)
    refresh_token = stored.refresh_token if stored else config.refresh_token
    if not refresh_token:
        raise TikTokError("No refresh token; run the authorize flow first")

    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": config.client_key,
            "client_secret": config.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=REQUEST_TIMEOUT,
    )
    payload = _payload(response, "token refresh")

    # TikTok invalidates the old refresh token the instant it issues a new one,
    # so the new one is written before anything else is validated. Failing
    # between the rotation and the save strands the account and costs a manual
    # re-authorization, which is exactly how the first CI run broke.
    rotated = payload.get("refresh_token")
    if rotated:
        save_tokens(
            config,
            Tokens(
                access_token=str(payload.get("access_token", "")),
                refresh_token=str(rotated),
                expires_at="",
            ),
        )
    _raise_for_error(payload, response, "token refresh")

    access_token = payload.get("access_token")
    new_refresh = rotated or refresh_token
    if not access_token:
        raise TikTokError(f"token refresh returned no access_token: {payload}")

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(payload.get("expires_in", 86400)))
    tokens = Tokens(
        access_token=str(access_token),
        refresh_token=str(new_refresh),
        expires_at=expires_at.isoformat(timespec="seconds"),
    )
    save_tokens(config, tokens)
    return tokens


def access_token(config: Config) -> str:
    stored = load_tokens(config)
    if stored and stored.access_token and stored.is_fresh:
        return stored.access_token
    # A CI run has no token file, and the sandbox will not refresh, so an
    # access token passed in by hand is the only credential it can have.
    if config.access_token:
        return config.access_token
    return refresh_tokens(config).access_token


def send_to_drafts(config: Config, title: str, description: str, photo_urls: list[str]) -> str:
    """Push a carousel into the creator's TikTok inbox. Returns the publish id."""
    if not photo_urls:
        raise TikTokError("No photo URLs to send")
    if len(photo_urls) > MAX_PHOTOS:
        raise TikTokError(f"A carousel takes at most {MAX_PHOTOS} images, got {len(photo_urls)}")
    for url in photo_urls:
        if not url.startswith("https://"):
            raise TikTokError(f"PULL_FROM_URL requires https: {url}")

    body = {
        "media_type": "PHOTO",
        "post_mode": "MEDIA_UPLOAD",
        "post_info": {
            "title": title[:TITLE_LIMIT],
            "description": description[:DESCRIPTION_LIMIT],
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "photo_cover_index": 0,
            "photo_images": photo_urls,
        },
    }
    response = requests.post(
        CONTENT_INIT_URL,
        headers={
            "Authorization": f"Bearer {access_token(config)}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    payload = _check(response, "content init")
    publish_id = (payload.get("data") or {}).get("publish_id")
    if not publish_id:
        raise TikTokError(f"content init returned no publish_id: {payload}")
    return str(publish_id)


def fetch_status(config: Config, publish_id: str) -> dict:
    response = requests.post(
        STATUS_URL,
        headers={
            "Authorization": f"Bearer {access_token(config)}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={"publish_id": publish_id},
        timeout=REQUEST_TIMEOUT,
    )
    return _check(response, "status fetch").get("data") or {}


def wait_for_completion(config: Config, publish_id: str, attempts: int = 10, delay: int = 6) -> dict:
    data: dict = {}
    for _ in range(attempts):
        data = fetch_status(config, publish_id)
        status = str(data.get("status", ""))
        if status in {"PUBLISH_COMPLETE", "FAILED"}:
            return data
        time.sleep(delay)
    return data
