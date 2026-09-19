"""NEON - dark, luminous, loud. The "cool" direction.

Near-black ground lit by two large coloured glows, the MBTI letters as giant
outline type behind the character, the character rim-lit in the partner neon.
Copy is white over a fade to black; body text sits on frosted glass.

Where copy and character share a slide, the copy is laid out first, from the
bottom of the safe area up, and the character is sized into what is left. That
is what keeps a long title off the character's face.
"""

from __future__ import annotations

from mbti_tiktok_bot.design import effects as fx
from mbti_tiktok_bot.design import text as T
from mbti_tiktok_bot.design.core import (
    HEIGHT,
    SAFE_BOTTOM,
    SAFE_LEFT,
    SAFE_RIGHT,
    SAFE_TOP,
    SAFE_WIDTH,
    WIDTH,
    Chip,
    Context,
    Slide,
    chip_flow,
    chip_row,
    neon_partner,
    vivid,
)
from mbti_tiktok_bot.design.kit import Layers, blank, canvas, glass, hollow, paste, subject, swipe_cue, vscrim

WHITE = (255, 255, 255, 255)
SOFT_WHITE = (255, 255, 255, 222)


def colors(ctx: Context) -> dict[str, str]:
    neon = vivid(ctx.palette.accent, 0.82, 1.0)
    return {
        "ink": fx.mix(ctx.palette.background, "#05040a", 0.88),
        "neon": neon,
        "neon2": neon_partner(neon),
        "soft": fx.mix(ctx.palette.light, "#ffffff", 0.3),
    }


def background(ctx: Context):
    if "neon.bg" in ctx.cache:
        return ctx.cache["neon.bg"]
    c = colors(ctx)
    w, h = ctx.device
    s = ctx.scale
    image = fx.aurora(
        ctx.device,
        fx.rgba(c["ink"]),
        [
            ((w * 0.88, h * 0.22), 780 * s, fx.rgba(c["neon"], 140)),
            ((w * 0.06, h * 0.78), 840 * s, fx.rgba(c["neon2"], 120)),
            ((w * 0.62, h * 0.60), 380 * s, fx.rgba(c["neon2"], 60)),
        ],
    )
    # A faint dot grid gives the dark field something to sit on.
    grid = canvas(image, ctx)
    for gy in range(96, HEIGHT, 64):
        for gx in range(48, WIDTH, 64):
            grid.ellipse((gx - 1.3, gy - 1.3, gx + 1.3, gy + 1.3), fill=(255, 255, 255, 20))
    image = fx.grain(image, 0.05, seed=ctx.topic_seed)
    ctx.cache["neon.bg"] = image
    return image


def _treat(ctx: Context, strength: float = 1.0):
    c = colors(ctx)

    def treat(figure):
        lit = fx.rim(figure, fx.rgba(c["neon2"], 235), (ctx.px(-10), ctx.px(-4)), ctx.px(5))
        return fx.glow(lit, ctx.px(34), fx.rgba(c["neon"], int(115 * strength)))

    return treat


def _ghost(layer, ctx: Context, y: float, alpha: int = 170, size: int = 560) -> None:
    c = colors(ctx)
    block = T.fit_single(ctx.package.mbti_type, "display", WIDTH - 40, size, 200, tracking_em=0.01)
    hollow(layer, ctx, block, (WIDTH - block.width) / 2, y, fx.rgba(c["neon"], alpha), stroke=3, fill_alpha=24)


def _top_row(text_layer, ctx: Context, cue: str = "SWIPE") -> float:
    """The type chip on the left, the swipe cue on the right. Returns the row height."""
    c = colors(ctx)
    draw = canvas(text_layer, ctx)
    package = ctx.package
    chip = Chip(f"{package.mbti_type}・{package.archetype_name}", "jp-bold", 28,
                fill=fx.rgba(c["neon"], 240), color=fx.rgba(c["ink"]), tracking_em=0.04)
    _, height = chip_row(draw, [chip], SAFE_LEFT, SAFE_TOP, SAFE_WIDTH - 220)
    cue_height = T.ink_height(T.single(cue, "label", 38))
    swipe_cue(draw, SAFE_RIGHT, SAFE_TOP + (height - cue_height) / 2, SOFT_WHITE, cue)
    return height


def _title(text: str, width: float, height: float, base: int, minimum: int, lines: int = 3) -> T.Block:
    return T.fit(text, "jp-black", width, height, base, minimum, leading=1.07, tracking_em=-0.02,
                 max_lines=lines, strict=True)


def cover(ctx: Context, slide: Slide) -> Layers:
    c = colors(ctx)
    bg = background(ctx).copy()
    accent = blank(ctx)
    _ghost(accent, ctx, 250)
    character = blank(ctx)
    treated, size = subject(ctx, 1180, _treat(ctx), max_width=980)
    paste(character, ctx, treated, size, (WIDTH * 0.60, 1660))

    text = blank(ctx)
    # The fade sits above the character so the headline reads over it.
    text.alpha_composite(vscrim(ctx, 860, 1520, c["ink"], 0, 236))
    _top_row(text, ctx)
    draw = canvas(text, ctx)
    hook = T.fit(ctx.package.hook, "jp-medium", SAFE_WIDTH, 250, 44, 30, leading=1.5, max_lines=4)
    title = _title(slide.title, SAFE_WIDTH, 440, 132, 68)
    hook_top = SAFE_BOTTOM - hook.height
    title_top = hook_top - 44 - title.height
    draw.rounded_rectangle((SAFE_LEFT, title_top - 46, SAFE_LEFT + 72, title_top - 36), radius=5, fill=fx.rgba(c["neon"]))
    T.draw(draw, title, SAFE_LEFT, title_top, WHITE, shadow=(0, 6, (0, 0, 0, 130)))
    T.draw(draw, hook, SAFE_LEFT, hook_top, SOFT_WHITE)
    return Layers(bg, accent, character, text)


def body(ctx: Context, slide: Slide) -> Layers:
    variant = (slide.number - 1) % 3
    return (_body_index, _body_hero, _body_statement)[variant](ctx, slide)


def _counter(slide: Slide) -> str:
    return f"{slide.number:02d} / {slide.total:02d}"


def _chips(ctx: Context, slide: Slide, key: str = "neon") -> list[Chip]:
    c = colors(ctx)
    return [Chip(label, "jp-bold", 28, fill=fx.rgba(c[key], 40), color=WHITE, outline=fx.rgba(c[key], 220),
                 tracking_em=0.02) for label in slide.chips]


def _copy_stack(draw, ctx: Context, slide: Slide, left: float, width: float, bottom: float,
                body_base: int = 46, draw_it: bool = True) -> float:
    """Chips then body text, bottom-aligned at `bottom`. Returns the top."""
    chips = _chips(ctx, slide)
    chip_height = chip_flow(draw, chips, 0, 0, width, draw=False) if chips else 0
    block = T.fit(slide.body, "jp-medium", width, 440, body_base, 34, leading=1.6) if slide.body else None
    body_top = bottom - (block.height if block else 0)
    chips_top = body_top - (chip_height + 28 if chips and block else chip_height)
    if draw_it:
        if chips:
            chip_flow(draw, chips, left, chips_top, width)
        if block:
            T.draw(draw, block, left, body_top, SOFT_WHITE)
    return chips_top


def _body_index(ctx: Context, slide: Slide) -> Layers:
    """Giant outline number, the statement under it, copy on glass, character behind."""
    c = colors(ctx)
    bg = background(ctx).copy()
    accent = blank(ctx)
    character = blank(ctx)
    treated, size = subject(ctx, 900, _treat(ctx, 0.8), max_width=760)
    paste(character, ctx, treated, size, (WIDTH * 0.74, 1720))

    text = blank(ctx)
    draw = canvas(text, ctx)
    number = T.single(f"{slide.number:02d}", "display", 300)
    hollow(accent, ctx, number, SAFE_LEFT - 6, SAFE_TOP, fx.rgba(c["neon"], 230), stroke=3, fill_alpha=30)
    total = T.single(f"/ {slide.total:02d}", "label", 60, tracking_em=0.06)
    T.draw(draw, total, SAFE_LEFT + number.width + 18, SAFE_TOP + number.height - T.ink_height(total), (255, 255, 255, 150))
    title_top = SAFE_TOP + number.height + 48
    title = _title(slide.title, SAFE_WIDTH, 330, 116, 64)
    T.draw(draw, title, SAFE_LEFT, title_top, WHITE, shadow=(0, 5, (0, 0, 0, 110)))

    left, right = SAFE_LEFT - 8, SAFE_RIGHT + 16
    inner_left, inner_width = left + 44, right - left - 88
    panel_top = title_top + title.height + 56
    content_top = _copy_stack(draw, ctx, slide, inner_left, inner_width, 0, draw_it=False)
    content_height = -content_top
    panel_bottom = min(panel_top + content_height + 96, SAFE_BOTTOM)
    glass(accent, ctx, background(ctx), (left, panel_top, right, panel_bottom), 40,
          (255, 255, 255, 22), fx.rgba(c["soft"], 70))
    _copy_stack(draw, ctx, slide, inner_left, inner_width, panel_bottom - 48)
    return Layers(bg, accent, character, text, order=("background", "character", "accent", "text"))


def _body_hero(ctx: Context, slide: Slide) -> Layers:
    """The character as the hero across the top half; the copy underneath."""
    c = colors(ctx)
    bg = background(ctx).copy()
    accent = blank(ctx)
    text = blank(ctx)
    draw = canvas(text, ctx)

    copy_top = _copy_stack(draw, ctx, slide, SAFE_LEFT, SAFE_WIDTH, SAFE_BOTTOM, body_base=44, draw_it=False)
    title = _title(slide.title, SAFE_WIDTH, 300, 110, 60, lines=2)
    title_top = copy_top - 40 - title.height
    counter = Chip(_counter(slide), "label", 38, fill=fx.rgba(c["neon"], 240), color=fx.rgba(c["ink"]),
                   tracking_em=0.1, pad_x=0.7)
    counter_top = title_top - 32 - counter.height

    number = T.single(f"{slide.number:02d}", "display", 640)
    hollow(accent, ctx, number, (WIDTH - number.width) / 2, SAFE_TOP - 20, fx.rgba(c["neon2"], 110), stroke=2, fill_alpha=16)
    character = blank(ctx)
    room = counter_top - 30 - (SAFE_TOP + 20)
    treated, size = subject(ctx, max(min(room, 1000), 420), _treat(ctx), max_width=900)
    paste(character, ctx, treated, size, (WIDTH / 2, counter_top - 30))

    text.alpha_composite(vscrim(ctx, counter_top - 120, counter_top + 60, c["ink"], 0, 200))
    chip_row(draw, [counter], SAFE_LEFT, counter_top, SAFE_WIDTH)
    T.draw(draw, title, SAFE_LEFT, title_top, WHITE, shadow=(0, 5, (0, 0, 0, 120)))
    _copy_stack(draw, ctx, slide, SAFE_LEFT, SAFE_WIDTH, SAFE_BOTTOM, body_base=44)
    return Layers(bg, accent, character, text)


def _body_statement(ctx: Context, slide: Slide) -> Layers:
    """The statement is the slide; the character small and glowing above it."""
    c = colors(ctx)
    bg = background(ctx).copy()
    accent = blank(ctx)
    number = T.single(f"{slide.number:02d}", "display", 620)
    hollow(accent, ctx, number, WIDTH - number.width + 40, 560, fx.rgba(c["neon2"], 90), stroke=2, fill_alpha=14)

    character = blank(ctx)
    treated, size = subject(ctx, 560, _treat(ctx), max_width=520)
    paste(character, ctx, treated, size, (WIDTH * 0.72, SAFE_TOP + 560))

    text = blank(ctx)
    draw = canvas(text, ctx)
    counter = T.single(_counter(slide), "label", 46, tracking_em=0.14)
    T.draw(draw, counter, SAFE_LEFT, SAFE_TOP, fx.rgba(c["neon"]))
    title = _title(slide.title, SAFE_WIDTH, 460, 148, 72)
    copy_top = _copy_stack(draw, ctx, slide, SAFE_LEFT, SAFE_WIDTH, SAFE_BOTTOM, draw_it=False)
    title_top = copy_top - 56 - title.height
    accent.alpha_composite(vscrim(ctx, title_top - 240, title_top + 120, c["ink"], 0, 170))
    draw.rounded_rectangle((SAFE_LEFT, title_top - 40, SAFE_LEFT + 96, title_top - 30), radius=5, fill=fx.rgba(c["neon2"]))
    T.draw(draw, title, SAFE_LEFT, title_top, WHITE, shadow=(0, 6, (0, 0, 0, 140)))
    _copy_stack(draw, ctx, slide, SAFE_LEFT, SAFE_WIDTH, SAFE_BOTTOM)
    return Layers(bg, accent, character, text)


def closer(ctx: Context, slide: Slide) -> Layers:
    c = colors(ctx)
    bg = background(ctx).copy()
    accent = blank(ctx)
    _ghost(accent, ctx, 200, alpha=150)

    text = blank(ctx)
    draw = canvas(text, ctx)
    title = _title(slide.title, SAFE_WIDTH, 260, 108, 64, lines=2)
    body_block = T.fit(slide.body, "jp-medium", SAFE_WIDTH, 200, 42, 30, leading=1.55)
    actions = [Chip(label, "jp-bold", 32, fill=None, color=WHITE, outline=fx.rgba(c["neon"], 240), pad_x=1.1)
               for label in ("保存する", "コメント", "シェア")]
    _, actions_height = chip_row(draw, actions, 0, 0, SAFE_WIDTH, gap=18, draw=False)
    actions_top = SAFE_BOTTOM - actions_height
    body_top = actions_top - 48 - body_block.height
    title_top = body_top - 36 - title.height

    character = blank(ctx)
    row = _top_row(text, ctx, "LAST")
    room = title_top - 40 - (SAFE_TOP + row + 40)
    treated, size = subject(ctx, max(min(room, 980), 420), _treat(ctx), max_width=860)
    paste(character, ctx, treated, size, (WIDTH / 2, title_top - 40))

    text.alpha_composite(vscrim(ctx, title_top - 160, title_top + 40, c["ink"], 0, 190))
    T.draw(draw, title, SAFE_LEFT, title_top, WHITE, align="center", box_width=SAFE_WIDTH)
    T.draw(draw, body_block, SAFE_LEFT, body_top, SOFT_WHITE, align="center", box_width=SAFE_WIDTH)
    chip_row(draw, actions, SAFE_LEFT, actions_top, SAFE_WIDTH, gap=18, align="center")
    return Layers(bg, accent, character, text)
