"""The slide layouts, drawn in whichever look the post was given.

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
    top_of_type = title_top

    # A countdown that starts at sixteenth needs a reason to be followed, so
    # the cover says where it ends up.
    promise = [look.chip("1位は最後に発表", strong=True, size=32)] if post.format == "ranking" else []
    if promise:
        _, promise_height = chip_row(draw, promise, SAFE_LEFT, 0, SAFE_WIDTH, draw=False)
        top_of_type = title_top - 20 - promise_height
        chip_row(draw, promise, SAFE_LEFT, top_of_type, SAFE_WIDTH)

    region = (SAFE_LEFT - 40, SAFE_TOP + row + ROW_GAP, SAFE_RIGHT + 40, top_of_type - 44)

    if len(card.types) > 2:
        _grid_of_sixteen(look, character, draw, card.types, region)
    elif len(card.types) == 2 and post.format == "versus":
        # Two types that get mistaken for each other, facing each other.
        left, right = card.types
        half = (region[2] - region[0]) / 2
        names_top = region[3] - 76
        for index, mbti in enumerate((left, right)):
            box = (region[0] + index * half, region[1] + 30, region[0] + (index + 1) * half, names_top - 16)
            character.alpha_composite(look.portrait(mbti, box, index=index))
            T.draw(draw, T.single(mbti, "display", 72, tracking_em=0.02), region[0] + index * half, names_top,
                   look.rgba("accent"), align="center", box_width=half)
        mark = T.single("VS", "display", 96)
        T.draw(draw, mark, region[0] + half - 90, (region[1] + names_top) / 2 - 48, look.rgba("accent"),
               align="center", box_width=180, stroke=8, stroke_fill=look.surface)
    elif post.format in ("manual", "remedy"):
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
# --- a line, and four types it could have come from ------------------------------


def quiz(look: Look, post: Post, card: Card) -> Layers:
    """The quote, big, with four types to choose from. No character: the whole
    point is that you cannot see whose line it is yet."""
    bg, accent, character, text = _start(look)
    draw = canvas(text, look.ctx)
    row = _top_row(look, draw, card.label, f"Q{card.number} / {card.total}")

    choices = [look.chip(mbti, size=44) for mbti in card.chips]
    choice_height = chip_flow(None, choices, 0, 0, SAFE_WIDTH, draw=False)
    choices_top = SAFE_BOTTOM - choice_height
    ask = look.body("どのタイプの一言？", SAFE_WIDTH, 80, base=40, minimum=32)
    ask_top = choices_top - 40 - ask.height

    quote = look.headline(f"「{card.title}」", SAFE_WIDTH, 620, 132, 64, lines=4)
    quote_top = SAFE_TOP + row + ROW_GAP + max((ask_top - (SAFE_TOP + row + ROW_GAP) - quote.height) / 2, 0)
    look.panel(accent, (SAFE_LEFT - 16, quote_top - 48, SAFE_RIGHT + 16, quote_top + quote.height + 48))
    look.draw_headline(draw, text, quote, SAFE_LEFT, quote_top)
    look.draw_body(draw, ask, SAFE_LEFT, ask_top, align="center", width=SAFE_WIDTH)
    chip_flow(draw, choices, SAFE_LEFT, choices_top, SAFE_WIDTH, align="center")
    return Layers(bg, accent, character, text)


def answer(look: Look, post: Post, card: Card) -> Layers:
    """The reveal: the type, its character, and why the line is theirs."""
    bg, accent, character, text = _start(look)
    draw = canvas(text, look.ctx)
    row = _top_row(look, draw, f"「{card.label}」", f"A{card.number} / {card.total}")

    body = look.body(card.body, SAFE_WIDTH, 260, base=44, minimum=32)
    body_top = SAFE_BOTTOM - body.height
    name_top = body_top - 40 - 120
    region = (SAFE_LEFT - 40, SAFE_TOP + row + ROW_GAP, SAFE_RIGHT + 40, name_top - 20)

    mbti = card.title
    look.type_mark(accent, canvas(accent, look.ctx), mbti, region[1] + 10, size=520)
    character.alpha_composite(look.portrait(mbti, region))
    look.type_name(draw, mbti, _archetype(mbti), SAFE_LEFT, name_top, size=110, align="center", width=SAFE_WIDTH)
    look.draw_body(draw, body, SAFE_LEFT, body_top, align="center", width=SAFE_WIDTH)
    return Layers(bg, accent, character, text)


# --- the reply, as it would arrive ------------------------------------------------


def chat(look: Look, post: Post, card: Card) -> Layers:
    """Two bubbles: what was sent, and what this type sends back."""
    bg, accent, character, text = _start(look)
    draw = canvas(text, look.ctx)
    adraw = canvas(accent, look.ctx)
    row = _top_row(look, draw, post.title, f"{card.number:02d} / {card.total:02d}")
    top = SAFE_TOP + row + ROW_GAP

    note = look.body(card.body, SAFE_WIDTH, 160, base=38, minimum=30) if card.body else None
    note_top = SAFE_BOTTOM - (note.height if note else 0)

    incoming = look.body(card.label, SAFE_WIDTH * 0.62 - 56, 200, base=40, minimum=30)
    reply = look.body(card.title, SAFE_WIDTH * 0.66 - 56, 300, base=44, minimum=32)
    pad = 30
    bubble_top = top + 150
    left_bubble = (SAFE_LEFT, bubble_top, SAFE_LEFT + incoming.width + pad * 2, bubble_top + incoming.height + pad * 2)
    look.bubble(accent, left_bubble, incoming=True)
    look.draw_body(draw, incoming, left_bubble[0] + pad, left_bubble[1] + pad, color=look.bubble_ink(True))

    reply_top = left_bubble[3] + 56
    right_bubble = (SAFE_RIGHT - reply.width - pad * 2, reply_top, SAFE_RIGHT, reply_top + reply.height + pad * 2)
    look.bubble(accent, right_bubble, incoming=False)
    look.draw_body(draw, reply, right_bubble[0] + pad, right_bubble[1] + pad, color=look.bubble_ink(False))

    # The sender, standing beside their own message.
    mbti = card.types[0]
    art_top = right_bubble[3] + 24
    if note_top - 24 - art_top >= 200:
        box = (SAFE_LEFT, art_top, SAFE_LEFT + 420, note_top - 24)
        character.alpha_composite(look.portrait(mbti, box))
    look.type_name(draw, mbti, _archetype(mbti), SAFE_LEFT, top, size=104)
    if note:
        look.draw_body(draw, note, SAFE_LEFT, note_top)
    return Layers(bg, accent, character, text)


# --- the one line that ends it -----------------------------------------------------


def nogo(look: Look, post: Post, card: Card) -> Layers:
    """The phrase in quotes, marked as the thing not to say, and who it lands on."""
    bg, accent, character, text = _start(look)
    draw = canvas(text, look.ctx)
    row = _top_row(look, draw, post.title, f"{card.number:02d} / {card.total:02d}")
    top = SAFE_TOP + row + ROW_GAP

    body = look.body(card.body, SAFE_WIDTH, 240, base=42, minimum=32)
    body_top = SAFE_BOTTOM - body.height
    phrase = look.headline(f"「{card.title}」", SAFE_WIDTH, 380, 124, 60, lines=3)
    phrase_top = body_top - 48 - phrase.height
    name_top = phrase_top - 36 - 104

    region = (SAFE_LEFT - 40, top, SAFE_RIGHT + 40, name_top - 16)
    mbti = card.types[0]
    character.alpha_composite(look.portrait(mbti, region))
    look.type_name(draw, mbti, _archetype(mbti), SAFE_LEFT, name_top, size=104)
    look.draw_headline(draw, text, phrase, SAFE_LEFT, phrase_top, color=look.rgba("caution"))
    look.draw_body(draw, body, SAFE_LEFT, body_top)
    return Layers(bg, accent, character, text)


# --- four roles, sixteen types -------------------------------------------------------


def role_map(look: Look, post: Post, card: Card) -> Layers:
    """The whole cast placed in four quarters, so a viewer can find themselves."""
    bg, accent, character, text = _start(look)
    draw = canvas(text, look.ctx)
    adraw = canvas(accent, look.ctx)
    row = _top_row(look, draw, card.label, "")
    top = SAFE_TOP + row + ROW_GAP

    heading = look.headline(card.title, SAFE_WIDTH, 200, 88, 52, lines=2)
    look.draw_headline(draw, text, heading, SAFE_LEFT, top)
    board_top = top + heading.height + 36
    board = (SAFE_LEFT - 24, board_top, SAFE_RIGHT + 24, SAFE_BOTTOM)
    half_w = (board[2] - board[0]) / 2
    half_h = (board[3] - board[1]) / 2

    for index, item in enumerate(card.items[:4]):
        col, quarter_row = index % 2, index // 2
        x0 = board[0] + col * half_w
        y0 = board[1] + quarter_row * half_h
        look.panel(accent, (x0 + 8, y0 + 8, x0 + half_w - 8, y0 + half_h - 8))
        name = T.fit(item.title, "jp-black", half_w - 48, 70, 38, 26, max_lines=2)
        T.draw(draw, name, x0 + 24, y0 + 24, look.rgba("accent"))
        types = card.types[index * 4:(index + 1) * 4]
        cell_w = (half_w - 48) / 4
        art_top = y0 + 24 + name.height + 12
        art_bottom = y0 + half_h - 44
        for slot, mbti in enumerate(types):
            box = (x0 + 24 + slot * cell_w, art_top, x0 + 24 + (slot + 1) * cell_w, art_bottom)
            character.alpha_composite(look.portrait(mbti, box, index=slot, small=True))
            T.draw(draw, T.single(mbti, "display", 30, tracking_em=0.02), box[0], art_bottom + 4,
                   look.sub, align="center", box_width=cell_w)
    return Layers(bg, accent, character, text, order=("background", "accent", "character", "text"))


def role(look: Look, post: Post, card: Card) -> Layers:
    """One role: its four types side by side, and what they actually do."""
    bg, accent, character, text = _start(look)
    draw = canvas(text, look.ctx)
    row = _top_row(look, draw, card.label, f"{card.number} / {card.total}")
    top = SAFE_TOP + row + ROW_GAP

    numeral = look.numeral(accent, canvas(accent, look.ctx), str(card.number), SAFE_LEFT, top, 180)
    title = look.headline(card.title, SAFE_WIDTH, 240, 116, 60, lines=2)
    title_top = top + numeral.height + 30
    look.draw_headline(draw, text, title, SAFE_LEFT, title_top)

    panel_top = _panelled_copy(look, accent, draw, card, SAFE_BOTTOM)
    names_top = panel_top - 40 - 64
    region = (SAFE_LEFT - 40, title_top + title.height + 24, SAFE_RIGHT + 40, names_top - 12)
    width = (region[2] - region[0]) / max(len(card.types), 1)
    for index, mbti in enumerate(card.types):
        box = (region[0] + index * width, region[1], region[0] + (index + 1) * width, region[3])
        character.alpha_composite(look.portrait(mbti, box, index=index, small=True))
        T.draw(draw, T.single(mbti, "display", 52, tracking_em=0.02), box[0], names_top,
               look.rgba("accent"), align="center", box_width=width)
    return Layers(bg, accent, character, text)


# --- a prescription ------------------------------------------------------------------


def dose(look: Look, post: Post, card: Card) -> Layers:
    """One step of the day: when, what to do, and why it works on this type."""
    bg, accent, character, text = _start(look)
    draw = canvas(text, look.ctx)
    row = _top_row(look, draw, post.title, f"{card.number} / {card.total}")
    top = SAFE_TOP + row + ROW_GAP

    why = look.body(card.body, SAFE_WIDTH, 220, base=42, minimum=32)
    why_top = SAFE_BOTTOM - why.height
    action = look.headline(card.title, SAFE_WIDTH, 320, 116, 60, lines=3)
    action_top = why_top - 44 - action.height
    step = look.headline(card.label, SAFE_WIDTH * 0.7, 120, 60, 36, lines=1)
    step_top = action_top - 28 - step.height

    numeral = look.numeral(accent, canvas(accent, look.ctx), f"{card.number:02d}", SAFE_LEFT, top, 190)
    region = (SAFE_LEFT + 200, top - 20, SAFE_RIGHT + 60, step_top - 24)
    character.alpha_composite(look.portrait(post.focus, region))
    look.draw_headline(draw, text, step, SAFE_LEFT, step_top, color=look.rgba("accent"))
    look.draw_headline(draw, text, action, SAFE_LEFT, action_top)
    look.draw_body(draw, why, SAFE_LEFT, why_top)
    return Layers(bg, accent, character, text, order=("background", "character", "accent", "text"))


# --- two types, one question ----------------------------------------------------------


def versus(look: Look, post: Post, card: Card) -> Layers:
    """The same question put to both, side by side, so the difference is the slide."""
    bg, accent, character, text = _start(look)
    draw = canvas(text, look.ctx)
    row = _top_row(look, draw, card.label, f"{card.number} / {card.total}")
    top = SAFE_TOP + row + ROW_GAP

    axis = look.headline(card.title, SAFE_WIDTH, 160, 104, 56, lines=1)
    look.draw_headline(draw, text, axis, SAFE_LEFT, top, align="center", width=SAFE_WIDTH)
    board_top = top + axis.height + 36
    half = SAFE_WIDTH / 2
    pad = 22
    for index, item in enumerate(card.items[:2]):
        x0 = SAFE_LEFT + index * half
        column = (x0 + (pad if index else 0), board_top, x0 + half - (0 if index else pad), SAFE_BOTTOM)
        body = look.body(item.body, column[2] - column[0] - pad * 2, 420, base=40, minimum=28)
        body_top = SAFE_BOTTOM - body.height
        look.panel(accent, (column[0], body_top - pad, column[2], SAFE_BOTTOM))
        look.draw_body(draw, body, column[0] + pad, body_top)
        name_top = body_top - 40 - 64
        T.draw(draw, T.single(item.type, "display", 64, tracking_em=0.02), column[0], name_top,
               look.rgba("accent"), align="center", box_width=column[2] - column[0])
        box = (column[0], board_top + 10, column[2], name_top - 12)
        character.alpha_composite(look.portrait(item.type, box, index=index))
    return Layers(bg, accent, character, text)


LAYOUTS = {
    "cover": cover, "entry": entry, "section": section, "pair": pair, "closer": closer,
    "quiz": quiz, "answer": answer, "chat": chat, "nogo": nogo,
    "map": role_map, "role": role, "dose": dose, "versus": versus,
}
