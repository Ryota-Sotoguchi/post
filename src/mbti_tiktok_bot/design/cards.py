"""The six slide layouts, drawn in whichever look the post was given.

Every layout lays its copy out first, from the bottom of the safe area up, and
gives the character whatever height is left above it. That is what keeps a
long headline off a face, in every look and every format.
"""

from __future__ import annotations

from mbti_tiktok_bot.catalog import TYPE_DATA
from mbti_tiktok_bot.design import text as T
from mbti_tiktok_bot.design.core import SAFE_BOTTOM, SAFE_LEFT, SAFE_RIGHT, SAFE_TOP, SAFE_WIDTH, WIDTH, chip_flow, chip_row
from mbti_tiktok_bot.design.kit import Layers, blank, canvas, paste, subject
from mbti_tiktok_bot.design.looks import Look
from mbti_tiktok_bot.formats.model import Card, Post

ROW_GAP = 40
# How much of the width the copy takes on a section slide; the character
# stands in what is left.
COLUMN = 0.63


def _archetype(mbti: str) -> str:
    return str(TYPE_DATA[mbti]["archetype"])


def _start(look: Look):
    return look.ground(), blank(look.ctx), blank(look.ctx), blank(look.ctx)


def _eyebrow_text(text: str) -> str:
    """Titles end in 【恋愛】-style tags; set inside a look's own brackets they nest."""
    return text.replace("【", "・").replace("】", "")


# What a counter or a swipe cue takes on the right of the top row.
RIGHT_ROOM = 230


def _top_row(look: Look, draw, left: str, right: str) -> float:
    """The eyebrow on the left and a counter or swipe cue on the right. Returns its height."""
    room = SAFE_WIDTH - (RIGHT_ROOM if right else 0)
    height = look.eyebrow(draw, _eyebrow_text(left), SAFE_LEFT, SAFE_TOP, max_width=room)
    if right == "SWIPE":
        look.cue(draw, SAFE_RIGHT, SAFE_TOP + max(height - 26, 0) / 2)
    elif right:
        look.counter(draw, right, SAFE_RIGHT, SAFE_TOP + max(height - 26, 0) / 2)
    return max(height, 30)


def _copy_height(look: Look, card: Card, width: float, body_base: int = 46) -> tuple[T.Block | None, float, list]:
    chips = [look.chip(label) for label in card.chips]
    chip_height = chip_flow(None, chips, 0, 0, width, draw=False) if chips else 0.0
    body = look.body(card.body, width, base=body_base) if card.body else None
    height = chip_height + (28 if chips and body else 0) + (body.height if body else 0)
    return body, height, chips


def _draw_copy(look: Look, draw, card: Card, body: T.Block | None, chips: list, x: float, y: float, width: float,
               align: str = "left") -> None:
    if chips:
        y += chip_flow(draw, chips, x, y, width, align=align) + 28
    if body:
        look.draw_body(draw, body, x, y, align=align, width=width if align != "left" else None)


def _panelled_copy(look: Look, accent, draw, card: Card, bottom: float, width: float = SAFE_WIDTH + 32,
                   body_base: int = 46) -> float:
    """Chips and body on the look's panel, bottom-aligned. Returns the panel's top."""
    pad = look.panel_pad
    left = SAFE_LEFT - 16
    body, height, chips = _copy_height(look, card, width - pad * 2, body_base)
    if not height:
        return bottom
    top = bottom - height - pad * 2
    look.panel(accent, (left, top, left + width, bottom))
    _draw_copy(look, draw, card, body, chips, left + pad, top + pad, width - pad * 2)
    return top


# --- cover --------------------------------------------------------------------


def _grid_of_sixteen(look: Look, character, draw, types: tuple[str, ...], region) -> None:
    left, top, right, bottom = region
    cols, rows = 4, 4
    cell_w, cell_h = (right - left) / cols, (bottom - top) / rows
    label_h = 30
    for index, mbti in enumerate(types[:16]):
        col, row = index % cols, index // cols
        x0, y0 = left + col * cell_w, top + row * cell_h
        box = (x0 + 8, y0 + 4, x0 + cell_w - 8, y0 + cell_h - label_h - 6)
        character.alpha_composite(look.portrait(mbti, box, index=index, small=True))
        name = T.single(mbti, "label", 28, tracking_em=0.1)
        T.draw(draw, name, x0, y0 + cell_h - label_h + 2, look.sub, align="center", box_width=cell_w)


def cover(look: Look, post: Post, card: Card) -> Layers:
    bg, accent, character, text = _start(look)
    draw = canvas(text, look.ctx)
    row = _top_row(look, draw, card.label, "SWIPE")

    hook = look.body(card.body, SAFE_WIDTH, 260, base=46, minimum=32)
    title = look.headline(card.title, SAFE_WIDTH, 460, 128, 64)
    hook_top = SAFE_BOTTOM - hook.height
    title_top = hook_top - 44 - title.height
    region = (SAFE_LEFT - 40, SAFE_TOP + row + ROW_GAP, SAFE_RIGHT + 40, title_top - 44)

    if post.format in ("gallery", "ranking"):
        _grid_of_sixteen(look, character, draw, card.types, region)
    elif post.format == "manual":
        mbti = post.focus
        look.type_mark(accent, canvas(accent, look.ctx), mbti, region[1] + 20, size=560)
        character.alpha_composite(look.portrait(mbti, region))
    else:
        # The focus type, and a question mark where its matches will be.
        mbti = post.focus
        names_top = region[3] - 76
        half = (region[2] - region[0]) / 2
        left_box = (region[0], region[1] + 40, region[0] + half, names_top - 16)
        character.alpha_composite(look.portrait(mbti, left_box, index=0))
        right_box = (region[0] + half, region[1] + 40, region[2], names_top - 16)
        radius = min(half, right_box[3] - right_box[1]) * 0.38
        cx, cy = (right_box[0] + right_box[2]) / 2, right_box[3] - radius - 24
        adraw = canvas(accent, look.ctx)
        adraw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=look.rgba("accent", 220), width=6)
        mark = T.single("?", "display", int(radius * 1.2))
        T.draw(adraw, mark, cx - radius, cy - T.ink_height(mark) / 2, look.rgba("accent"), align="center", box_width=radius * 2)
        cross = T.single("×", "jp-black", 110, compress=False)
        T.draw(draw, cross, region[0] + half - 60, cy - T.ink_height(cross) / 2, look.rgba("accent"),
               align="center", box_width=120)
        for index, name in enumerate((mbti, "WHO?")):
            T.draw(draw, T.single(name, "display", 72, tracking_em=0.02), region[0] + index * half, names_top,
                   look.rgba("accent"), align="center", box_width=half)

    look.draw_headline(draw, text, title, SAFE_LEFT, title_top)
    look.draw_body(draw, hook, SAFE_LEFT, hook_top)
    return Layers(bg, accent, character, text)


# --- one type ------------------------------------------------------------------


def entry(look: Look, post: Post, card: Card) -> Layers:
    """One type as the hero: a gallery slide, or a place in a ranking's top four."""
    bg, accent, character, text = _start(look)
    draw = canvas(text, look.ctx)
    item = card.items[0]
    ranking = post.format == "ranking"
    # A ranking's place is the slide's giant numeral; saying 第4位 above it
    # again only crowded the corner, so the eyebrow keeps the post's title.
    row = _top_row(look, draw, post.title, f"{card.number:02d} / {card.total:02d}" if not ranking else "")

    body, body_height, chips = _copy_height(look, card, SAFE_WIDTH)
    title = look.headline(card.title, SAFE_WIDTH, 330, 112, 60)
    body_top = SAFE_BOTTOM - body_height
    title_top = body_top - (40 if body_height else 0) - title.height
    name_top = title_top - 44 - 104
    top = SAFE_TOP + row + ROW_GAP

    if ranking:
        art = (SAFE_LEFT + 140, top + 30, SAFE_RIGHT + 60, name_top - 20)
        if card.number == 1:
            look.burst(accent, ((art[0] + art[2]) / 2, (art[1] + art[3]) / 2), (art[3] - art[1]) * 0.7)
        look.rank(text, draw, card.number, SAFE_LEFT, top, 260)
    else:
        look.type_mark(accent, canvas(accent, look.ctx), item.type, top + 20, size=520)
        art = (SAFE_LEFT - 40, top + 40, SAFE_RIGHT + 40, name_top - 20)
    character.alpha_composite(look.portrait(item.type, art, index=card.number))

    look.type_name(draw, item.type, _archetype(item.type), SAFE_LEFT, name_top, size=104)
    look.draw_headline(draw, text, title, SAFE_LEFT, title_top)
    _draw_copy(look, draw, card, body, chips, SAFE_LEFT, body_top, SAFE_WIDTH)
    return Layers(bg, accent, character, text)


# --- four ranks at once ---------------------------------------------------------


# --- a manual section -------------------------------------------------------------


def section(look: Look, post: Post, card: Card) -> Layers:
    """Number, heading, copy on a panel, character in the column beside it.

    Every section is laid out the same way, whatever the copy length. The
    arrangement used to follow the copy - character above short copy, beside
    long copy - which made the sixteen posts of one series look like sixteen
    different designs.
    """
    bg, accent, character, text = _start(look)
    draw = canvas(text, look.ctx)
    row = _top_row(look, draw, card.label, f"{card.number:02d} / {card.total:02d}")
    top = SAFE_TOP + row + ROW_GAP

    numeral = look.numeral(accent, canvas(accent, look.ctx), f"{card.number:02d}", SAFE_LEFT, top, 200)
    title = look.headline(card.title, SAFE_WIDTH, 300, 116, 60, lines=2)
    title_top = top + numeral.height + 36
    look.draw_headline(draw, text, title, SAFE_LEFT, title_top)

    panel_width = (SAFE_WIDTH + 32) * COLUMN
    _panelled_copy(look, accent, draw, card, SAFE_BOTTOM, width=panel_width)
    box = (SAFE_LEFT - 16 + panel_width + 8, title_top + title.height + 16, SAFE_RIGHT + 60, SAFE_BOTTOM - 16)

    character.alpha_composite(look.portrait(post.focus, box, index=card.number))
    return Layers(bg, accent, character, text, order=("background", "character", "accent", "text"))


# --- a pairing --------------------------------------------------------------------


def pair(look: Look, post: Post, card: Card) -> Layers:
    bg, accent, character, text = _start(look)
    draw = canvas(text, look.ctx)
    caution = card.label.startswith("要注意")
    row = _top_row(look, draw, post.title, f"{'CAUTION' if caution else 'MATCH'} {card.number}")

    label = look.headline(card.label, SAFE_WIDTH, 150, 104, 60, lines=1)
    label_top = SAFE_TOP + row + 28
    look.draw_headline(draw, text, label, SAFE_LEFT, label_top, color=look.rgba("caution") if caution else None)

    body, body_height, chips = _copy_height(look, card, SAFE_WIDTH - look.panel_pad * 2 + 32)
    title = look.headline(card.title, SAFE_WIDTH, 260, 96, 56, lines=2)
    panel_top = _panelled_copy(look, accent, draw, card, SAFE_BOTTOM)
    title_top = panel_top - 36 - title.height
    names_top = title_top - 44 - 72

    region = (SAFE_LEFT - 40, label_top + label.height + 40, SAFE_RIGHT + 40, names_top - 16)
    half = (region[2] - region[0]) / 2
    for index, mbti in enumerate((card.items[0].type, card.items[1].type)):
        box = (region[0] + index * half, region[1], region[0] + (index + 1) * half, region[3])
        character.alpha_composite(look.portrait(mbti, box, index=index))
        T.draw(draw, T.single(mbti, "display", 72, tracking_em=0.02), box[0], names_top, look.rgba("accent"),
               align="center", box_width=half)
    mark = T.single("×" if not caution else "!?", "jp-black", 120, compress=False)
    T.draw(draw, mark, region[0] + half - 80, (region[1] + region[3]) / 2 - 40,
           look.rgba("caution") if caution else look.rgba("accent"), align="center", box_width=160,
           stroke=8, stroke_fill=look.surface)
    look.draw_headline(draw, text, title, SAFE_LEFT, title_top)
    return Layers(bg, accent, character, text)


# --- the last slide ----------------------------------------------------------------


def closer(look: Look, post: Post, card: Card) -> Layers:
    bg, accent, character, text = _start(look)
    draw = canvas(text, look.ctx)
    row = _top_row(look, draw, "FOLLOW", "LAST")

    actions = [look.chip(label, strong=True, size=34) for label in ("保存する", "コメント", "シェア")]
    _, actions_height = chip_row(draw, actions, 0, 0, SAFE_WIDTH, gap=18, draw=False)
    actions_top = SAFE_BOTTOM - actions_height
    body = look.body(card.body, SAFE_WIDTH, 220, base=44, minimum=32)
    body_top = actions_top - 44 - body.height
    title = look.headline(card.title, SAFE_WIDTH, 300, 116, 64, lines=2)
    title_top = body_top - 36 - title.height

    region = (SAFE_LEFT - 40, SAFE_TOP + row + ROW_GAP, SAFE_RIGHT + 40, title_top - 40)
    types = card.types[:4] if len(card.types) > 2 else card.types
    width = (region[2] - region[0]) / max(len(types), 1)
    for index, mbti in enumerate(types):
        box = (region[0] + index * width, region[1], region[0] + (index + 1) * width, region[3])
        character.alpha_composite(look.portrait(mbti, box, index=index, small=len(types) > 2))

    look.draw_headline(draw, text, title, SAFE_LEFT, title_top, align="center", width=SAFE_WIDTH)
    look.draw_body(draw, body, SAFE_LEFT, body_top, align="center", width=SAFE_WIDTH)
    chip_row(draw, actions, SAFE_LEFT, actions_top, SAFE_WIDTH, gap=18, align="center")
    return Layers(bg, accent, character, text)


# "grid" is gone: a ranking put its bottom twelve four to a slide, which left
# most of the sixteen types without a picture of their own.
LAYOUTS = {"cover": cover, "entry": entry, "section": section, "pair": pair, "closer": closer}
