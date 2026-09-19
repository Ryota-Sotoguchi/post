"""Building blocks the styles compose: layers, the character, hollow type.

All positions are logical; device conversion happens here.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

from PIL import Image, ImageChops

from mbti_tiktok_bot.design import effects as fx
from mbti_tiktok_bot.design import text as T
from mbti_tiktok_bot.design.core import HEIGHT, WIDTH, Context
from mbti_tiktok_bot.visuals import ScaledDraw


@dataclass(slots=True)
class Layers:
    """One slide, as the four layers the pipeline records.

    `order` is the compositing order, so a style can put the character behind a
    glass panel. `base` is an optional 1x image laid under everything after the
    downsample - photographs smaller than the canvas go there, so they are not
    enlarged twice.
    """

    background: Image.Image
    accent: Image.Image
    character: Image.Image
    text: Image.Image
    base: Image.Image | None = None
    order: tuple[str, ...] = ("background", "accent", "character", "text")

    def stack(self) -> list[Image.Image]:
        return [getattr(self, name) for name in self.order]


def blank(ctx: Context) -> Image.Image:
    return Image.new("RGBA", ctx.device, (0, 0, 0, 0))


def canvas(image: Image.Image, ctx: Context) -> ScaledDraw:
    return ScaledDraw(image, ctx.scale)


# --- the character ----------------------------------------------------------


@lru_cache(maxsize=64)
def load_subject(path: str) -> Image.Image:
    with Image.open(path) as opened:
        return fx.trim(opened.convert("RGBA"))


def subject(
    ctx: Context,
    height: float,
    treat: Callable[[Image.Image], Image.Image] | None = None,
    max_width: float | None = None,
) -> tuple[Image.Image, tuple[int, int]]:
    """The character scaled to a logical height, then treated.

    Scaling is to a height, not into a box: the old renderer used
    Image.thumbnail, which is contain-fit, and a square figure in a tall box
    came out at 6.6% of the frame. Returns the treated image and the device
    size of the figure inside it, so a treatment's padding can be allowed for.
    """
    device_height = ctx.px(height)
    figure = fx.fit_height(ctx.subject, device_height)
    if max_width is not None and figure.width > ctx.px(max_width):
        figure = fx.fit_width(figure, ctx.px(max_width))
    size = figure.size
    return (treat(figure) if treat else figure), size


def paste(layer: Image.Image, ctx: Context, treated: Image.Image, figure_size: tuple[int, int],
          anchor: tuple[float, float], at: str = "bottom") -> tuple[float, float, float, float]:
    """Place a treated figure so the figure itself - not its padding - sits on anchor.

    at="bottom" puts the figure's bottom centre on anchor; "center" its centre.
    Returns the figure's logical box.
    """
    margin_x = (treated.width - figure_size[0]) / 2
    margin_y = (treated.height - figure_size[1]) / 2
    ax, ay = ctx.px(anchor[0]), ctx.px(anchor[1])
    left = ax - figure_size[0] / 2
    top = ay - figure_size[1] if at == "bottom" else ay - figure_size[1] / 2
    layer.alpha_composite(treated, (round(left - margin_x), round(top - margin_y)))
    s = ctx.scale
    return (left / s, top / s, (left + figure_size[0]) / s, (top + figure_size[1]) / s)


# --- type effects -----------------------------------------------------------


def hollow(layer: Image.Image, ctx: Context, block: T.Block, x: float, y: float,
           color: tuple[int, int, int, int], stroke: int = 3, fill_alpha: int = 0) -> None:
    """Outline-only type: the stroked glyphs minus the glyphs themselves."""
    outer = Image.new("L", layer.size, 0)
    inner = Image.new("L", layer.size, 0)
    T.draw(ScaledDraw(outer, ctx.scale), block, x, y, 255, stroke=stroke, stroke_fill=255)
    T.draw(ScaledDraw(inner, ctx.scale), block, x, y, 255)
    ring = ImageChops.subtract(outer, inner).point(lambda value: value * color[3] // 255)
    paint = Image.new("RGBA", layer.size, color[:3] + (255,))
    paint.putalpha(ring)
    if fill_alpha:
        fill = Image.new("RGBA", layer.size, color[:3] + (255,))
        fill.putalpha(inner.point(lambda value: value * fill_alpha // 255))
        layer.alpha_composite(fill)
    layer.alpha_composite(paint)


def arrow(draw, x: float, y: float, length: float, color, width: float = 4) -> None:
    """A drawn right arrow. Bebas Neue and Anton have no → glyph, so it came out as a box."""
    head = width * 3.2
    draw.line((x, y, x + length, y), fill=color, width=round(width))
    draw.line((x + length - head, y - head, x + length, y), fill=color, width=round(width))
    draw.line((x + length - head, y + head, x + length, y), fill=color, width=round(width))


def swipe_cue(draw, x_right: float, y: float, color, label: str = "SWIPE", size: int = 38) -> float:
    """Right-aligned 'SWIPE ⟶' ending at x_right. Returns its height."""
    block = T.single(label, "label", size, tracking_em=0.16)
    length = size * 1.3
    gap = size * 0.35
    left = x_right - block.width - gap - length
    T.draw(draw, block, left, y, color)
    arrow(draw, left + block.width + gap, y + T.ink_height(block) / 2, length, color, width=max(size / 11, 2))
    return T.ink_height(block)


def vscrim(ctx: Context, top: float, bottom: float, color: str, alpha_top: int, alpha_bottom: int) -> Image.Image:
    """A vertical fade of one colour between two logical heights."""
    layer = blank(ctx)
    height = max(ctx.px(bottom) - ctx.px(top), 2)
    ramp = fx.linear((ctx.device[0], height), fx.rgba(color, alpha_top), fx.rgba(color, alpha_bottom), angle=90)
    layer.alpha_composite(ramp, (0, ctx.px(top)))
    if bottom < HEIGHT:
        layer.alpha_composite(fx.solid((ctx.device[0], ctx.device[1] - ctx.px(bottom)), fx.rgba(color, alpha_bottom)), (0, ctx.px(bottom)))
    return layer


def glass(layer: Image.Image, ctx: Context, background: Image.Image, box: tuple[float, float, float, float],
          radius: float, tint: tuple[int, int, int, int], border: tuple[int, int, int, int] | None, blur: float = 28) -> None:
    """A frosted panel over the background."""
    device_box = ctx.box(box)
    layer.alpha_composite(fx.frosted(background, device_box, ctx.px(radius), ctx.px(blur), tint))
    if border is not None:
        canvas(layer, ctx).rounded_rectangle(box, radius=radius, outline=border, width=2)


def arch_mask(ctx: Context, box: tuple[float, float, float, float]) -> Image.Image:
    """A device-size mask of an arch: a rectangle with a semicircular top."""
    left, top, right, bottom = box
    radius = (right - left) / 2
    mask = Image.new("L", ctx.device, 0)
    draw = ScaledDraw(mask, ctx.scale)
    draw.ellipse((left, top, right, top + radius * 2), fill=255)
    draw.rectangle((left, top + radius, right, bottom), fill=255)
    return mask


def framed(ctx: Context, box: tuple[float, float, float, float], mask: Image.Image, field: tuple[int, int, int, int],
           height: float, top_inset: float, treat=None, x_center: float | None = None) -> Image.Image:
    """The character inside a shaped window, cropped by the window's edge.

    The figure is sized to overflow the window and clipped, so it reads as a
    portrait cut into the page rather than a sticker placed on it.
    """
    left, top, right, bottom = box
    layer = blank(ctx)
    ScaledDraw(layer, ctx.scale).rectangle(box, fill=field)
    figure_layer = blank(ctx)
    treated, size = subject(ctx, height, treat)
    center = x_center if x_center is not None else (left + right) / 2
    paste(figure_layer, ctx, treated, size, (center, top + top_inset + height), at="bottom")
    layer.alpha_composite(figure_layer)
    clipped = Image.new("RGBA", ctx.device, (0, 0, 0, 0))
    clipped.paste(layer, (0, 0), mask)
    return clipped


def asset(path: Path) -> Image.Image | None:
    if not path.exists():
        return None
    with Image.open(path) as opened:
        return opened.convert("RGB")


def logical_size() -> tuple[int, int]:
    return (WIDTH, HEIGHT)
