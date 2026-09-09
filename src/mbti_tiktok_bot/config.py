from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _read_env_file(path: Path) -> dict[str, str]:
    raw_bytes = path.read_bytes()
    text = None
    for encoding in ["utf-8-sig", "utf-8", "cp932"]:
        try:
            text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw_bytes.decode("utf-8", errors="ignore")

    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_value = value.strip()
        if len(normalized_value) >= 2 and normalized_value[0] == normalized_value[-1] and normalized_value[0] in {'"', "'"}:
            normalized_value = normalized_value[1:-1]
        values[key.strip()] = normalized_value
    return values


def _load_settings(project_root: Path) -> dict[str, str]:
    # The repo root .env is the shared file, read by the poster half too. The
    # generator used to keep its config inside .venv/, which does not survive
    # rebuilding the virtualenv; that location is still honoured so an existing
    # checkout keeps working, but the root file wins.
    settings: dict[str, str] = {}
    for env_path in (project_root / ".venv" / ".env", project_root / ".env"):
        if env_path.exists():
            settings.update(_read_env_file(env_path))
    settings.update(os.environ)
    return settings


def _bool_env(settings: dict[str, str], name: str, default: bool = False) -> bool:
    raw_value = settings.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _path_env(settings: dict[str, str], project_root: Path, name: str, default: str) -> Path:
    raw_value = settings.get(name, default)
    candidate = Path(raw_value)
    if candidate.is_absolute():
        return candidate
    return project_root / candidate


@dataclass(slots=True)
class AppConfig:
    project_root: Path
    output_dir: Path
    assets_dir: Path
    official_images_dir: Path
    editorial_photos_dir: Path
    state_dir: Path
    openai_api_key: str | None
    openai_model: str
    openai_base_url: str
    video_width: int
    video_height: int
    daily_posts: int
    slot_posts: int
    topic_depth: str
    default_hashtags: list[str]
    phone_export_auto: bool
    phone_export_dir: Path
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    telegram_as_document: bool
    keep_render_layers: bool


def load_config(project_root: Path | None = None) -> AppConfig:
    resolved_root = project_root or Path.cwd()
    settings = _load_settings(resolved_root)

    default_hashtags = settings.get(
        "DEFAULT_HASHTAGS",
        "#MBTI #mbti診断 #16personalities #性格診断",
    ).split()

    return AppConfig(
        project_root=resolved_root,
        output_dir=resolved_root / "out",
        assets_dir=resolved_root / "assets" / "mbti_images",
        official_images_dir=resolved_root / settings.get("MBTI_IMAGES_DIR", "images"),
        # Photographs for the editorial motif. The motif drops out of the
        # rotation when the folder is empty, so this is optional.
        editorial_photos_dir=_path_env(settings, resolved_root, "MBTI_EDITORIAL_PHOTOS_DIR", "assets/editorial_people"),
        state_dir=resolved_root / "state",
        openai_api_key=settings.get("OPENAI_API_KEY") or None,
        openai_model=settings.get("OPENAI_MODEL", "gpt-4.1-mini"),
        openai_base_url=settings.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        video_width=int(settings.get("VIDEO_WIDTH", "1080")),
        video_height=int(settings.get("VIDEO_HEIGHT", "1920")),
        daily_posts=int(settings.get("DAILY_POSTS", "3")),
        # One scheduled slot draws this many types. Four slots of four
        # covers all 16 MBTI types in a day, so a theme starts and
        # finishes on the same date instead of straddling five of them.
        slot_posts=int(settings.get("SLOT_POSTS", "4")),
        topic_depth=(settings.get("TOPIC_DEPTH", "deep").strip().lower() or "deep"),
        default_hashtags=default_hashtags,
        phone_export_auto=_bool_env(settings, "PHONE_EXPORT_AUTO", default=False),
        phone_export_dir=_path_env(settings, resolved_root, "PHONE_EXPORT_DIR", "delivery/phone"),
        telegram_bot_token=settings.get("TELEGRAM_BOT_TOKEN") or None,
        telegram_chat_id=settings.get("TELEGRAM_CHAT_ID") or None,
        # Telegram re-encodes anything sent as a photo. Slides go out as
        # documents so what lands in the camera roll is the rendered PNG.
        telegram_as_document=_bool_env(settings, "TELEGRAM_AS_DOCUMENT", default=True),
        # Per-layer PNGs are a debugging aid. Keeping them cost more disk
        # than the finished slides they were built from.
        keep_render_layers=_bool_env(settings, "MBTI_KEEP_RENDER_LAYERS", default=False),
    )
