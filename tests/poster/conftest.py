from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from tiktok_poster.config import Config, load_config

# Two posts as the generator writes them, and two pieces of filler: the back
# catalogue redrawn in the current design, which goes out only when nothing
# freshly written is waiting.
LAYOUT = (
    ("00001-gallery", "gallery", "既読スルーされた時の16タイプ", False),
    ("00002-manual", "manual", "INTJの取扱説明書", False),
    ("L0001-manual", "manual", "INFPが本命だけに見せる距離の縮め方", True),
    ("L0002-manual", "manual", "ENFJが本命だけに見せる距離の縮め方", True),
)
SLIDES = 7


def _slide(path: Path, size=(1080, 1920), mode="RGB") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, (120, 60, 200) if mode == "RGB" else (120, 60, 200, 255)).save(path)


def write_post(source: Path, name: str, format: str, title: str, filler: bool, slides: int = SLIDES) -> Path:
    folder = source / "_posts" / name
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(1, slides + 1):
        _slide(folder / f"slide_{index:02d}.png")
    folder.joinpath("post.json").write_text(
        json.dumps(
            {
                "key": name,
                "format": format,
                "post_date": "2026-09-20",
                "title": title,
                "description": f"{title}のフック\n\n#MBTI #{format}",
                "filler": filler,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return folder


@pytest.fixture
def source_tree(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    for name, format, title, filler in LAYOUT:
        write_post(source, name, format, title, filler)
    # Noise that must be ignored: a post still being written, so without the
    # post.json that is saved last, and a stray file beside the handoff folder.
    _slide(source / "_posts" / "00003-ranking" / "slide_01.png")
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
        # One piece of filler published at a time stands in for the thirty days
        # of stock the real setting keeps reachable.
        publish_filler=1,
        jpeg_quality=90,
        keep_published_posts=2,
        client_key="key",
        client_secret="secret",
        refresh_token="refresh-0",
    )
