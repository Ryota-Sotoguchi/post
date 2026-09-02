from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from tiktok_poster.config import Config
from tiktok_poster.tiktok import REQUEST_TIMEOUT, TOKEN_URL, TikTokError, Tokens, _check, save_tokens

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
# video.upload covers MEDIA_UPLOAD (drafts). Asking for video.publish as well
# would be an unused scope, which is grounds for rejection at audit.
SCOPE = "video.upload"


def authorize_url(config: Config, redirect_uri: str) -> tuple[str, str]:
    if not config.client_key:
        raise TikTokError("TIKTOK_CLIENT_KEY must be set")
    state = secrets.token_urlsafe(16)
    query = urlencode(
        {
            "client_key": config.client_key,
            "scope": SCOPE,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}", state


def exchange_code(config: Config, code: str, redirect_uri: str) -> Tokens:
    if not (config.client_key and config.client_secret):
        raise TikTokError("TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET must be set")

    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": config.client_key,
            "client_secret": config.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=REQUEST_TIMEOUT,
    )
    payload = _check(response, "code exchange")

    refresh_token = payload.get("refresh_token")
    access_token = payload.get("access_token")
    if not (refresh_token and access_token):
        raise TikTokError(f"code exchange returned no tokens: {payload}")

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(payload.get("expires_in", 86400)))
    tokens = Tokens(
        access_token=str(access_token),
        refresh_token=str(refresh_token),
        expires_at=expires_at.isoformat(timespec="seconds"),
    )
    save_tokens(config, tokens)
    return tokens
