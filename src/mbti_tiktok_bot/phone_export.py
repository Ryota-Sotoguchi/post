from __future__ import annotations

import os
import stat
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PIL import Image

from mbti_tiktok_bot.config import AppConfig
from mbti_tiktok_bot.pipeline import PipelineResult

PHONE_EXPORT_IMAGE_SIZE = (1080, 1920)


@dataclass(slots=True)
class PhoneExportResult:
    export_dir: Path
    post_count: int


def _retry_remove_with_write_access(func, path, _excinfo) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _remove_directory_if_present(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onexc=_retry_remove_with_write_access)


def _phone_export_image_size(config: AppConfig) -> tuple[int, int]:
    return (config.video_width, config.video_height)


def _validate_phone_image(path: Path, expected_size: tuple[int, int]) -> None:
    with Image.open(path) as image:
        if image.size != expected_size:
            raise ValueError(f"Phone export image must be {expected_size[0]}x{expected_size[1]}: {path} is {image.size[0]}x{image.size[1]}")
        if image.mode != "RGB":
            raise ValueError(f"Phone export image must be RGB without transparency: {path} is {image.mode}")


def _write_phone_safe_png(source: Path, destination: Path, expected_size: tuple[int, int]) -> None:
    _validate_phone_image(source, expected_size)
    with Image.open(source) as image:
        image.load()
        flattened = Image.new("RGB", expected_size, (255, 255, 255))
        flattened.paste(image)
        flattened.save(destination, format="PNG", optimize=False, compress_level=1)
    os.utime(destination, None)


def _copy_post_images(config: AppConfig, result: PipelineResult, destination_root: Path) -> Path:
    destination = destination_root / result.output_dir.name
    if destination.exists():
        shutil.rmtree(destination, onexc=_retry_remove_with_write_access)
    destination.mkdir(parents=True, exist_ok=True)
    expected_size = _phone_export_image_size(config)
    for media_path in result.media_paths:
        # Resolve to absolute path in case it's relative
        abs_media_path = media_path if media_path.is_absolute() else media_path.resolve()
        if abs_media_path.exists():
            destination_path = destination / abs_media_path.name
            _write_phone_safe_png(abs_media_path, destination_path, expected_size)
    return destination


def _topic_export_dir(config: AppConfig, result: PipelineResult) -> Path:
    return config.phone_export_dir / result.output_dir.parent.name


def export_daily_results_to_phone(
    config: AppConfig,
    target_date: date,
    results: list[PipelineResult],
    reset_export_dir: bool = True,
) -> PhoneExportResult:
    if not results:
        raise ValueError("No results available to export")

    export_dir = config.phone_export_dir
    config.phone_export_dir.mkdir(parents=True, exist_ok=True)
    _remove_directory_if_present(config.phone_export_dir / "latest")

    prepared_export_dirs = {_topic_export_dir(config, result) for result in results}
    if reset_export_dir:
        # A refresh must be a true clean rebuild. Remove every affected topic
        # before recreating any of them so sync clients observe the deletion
        # phase instead of treating the operation as an in-place overwrite.
        for topic_export_dir in prepared_export_dirs:
            _remove_directory_if_present(topic_export_dir)
        stale_export_dirs = [path for path in prepared_export_dirs if path.exists()]
        if stale_export_dirs:
            stale_paths = ", ".join(str(path) for path in sorted(stale_export_dirs))
            raise RuntimeError(f"Failed to clear phone export directories: {stale_paths}")

    for topic_export_dir in prepared_export_dirs:
        topic_export_dir.mkdir(parents=True, exist_ok=True)

    for result in results:
        topic_export_dir = _topic_export_dir(config, result)
        _copy_post_images(config, result, topic_export_dir)

    if len(prepared_export_dirs) == 1:
        export_dir = next(iter(prepared_export_dirs))

    return PhoneExportResult(
        export_dir=export_dir,
        post_count=len(results),
    )
