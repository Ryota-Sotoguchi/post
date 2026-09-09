from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

from tiktok_poster.catalog import Post
from tiktok_poster.config import Config

# TikTok accepts WebP and JPEG for photo posts. PNG is rejected, and the
# renderer writes PNG, so every slide is converted on the way out.
OUTPUT_SUFFIX = ".jpg"
MAX_EDGE = 1080
MAX_BYTES = 20 * 1024 * 1024


def _convert(source: Path, destination: Path, quality: int) -> Path:
    with Image.open(source) as image:
        image.load()
        if image.mode != "RGB":
            # Flatten instead of dropping alpha, so transparent edges do not
            # come out black.
            flattened = Image.new("RGB", image.size, (255, 255, 255))
            flattened.paste(image, mask=image.getchannel("A") if "A" in image.getbands() else None)
            image = flattened
        if image.width > MAX_EDGE:
            height = round(image.height * MAX_EDGE / image.width)
            image = image.resize((MAX_EDGE, height), Image.Resampling.LANCZOS)

        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, format="JPEG", quality=quality, optimize=True, progressive=True)

    if destination.stat().st_size > MAX_BYTES:
        raise ValueError(f"Slide exceeds TikTok's 20MB limit: {destination}")
    return destination


def post_publish_dir(config: Config, post: Post) -> Path:
    return config.publish_dir / post.theme_slug / post.source_dir.name


def publish_post(config: Config, post: Post) -> list[Path]:
    """Write the carousel into the Pages tree as JPEG."""
    target_dir = post_publish_dir(config, post)
    if target_dir.exists():
        shutil.rmtree(target_dir)

    written: list[Path] = []
    for index, slide in enumerate(post.slides, start=1):
        written.append(_convert(slide, target_dir / f"{index:02d}{OUTPUT_SUFFIX}", config.jpeg_quality))
    return written


def public_urls(config: Config, post: Post) -> list[str]:
    if not config.pages_base_url:
        raise ValueError("PAGES_BASE_URL must be set before publishing")
    target_dir = post_publish_dir(config, post)
    names = sorted(path.name for path in target_dir.glob(f"*{OUTPUT_SUFFIX}"))
    prefix = f"{config.pages_base_url}/{post.theme_slug}/{post.source_dir.name}"
    return [f"{prefix}/{name}" for name in names]


def prune(config: Config, keep_keys: set[str]) -> list[Path]:
    """Drop carousels TikTok no longer needs to reach."""
    removed: list[Path] = []
    if not config.publish_dir.is_dir():
        return removed
    for theme_dir in sorted(p for p in config.publish_dir.iterdir() if p.is_dir()):
        for post_dir in sorted(p for p in theme_dir.iterdir() if p.is_dir()):
            if f"{theme_dir.name}/{post_dir.name}" in keep_keys:
                continue
            shutil.rmtree(post_dir)
            removed.append(post_dir)
        if not any(theme_dir.iterdir()):
            theme_dir.rmdir()
    return removed
