"""Render a carousel with one of the style packs.

The style is chosen per topic, from the same topic seed the palette uses, so
all sixteen MBTI types of a series come out in one look; only the character
and the type name differ between them.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import ModuleType

from mbti_tiktok_bot.config import AppConfig
from mbti_tiktok_bot.design.core import HEIGHT, WIDTH, Context, slides_for
from mbti_tiktok_bot.design.kit import load_subject
from mbti_tiktok_bot.design.styles import STYLES
from mbti_tiktok_bot.models import ContentPackage, SceneRenderAssets
from mbti_tiktok_bot.visuals import (
    RENDER_SCALE,
    _compose_scene,
    _palette,
    _resolve_illustration_path,
    _save_layer,
    _seed_choice,
    _visual_identity,
    _visual_seed,
)

STYLE_ENV = "MBTI_STYLE"


def style_name(package: ContentPackage) -> str:
    names = sorted(STYLES)
    return names[_seed_choice(_visual_seed(package, include_mbti=False), "style", len(names))]


def _context(package: ContentPackage, config: AppConfig) -> Context:
    source = _resolve_illustration_path(config, package.mbti_type)
    if source is None:
        # Substituting a generated figure for a missing type is exactly what
        # the provided-material policy rules out.
        raise FileNotFoundError(
            f"Provided MBTI material is required for {package.mbti_type}; "
            f"place it in {config.official_images_dir} or {config.assets_dir}"
        )
    return Context(
        package=package,
        config=config,
        palette=_palette(package),
        topic_seed=_visual_seed(package, include_mbti=False),
        subject=load_subject(str(source)),
        scale=RENDER_SCALE,
    )


def render_carousel(
    package: ContentPackage,
    config: AppConfig,
    slides_dir: Path,
    style: str | None = None,
) -> list[SceneRenderAssets]:
    if slides_dir.exists():
        shutil.rmtree(slides_dir)
    slides_dir.mkdir(parents=True, exist_ok=True)
    render_dir = slides_dir.parent / "_render"
    shutil.rmtree(render_dir, ignore_errors=True)
    keep = config.keep_render_layers

    ctx = _context(package, config)
    chosen = style or style_name(package)
    module: ModuleType = STYLES[chosen]

    identity = _visual_identity(package)
    identity.update({"version": 6, "style": chosen})
    (slides_dir.parent / "visual_identity.json").write_text(
        json.dumps(identity, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    assets: list[SceneRenderAssets] = []
    for slide in slides_for(package):
        layers = getattr(module, slide.kind)(ctx, slide)
        paths = {
            name: render_dir / f"{name}_{slide.index + 1:02d}.png"
            for name in ("background", "accent", "character", "text")
        }
        if keep:
            for name, path in paths.items():
                _save_layer(getattr(layers, name), path)
        _compose_scene(
            layers.stack(),
            (WIDTH, HEIGHT),
            slides_dir / f"slide_{slide.index + 1:02d}.png",
            base=layers.base,
        )
        assets.append(
            SceneRenderAssets(
                background_path=paths["background"],
                text_overlay_path=paths["text"],
                character_overlay_path=paths["character"],
                accent_overlay_path=paths["accent"],
            )
        )
    return assets
