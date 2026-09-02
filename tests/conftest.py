from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from tiktok_poster.config import Config, load_config


def _slide(path: Path, size=(1080, 1920), mode="RGB") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, (120, 60, 200) if mode == "RGB" else (120, 60, 200, 255)).save(path)


@pytest.fixture
def source_tree(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    layout = {
        "が本命だけに見せる距離の縮め方": ["post_01_INTJ", "post_02_INTP", "post_10_ISFJ"],
        "がしんどい時に出るサイン": ["post_01_INTJ"],
    }
    for theme, posts in layout.items():
        for post in posts:
            for index in range(1, 8):
                _slide(source / theme / post / f"slide_{index:02d}.png")
    # Noise that must be ignored.
    (source / "が本命だけに見せる距離の縮め方" / "notes").mkdir(parents=True, exist_ok=True)
    (source / "が本命だけに見せる距離の縮め方" / "notes" / "readme.txt").write_text("x", encoding="utf-8")
    (source / "plan.xlsx").write_text("x", encoding="utf-8")
    return source


@pytest.fixture
def config(tmp_path: Path, source_tree: Path) -> Config:
    return replace(
        load_config(tmp_path),
        project_root=tmp_path,
        source_dir=source_tree,
        publish_dir=tmp_path / "docs" / "media",
        state_path=tmp_path / "state" / "posted.json",
        pages_base_url="https://example.github.io/tiktok/media",
        posts_per_day=5,
        jpeg_quality=90,
        keep_published_posts=2,
        client_key="key",
        client_secret="secret",
        refresh_token="refresh-0",
    )
