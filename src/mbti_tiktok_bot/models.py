from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


CLOSER_SCENE_TITLE = "ここまで見た人へ"
CLOSER_SCENE_BODY = "合ってたらコメントしてね。友だちにもシェアして、答え合わせしてみて。"


@dataclass(slots=True)
class Scene:
    title: str
    body: str
    duration_seconds: float = 4.0


@dataclass(slots=True)
class ContentPackage:
    post_date: str
    mbti_type: str
    archetype_name: str
    group_name: str
    title: str
    series_name: str
    format_name: str
    theme: str
    hook: str
    narration: str
    caption: str
    hashtags: list[str]
    global_post_index: int = 0
    daily_slot: int = 1
    series_post_number: int = 1
    series_total_posts: int = 16
    scenes: list[Scene] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class SceneRenderAssets:
    background_path: Path
    text_overlay_path: Path | None = None
    character_overlay_path: Path | None = None
    accent_overlay_path: Path | None = None
