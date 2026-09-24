"""Render a post: pick its look and palette, lay out each card, compose, save."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from mbti_tiktok_bot.catalog import GROUP_PALETTE_VARIANTS
from mbti_tiktok_bot.config import AppConfig
from mbti_tiktok_bot.design.cards import LAYOUTS
from mbti_tiktok_bot.design.core import HEIGHT, WIDTH, Context
from mbti_tiktok_bot.design.looks import LOOK_ORDER, LOOKS
from mbti_tiktok_bot.formats.model import Post
from mbti_tiktok_bot.models import SceneRenderAssets
from mbti_tiktok_bot.visuals import RENDER_SCALE, _compose_scene, _save_layer, _seed_choice

GROUPS = ("分析家", "外交官", "番人", "探検家")


def subject_of(post: Post) -> str:
    """What the post belongs to: its series, or itself when it is a one-off.

    Everything drawn from the same subject shares a seed, so the sixteen posts
    of a series come out in one look, one palette and one arrangement.
    """
    return post.series or post.key


def post_seed(post: Post) -> int:
    return int.from_bytes(hashlib.sha256(subject_of(post).encode("utf-8")).digest()[:8], "big")


def look_name(post: Post) -> str:
    """Looks rotate with the series, so consecutive series never look alike."""
    if post.series_index:
        return LOOK_ORDER[(post.series_index - 1) % len(LOOK_ORDER)]
    return LOOK_ORDER[_seed_choice(post_seed(post), "look", len(LOOK_ORDER))]


def palette_for(post: Post):
    """One colour scheme per subject, the way a magazine feature has one.

    It used to be the focus type's own group, which meant the sixteen posts of
    a series arrived in four different colour schemes.
    """
    seed = post_seed(post)
    group = GROUPS[_seed_choice(seed, "group", len(GROUPS))]
    variants = GROUP_PALETTE_VARIANTS[group]
    return variants[_seed_choice(seed, "palette", len(variants))]


def render_post(post: Post, config: AppConfig, slides_dir: Path, look: str | None = None) -> list[SceneRenderAssets]:
    if slides_dir.exists():
        shutil.rmtree(slides_dir)
    slides_dir.mkdir(parents=True, exist_ok=True)
    render_dir = slides_dir.parent / "_render"
    shutil.rmtree(render_dir, ignore_errors=True)
    keep = config.keep_render_layers

    ctx = Context(config=config, palette=palette_for(post), seed=post_seed(post), scale=RENDER_SCALE)
    chosen = look or look_name(post)
    style = LOOKS[chosen](ctx)
    (slides_dir.parent / "visual_identity.json").write_text(
        json.dumps({"version": 8, "look": chosen, "palette": ctx.palette.name, "format": post.format,
                    "series": post.series, "series_index": post.series_index,
                    "series_position": post.series_position, "render_scale": RENDER_SCALE},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    assets: list[SceneRenderAssets] = []
    for index, card in enumerate(post.cards, start=1):
        layers = LAYOUTS[card.kind](style, post, card)
        paths = {name: render_dir / f"{name}_{index:02d}.png" for name in ("background", "accent", "character", "text")}
        if keep:
            for name, path in paths.items():
                _save_layer(getattr(layers, name), path)
        _compose_scene(layers.stack(), (WIDTH, HEIGHT), slides_dir / f"slide_{index:02d}.png", base=layers.base)
        assets.append(SceneRenderAssets(
            background_path=paths["background"],
            text_overlay_path=paths["text"],
            character_overlay_path=paths["character"],
            accent_overlay_path=paths["accent"],
        ))
    return assets
