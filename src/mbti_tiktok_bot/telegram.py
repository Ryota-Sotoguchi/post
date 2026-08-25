"""Deliver finished slides to a Telegram chat.

The generation runs on GitHub Actions, which cannot reach a local sync folder,
so the phone picks the slides up from a chat instead. Slides go out as an album
of documents rather than photos: Telegram re-encodes photos, and these are
posted to TikTok afterwards, so the rendered PNG has to survive intact. The
caption follows as its own text message so it can be copied in one long-press.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from mbti_tiktok_bot.config import AppConfig
from mbti_tiktok_bot.pipeline import PipelineResult

API_ROOT = "https://api.telegram.org"
# Telegram caps an album at 10 items.
MAX_ALBUM_SIZE = 10
MAX_ATTEMPTS = 4
REQUEST_TIMEOUT_SECONDS = 120


class TelegramError(RuntimeError):
    pass


@dataclass(slots=True)
class TelegramDeliveryResult:
    sent_posts: int
    sent_files: int


def _method_url(token: str, method: str) -> str:
    return f"{API_ROOT}/bot{token}/{method}"


def _post(
    token: str,
    method: str,
    data: dict[str, object],
    files: dict[str, tuple[str, Path]] | None = None,
) -> dict:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        # The upload consumes the handles, so reopen them for every attempt.
        handles = [(name, filename, path.open("rb")) for name, (filename, path) in (files or {}).items()]
        try:
            response = requests.post(
                _method_url(token, method),
                data=data,
                files={name: (filename, handle) for name, filename, handle in handles} or None,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        finally:
            for _, _, handle in handles:
                handle.close()

        if response.status_code == 429:
            retry_after = int(response.json().get("parameters", {}).get("retry_after", 5))
            time.sleep(retry_after)
            continue
        if response.status_code >= 500 and attempt < MAX_ATTEMPTS:
            time.sleep(2 ** attempt)
            continue

        payload = response.json()
        if not payload.get("ok"):
            raise TelegramError(f"Telegram {method} failed: {payload.get('description') or response.text}")
        return payload

    raise TelegramError(f"Telegram {method} failed after {MAX_ATTEMPTS} attempts")


def _chunk(items: list[Path], size: int) -> list[list[Path]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def send_album(config: AppConfig, image_paths: list[Path]) -> int:
    if not config.telegram_bot_token or not config.telegram_chat_id:
        raise TelegramError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")

    media_type = "document" if config.telegram_as_document else "photo"
    sent = 0
    for batch in _chunk(image_paths, MAX_ALBUM_SIZE):
        media = []
        files: dict[str, tuple] = {}
        for index, path in enumerate(batch):
            attach_name = f"file{index}"
            media.append({"type": media_type, "media": f"attach://{attach_name}"})
            files[attach_name] = (path.name, path)

        if len(batch) == 1:
            # sendMediaGroup rejects a single-item album.
            method = "sendDocument" if config.telegram_as_document else "sendPhoto"
            _post(
                config.telegram_bot_token,
                method,
                {"chat_id": config.telegram_chat_id},
                {media_type: (batch[0].name, batch[0])},
            )
        else:
            _post(
                config.telegram_bot_token,
                "sendMediaGroup",
                {"chat_id": config.telegram_chat_id, "media": json.dumps(media)},
                files,
            )
        sent += len(batch)
    return sent


def send_text(config: AppConfig, text: str) -> None:
    if not config.telegram_bot_token or not config.telegram_chat_id:
        raise TelegramError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")
    _post(
        config.telegram_bot_token,
        "sendMessage",
        {
            "chat_id": config.telegram_chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
    )


def deliver_results(config: AppConfig, results: list[PipelineResult]) -> TelegramDeliveryResult:
    sent_files = 0
    for result in results:
        image_paths = [path for path in result.media_paths if path.exists()]
        if not image_paths:
            continue

        caption = ""
        if result.caption_path.exists():
            caption = result.caption_path.read_text(encoding="utf-8").strip()

        send_text(config, f"{result.mbti_type} / {result.title}")
        sent_files += send_album(config, image_paths)
        if caption:
            send_text(config, caption)

    return TelegramDeliveryResult(sent_posts=len(results), sent_files=sent_files)
