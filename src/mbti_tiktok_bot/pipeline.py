from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

from mbti_tiktok_bot.config import AppConfig
from mbti_tiktok_bot.models import CLOSER_SCENE_BODY, CLOSER_SCENE_TITLE, ContentPackage, Scene
from mbti_tiktok_bot.planner import SERIES_TOTAL_POSTS, build_daily_packages, build_template_package, maybe_polish_with_llm, persist_package
from mbti_tiktok_bot.visuals import generate_scene_assets

MAX_CONTENT_IMAGE_SLIDES = 10
SERIES_SUMMARY_FILE_NAME = "series_plan.json"
LEGACY_DAILY_SUMMARY_FILE_NAME = "daily_plan.json"
INVALID_FOLDER_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
CONTENT_OVERLAP_BLOCK_THRESHOLD = 0.8


@dataclass(slots=True)
class PipelineResult:
    output_dir: Path
    package_path: Path
    caption_path: Path
    title: str
    mbti_type: str
    daily_slot: int
    global_post_index: int
    media_paths: list[Path] = field(default_factory=list)
    media_kind: str = "image-carousel"


def _topic_folder_name(series_name: str) -> str:
    normalized = re.sub(r"\s+", " ", series_name).strip().strip(". ")
    sanitized = INVALID_FOLDER_CHARS_RE.sub("_", normalized)
    return sanitized or "untitled_topic"


def _topic_output_dir(output_root: Path, content_package: ContentPackage) -> Path:
    return output_root / _topic_folder_name(content_package.series_name)


def _bundle_output_dir(base_dir: Path, content_package: ContentPackage) -> Path:
    return base_dir / f"post_{content_package.series_post_number:02d}_{content_package.mbti_type}"


def _build_render_package(content_package: ContentPackage) -> ContentPackage:
    content_scenes = list(content_package.scenes)
    if content_scenes and content_scenes[0].title == content_package.title and content_scenes[0].body == content_package.hook:
        content_scenes = content_scenes[1:]

    thumbnail_scene = Scene(
        title=content_package.title,
        body=content_package.hook,
        duration_seconds=2.2,
    )
    closer_scene = Scene(
        title=CLOSER_SCENE_TITLE,
        body=CLOSER_SCENE_BODY,
        duration_seconds=2.2,
    )
    return replace(content_package, scenes=[thumbnail_scene, *content_scenes[:MAX_CONTENT_IMAGE_SLIDES], closer_scene])


def _carousel_image_paths(slides_dir: Path, scene_count: int) -> list[Path]:
    return [slides_dir / f"slide_{index + 1:02d}.png" for index in range(scene_count)]


def _summary_item(base_dir: Path, content_package: ContentPackage) -> dict[str, object]:
    return {
        "post_date": content_package.post_date,
        "title": content_package.title,
        "series_name": content_package.series_name,
        "format_name": content_package.format_name,
        "theme": content_package.theme,
        "mbti_type": content_package.mbti_type,
        "daily_slot": content_package.daily_slot,
        "series_post_number": content_package.series_post_number,
        "global_post_index": content_package.global_post_index,
        "output_dir": str(_bundle_output_dir(base_dir, content_package)),
    }


def _merge_summary_items(summary_path: Path, summary_items: list[dict[str, object]]) -> list[dict[str, object]]:
    merged_items: dict[str, dict[str, object]] = {}
    if summary_path.exists():
        existing_items = json.loads(summary_path.read_text(encoding="utf-8"))
        for item in existing_items:
            if not isinstance(item, dict):
                continue
            output_dir = str(item.get("output_dir") or "")
            if not output_dir:
                continue
            merged_items[output_dir] = item

    for item in summary_items:
        merged_items[str(item["output_dir"])] = item

    return sorted(
        merged_items.values(),
        key=lambda item: (
            str(item.get("post_date") or ""),
            int(item.get("global_post_index", 0)),
            str(item.get("output_dir", "")),
        ),
    )


def _similarity_text(text: str) -> str:
    return re.sub(r"\s+", "", text.casefold())


def _text_similarity(left: str, right: str) -> float:
    normalized_left = _similarity_text(left)
    normalized_right = _similarity_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    return SequenceMatcher(None, normalized_left, normalized_right).ratio()


def _package_body_text(content_package: ContentPackage) -> str:
    return "\n".join(
        [content_package.hook]
        + [f"{scene.title}\n{scene.body}" for scene in content_package.scenes]
    )


def _load_package(path: Path) -> ContentPackage | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        scenes = [Scene(**scene) for scene in data.get("scenes", [])]
        return ContentPackage(
            post_date=data.get("post_date", ""),
            mbti_type=data.get("mbti_type", ""),
            archetype_name=data.get("archetype_name", ""),
            group_name=data.get("group_name", ""),
            title=data.get("title", ""),
            series_name=data.get("series_name", ""),
            format_name=data.get("format_name", ""),
            theme=data.get("theme", ""),
            hook=data.get("hook", ""),
            narration=data.get("narration", ""),
            caption=data.get("caption", ""),
            hashtags=data.get("hashtags", []),
            global_post_index=int(data.get("global_post_index", 0)),
            daily_slot=int(data.get("daily_slot", 1)),
            series_post_number=int(data.get("series_post_number", 1)),
            series_total_posts=int(data.get("series_total_posts", SERIES_TOTAL_POSTS)),
            scenes=scenes,
        )
    except Exception:
        return None


def _iter_existing_packages(output_root: Path) -> list[tuple[Path, ContentPackage]]:
    if not output_root.exists():
        return []
    packages: list[tuple[Path, ContentPackage]] = []
    for package_path in output_root.glob("*/post_*/package.json"):
        package = _load_package(package_path)
        if package is not None:
            packages.append((package_path, package))
    return packages


def _assert_not_too_similar_to_existing_outputs(
    config: AppConfig,
    content_package: ContentPackage,
    output_dir: Path,
) -> None:
    current_package_path = (output_dir / "package.json").resolve()
    current_body = _package_body_text(content_package)
    for package_path, existing_package in _iter_existing_packages(config.output_dir):
        if package_path.resolve() == current_package_path:
            continue
        if existing_package.series_name == content_package.series_name:
            continue
        title_similarity = _text_similarity(content_package.series_name, existing_package.series_name)
        body_similarity = _text_similarity(current_body, _package_body_text(existing_package))
        if title_similarity >= CONTENT_OVERLAP_BLOCK_THRESHOLD or body_similarity >= CONTENT_OVERLAP_BLOCK_THRESHOLD:
            raise ValueError(
                "Generated package overlaps an existing package by 80% or more: "
                f"{content_package.title} vs {existing_package.title} ({package_path})"
            )


def _write_series_summary(base_dir: Path, packages: list[ContentPackage]) -> Path:
    summary_path = base_dir / SERIES_SUMMARY_FILE_NAME
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_items = [_summary_item(base_dir, package) for package in packages]
    summary_items = _merge_summary_items(summary_path, summary_items)

    summary_path.write_text(
        json.dumps(summary_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary_path


def _render_bundle(content_package: ContentPackage, config: AppConfig, output_dir: Path) -> PipelineResult:
    content_package = maybe_polish_with_llm(content_package, config)
    _assert_not_too_similar_to_existing_outputs(config, content_package, output_dir)
    package_path = persist_package(content_package, output_dir)
    render_package = _build_render_package(content_package)

    slides_dir = output_dir / "slides"
    generate_scene_assets(render_package, config, slides_dir)
    media_paths = _carousel_image_paths(slides_dir, len(render_package.scenes))
    return PipelineResult(
        output_dir=output_dir,
        package_path=package_path,
        caption_path=output_dir / "caption.txt",
        title=content_package.title,
        mbti_type=content_package.mbti_type,
        daily_slot=content_package.daily_slot,
        global_post_index=content_package.global_post_index,
        media_paths=media_paths,
    )


def render_content_package(
    content_package: ContentPackage,
    config: AppConfig,
    output_dir: Path,
) -> PipelineResult:
    return _render_bundle(content_package, config, output_dir)


def refresh_existing_visuals(
    config: AppConfig,
    topic: str | None = None,
) -> list[PipelineResult]:
    """Re-render existing packages without changing their copy or series state."""
    refreshed: list[PipelineResult] = []
    for package_path, content_package in sorted(_iter_existing_packages(config.output_dir), key=lambda item: str(item[0])):
        output_dir = package_path.parent
        if topic and output_dir.parent.name != topic:
            continue
        render_package = _build_render_package(content_package)
        slides_dir = output_dir / "slides"
        generate_scene_assets(render_package, config, slides_dir)
        media_paths = _carousel_image_paths(slides_dir, len(render_package.scenes))
        refreshed.append(
            PipelineResult(
                output_dir=output_dir,
                package_path=package_path,
                caption_path=output_dir / "caption.txt",
                title=content_package.title,
                mbti_type=content_package.mbti_type,
                daily_slot=content_package.daily_slot,
                global_post_index=content_package.global_post_index,
                media_paths=media_paths,
            )
        )
    return refreshed


def load_existing_visual_results(
    config: AppConfig,
    topic: str | None = None,
) -> list[PipelineResult]:
    """Load already-rendered visual results without regenerating any files."""
    results: list[PipelineResult] = []
    for package_path, content_package in sorted(_iter_existing_packages(config.output_dir), key=lambda item: str(item[0])):
        output_dir = package_path.parent
        if topic and output_dir.parent.name != topic:
            continue
        media_paths = sorted((output_dir / "slides").glob("slide_*.png"))
        if not media_paths:
            continue
        results.append(
            PipelineResult(
                output_dir=output_dir,
                package_path=package_path,
                caption_path=output_dir / "caption.txt",
                title=content_package.title,
                mbti_type=content_package.mbti_type,
                daily_slot=content_package.daily_slot,
                global_post_index=content_package.global_post_index,
                media_paths=media_paths,
            )
        )
    return results


def build_daily_bundle(
    target_date: date,
    config: AppConfig,
    explicit_mbti: str | None = None,
    explicit_format: str | None = None,
) -> PipelineResult:
    content_package = build_template_package(
        target_date=target_date,
        config=config,
        explicit_mbti=explicit_mbti,
        explicit_format=explicit_format,
    )
    base_dir = _topic_output_dir(config.output_dir, content_package)
    _write_series_summary(base_dir, [content_package])
    output_dir = _bundle_output_dir(base_dir, content_package)
    return render_content_package(content_package, config, output_dir)


def build_daily_bundles(
    target_date: date,
    config: AppConfig,
    explicit_mbti: str | None = None,
    explicit_format: str | None = None,
    count: int | None = None,
    start_post_index: int | None = None,
    append_summary: bool = False,
) -> list[PipelineResult]:
    packages = build_daily_packages(
        target_date=target_date,
        config=config,
        count=count,
        start_post_index=start_post_index,
        explicit_format=explicit_format,
        explicit_mbti=explicit_mbti,
    )
    packages_by_base_dir: dict[Path, list[ContentPackage]] = {}
    for package in packages:
        base_dir = _topic_output_dir(config.output_dir, package)
        packages_by_base_dir.setdefault(base_dir, []).append(package)

    for base_dir, grouped_packages in packages_by_base_dir.items():
        _write_series_summary(base_dir, grouped_packages)

    results = [
        render_content_package(
            package,
            config,
            _bundle_output_dir(_topic_output_dir(config.output_dir, package), package),
        )
        for package in packages
    ]
    return results


def _summary_paths(output_dir: Path) -> list[Path]:
    if not output_dir.exists():
        return []

    summary_paths: list[Path] = []
    for child in output_dir.iterdir():
        if not child.is_dir():
            continue
        series_summary_path = child / SERIES_SUMMARY_FILE_NAME
        legacy_summary_path = child / LEGACY_DAILY_SUMMARY_FILE_NAME
        if series_summary_path.exists():
            summary_paths.append(series_summary_path)
        elif legacy_summary_path.exists():
            summary_paths.append(legacy_summary_path)
    return summary_paths


def load_daily_results(target_date: date, config: AppConfig) -> list[PipelineResult]:
    target_date_str = target_date.isoformat()
    results: list[PipelineResult] = []
    for summary_path in _summary_paths(config.output_dir):
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        for item in data:
            item_date = str(item.get("post_date") or "")
            if not item_date and summary_path.name == LEGACY_DAILY_SUMMARY_FILE_NAME:
                item_date = summary_path.parent.name
            if item_date != target_date_str:
                continue

            output_dir = Path(item["output_dir"])
            if not output_dir.exists():
                continue
            slides_dir = output_dir / "slides"
            media_paths = sorted(slides_dir.glob("slide_*.png"))
            results.append(
                PipelineResult(
                    output_dir=output_dir,
                    package_path=output_dir / "package.json",
                    caption_path=output_dir / "caption.txt",
                    title=item["title"],
                    mbti_type=item["mbti_type"],
                    daily_slot=int(item.get("daily_slot", 1)),
                    global_post_index=int(item["global_post_index"]),
                    media_paths=media_paths,
                )
            )

    results.sort(key=lambda result: (result.global_post_index, str(result.output_dir)))
    return results
