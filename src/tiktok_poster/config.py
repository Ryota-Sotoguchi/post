from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_bytes().decode("utf-8-sig", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _settings(project_root: Path) -> dict[str, str]:
    settings = _read_env_file(project_root / ".env")
    settings.update(os.environ)
    return settings


@dataclass(frozen=True, slots=True)
class Config:
    project_root: Path
    source_dir: Path
    publish_dir: Path
    pages_base_url: str
    state_path: Path
    posts_per_day: int
    jpeg_quality: int
    keep_published_posts: int
    client_key: str | None
    client_secret: str | None
    refresh_token: str | None

    @property
    def is_authorized(self) -> bool:
        return bool(self.client_key and self.client_secret and self.refresh_token)


def load_config(project_root: Path | None = None) -> Config:
    root = project_root or Path.cwd()
    settings = _settings(root)

    def path_of(name: str, default: str) -> Path:
        raw = settings.get(name, default)
        candidate = Path(raw)
        return candidate if candidate.is_absolute() else root / candidate

    return Config(
        project_root=root,
        source_dir=path_of("SOURCE_DIR", "source"),
        publish_dir=path_of("PUBLISH_DIR", "docs/media"),
        # TikTok verifies ownership of an exact URL prefix, so this has to match
        # the prefix registered in the developer portal, character for character.
        pages_base_url=settings.get("PAGES_BASE_URL", "").rstrip("/"),
        state_path=path_of("STATE_PATH", "state/posted.json"),
        posts_per_day=int(settings.get("POSTS_PER_DAY", "5")),
        jpeg_quality=int(settings.get("JPEG_QUALITY", "90")),
        # Published images stay reachable only long enough for TikTok to fetch
        # them; keeping every carousel would grow the repo without bound.
        keep_published_posts=int(settings.get("KEEP_PUBLISHED_POSTS", "20")),
        client_key=settings.get("TIKTOK_CLIENT_KEY") or None,
        client_secret=settings.get("TIKTOK_CLIENT_SECRET") or None,
        refresh_token=settings.get("TIKTOK_REFRESH_TOKEN") or None,
    )
