"""The four looks, as primitives a layout can call.

A layout decides where things go - the headline here, the character there. A
look decides what they are made of: how a headline is set and lit, what sits
behind a paragraph, what a big number looks like, how a character is presented.
Four looks times six layouts is twenty-four slide designs from ten functions.

NEON       dark, glowing, loud         - cool
BUBBLE     pastel, round, sticker-like - cute
EDITORIAL  paper, serif, hairlines     - stylish
BRUTAL     flat, gridded, oversized    - cutting edge
"""

from __future__ import annotations

import random

from PIL import Image, ImageFilter

from mbti_tiktok_bot.design import contrast as C
from mbti_tiktok_bot.design import effects as fx
from mbti_tiktok_bot.design import text as T
from mbti_tiktok_bot.design.backgrounds import texture
from mbti_tiktok_bot.design.core import HEIGHT, WIDTH, Chip, Context, neon_partner, vivid
from mbti_tiktok_bot.design.kit import blank, canvas, framed, glass, hollow, paste, shape_mask, subject, swipe_cue
from mbti_tiktok_bot.visuals import _seed_choice

RGBA = tuple[int, int, int, int]


def fit_label(text: str, role: str, size: int, max_width: float | None, tracking_em: float,
              minimum: int = 22) -> int:
    """The largest size at which one line of label text fits.

    A post title is an eyebrow on its inner slides, and the catalogue has some
    long ones: INTJが本命前で見せる距離を詰めたい時の葛藤 ran straight through the
    01 / 05 counter on the other side of the row.
    """
    if max_width is None:
        return size
    for candidate in range(size, minimum - 1, -2):
        if T.single(text, role, candidate, tracking_em=tracking_em).width <= max_width:
            return candidate
    return minimum


class Look:
    name = "base"
    dark = False
    headline_role = "jp-black"
    headline_leading = 1.08
    headline_tracking = -0.02
    body_role = "jp-medium"
    body_leading = 1.6
    panel_pad = 44

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.c = self.colors()

    # -- palette -------------------------------------------------------------
    def colors(self) -> dict[str, str]:
        raise NotImplementedError

    def rgba(self, key: str, alpha: int = 255) -> RGBA:
        return fx.rgba(self.c[key], alpha)

    def pairs(self) -> list[tuple[str, str, str]]:
        """(what, ink, what is behind it) for every piece of type the look sets.

        The contrast test walks these for all twenty-four palettes; a look that
        adds a coloured surface adds the pair that goes with it.
        """
        raise NotImplementedError

    @property
    def ink(self) -> RGBA:
        return self.rgba("ink")

    @property
    def sub(self) -> RGBA:
        return self.rgba("ink", 215)

    surface_key = "ground"

    @property
    def surface(self) -> RGBA:
        """The page colour, for keylines that lift a mark off a character."""
        return self.rgba(self.surface_key)

    # -- ground --------------------------------------------------------------
    def background(self) -> Image.Image:
        raise NotImplementedError

    def ground(self) -> Image.Image:
        key = f"{self.name}.bg"
        if key not in self.ctx.cache:
            self.ctx.cache[key] = self.background()
        return self.ctx.cache[key].copy()

    # -- type ----------------------------------------------------------------
    def headline(self, text: str, width: float, height: float, base: int, minimum: int, lines: int = 3) -> T.Block:
        return T.fit(text, self.headline_role, width, height, base, minimum, leading=self.headline_leading,
                     tracking_em=self.headline_tracking, max_lines=lines, strict=True)

    def draw_headline(self, draw, layer, block: T.Block, x: float, y: float, align: str = "left",
                      width: float | None = None, color: RGBA | None = None) -> None:
        T.draw(draw, block, x, y, color or self.ink, align=align, box_width=width)

    def body(self, text: str, width: float, height: float = 440, base: int = 46, minimum: int = 34) -> T.Block:
        return T.fit(text, self.body_role, width, height, base, minimum, leading=self.body_leading)

    def draw_body(self, draw, block: T.Block, x: float, y: float, align: str = "left", width: float | None = None) -> None:
        T.draw(draw, block, x, y, self.sub, align=align, box_width=width)

    def eyebrow(self, draw, text: str, x: float, y: float, align: str = "left", width: float | None = None,
                size: int = 36, max_width: float | None = None) -> float:
        role, tracking = self._label_face(text)
        size = fit_label(text, role, size, max_width, tracking)
        block = T.single(text, role, size, tracking_em=tracking)
        T.draw(draw, block, x, y, self.rgba("accent"), align=align, box_width=width)
        return T.ink_height(block)

    def _label_face(self, text: str) -> tuple[str, float]:
        return ("label", 0.18) if text.isascii() else ("jp-bold", 0.06)

    def chip(self, label: str, strong: bool = False, size: int = 30) -> Chip:
        raise NotImplementedError

    def numeral(self, layer, draw, text: str, x: float, y: float, size: int, align: str = "left",
                width: float | None = None) -> T.Block:
        raise NotImplementedError

    def rank(self, layer, draw, number: int, x: float, y: float, size: int) -> tuple[float, float]:
        """A place in a ranking: the look's numeral with 位 on its baseline. Returns (width, height).

        Drawn on the text layer, above the character: in the accent layer the
        portrait and the winner's rays covered the one number the slide is about.
        """
        block = self.numeral(layer, draw, str(number), x, y, size)
        unit = T.single("位", self.headline_role, max(int(size * 0.3), 40), compress=False)
        gap = size * 0.05
        self.draw_headline(draw, layer, unit, x + block.width + gap, y + block.height - T.ink_height(unit),
                           color=self.rgba("accent"))
        return block.width + gap + unit.width, block.height

    def type_mark(self, layer, draw, mbti: str, y: float, size: int = 520, alpha: int = 255) -> None:
        """The type's letters as a big graphic element behind the character."""

    def cue(self, draw, x_right: float, y: float, label: str = "SWIPE") -> None:
        swipe_cue(draw, x_right, y, self.sub, label)

    def counter(self, draw, text: str, x_right: float, y: float, size: int = 38) -> float:
        block = T.single(text, "label", size, tracking_em=0.14)
        T.draw(draw, block, x_right - block.width, y, self.sub)
        return T.ink_height(block)

    def type_name(self, draw, mbti: str, archetype: str, x: float, y: float, size: int = 104,
                  align: str = "left", width: float | None = None) -> float:
        """The type in display caps with its archetype beside or under it. Returns the height used."""
        block = T.single(mbti, "display", size, tracking_em=0.02)
        arche = T.single(archetype, "jp-bold", max(int(size * 0.3), 22), tracking_em=0.08)
        if align == "center":
            T.draw(draw, block, x, y, self.rgba("accent"), align="center", box_width=width)
            T.draw(draw, arche, x, y + block.height + size * 0.16, self.sub, align="center", box_width=width)
            return block.height + size * 0.16 + T.ink_height(arche)
        T.draw(draw, block, x, y, self.rgba("accent"))
        T.draw(draw, arche, x + block.width + size * 0.2, y + block.height - T.ink_height(arche), self.sub)
        return block.height

    # -- surfaces ------------------------------------------------------------
    def panel(self, layer, box: tuple[float, float, float, float]) -> None:
        """What sits behind a paragraph."""

    def scrim(self, layer, top: float, bottom: float) -> None:
        """Darken or lighten a band so copy reads over art."""

    def burst(self, layer, center: tuple[float, float], radius: float) -> None:
        """Rays behind a winner."""
        draw = canvas(layer, self.ctx)
        cx, cy = center
        for index in range(24):
            import math

            a0 = index * math.tau / 24
            a1 = a0 + math.tau / 48
            draw.polygon([(cx, cy), (cx + radius * math.cos(a0), cy + radius * math.sin(a0)),
                          (cx + radius * math.cos(a1), cy + radius * math.sin(a1))],
                         fill=self.rgba("accent", 60 if self.dark else 70))

    # -- characters ----------------------------------------------------------
    def portrait(self, mbti: str, box: tuple[float, float, float, float], index: int = 0,
                 small: bool = False) -> Image.Image:
        """A character presented inside box, bottom-anchored. Returns a device layer."""
        raise NotImplementedError

    def _fit(self, mbti: str, box, treat, anchor_x: float | None = None, scale: float = 1.0) -> Image.Image:
        left, top, right, bottom = box
        layer = blank(self.ctx)
        treated, size = subject(self.ctx, mbti, (bottom - top) * scale, treat, max_width=(right - left) * scale)
        paste(layer, self.ctx, treated, size, (anchor_x if anchor_x is not None else (left + right) / 2, bottom))
        return layer


# --- NEON --------------------------------------------------------------------


class Neon(Look):
    name = "neon"
    dark = True

    def colors(self) -> dict[str, str]:
        neon = vivid(self.ctx.palette.accent, 0.82, 1.0)
        ground = fx.mix(self.ctx.palette.background, "#05040a", 0.88)
        # A deep indigo is still dark at full saturation, and it carries the
        # eyebrow and the numerals, so it is brightened until it reads.
        return {
            "ground": ground,
            "ink": "#ffffff",
            "accent": C.against(neon, ground),
            "accent2": C.against(neon_partner(neon), ground, C.LARGE),
            "soft": fx.mix(self.ctx.palette.light, "#ffffff", 0.3),
            "caution": C.against("#ff4d6d", ground),
        }

    def pairs(self) -> list[tuple[str, str, str]]:
        # The aurora only lifts the ground, so the base colour is the worst case
        # for white type and the best case for the accent; both are checked.
        return [
            ("headline", self.c["ink"], self.c["ground"]),
            ("body", self.c["ink"], self.c["ground"]),
            ("eyebrow", self.c["accent"], self.c["ground"]),
            ("numeral", self.c["accent"], self.c["ground"]),
            ("chip", self.c["ink"], self.c["ground"]),
            ("strong chip", self.c["ground"], self.c["accent"]),
            ("caution", self.c["caution"], self.c["ground"]),
        ]

    def background(self) -> Image.Image:
        w, h = self.ctx.device
        s = self.ctx.scale
        image = fx.aurora(self.ctx.device, self.rgba("ground"), [
            ((w * 0.88, h * 0.22), 780 * s, self.rgba("accent", 140)),
            ((w * 0.06, h * 0.78), 840 * s, self.rgba("accent2", 120)),
            ((w * 0.62, h * 0.60), 380 * s, self.rgba("accent2", 60)),
        ])
        # The texture goes over the glows and under the dot grid, so the grid
        # still reads as the look's own structure rather than part of the art.
        art = texture(self.ctx, self.name, self.c["ground"], self.c["accent"], 150)
        if art is not None:
            image.alpha_composite(art)
        draw = canvas(image, self.ctx)
        for gy in range(96, HEIGHT, 64):
            for gx in range(48, WIDTH, 64):
                draw.ellipse((gx - 1.3, gy - 1.3, gx + 1.3, gy + 1.3), fill=(255, 255, 255, 20))
        return fx.grain(image, 0.05, seed=self.ctx.seed)

    def draw_headline(self, draw, layer, block, x, y, align="left", width=None, color=None) -> None:
        T.draw(draw, block, x, y, color or self.ink, align=align, box_width=width, shadow=(0, 6, (0, 0, 0, 130)))

    def chip(self, label, strong=False, size=30) -> Chip:
        if strong:
            return Chip(label, "jp-bold", size, fill=self.rgba("accent", 240), color=self.rgba("ground"))
        return Chip(label, "jp-bold", size, fill=self.rgba("accent", 40), color=self.ink, outline=self.rgba("accent", 220))

    def numeral(self, layer, draw, text, x, y, size, align="left", width=None) -> T.Block:
        block = T.single(text, "display", size)
        hollow(layer, self.ctx, block, x, y, self.rgba("accent", 235), stroke=3, fill_alpha=30, align=align, width=width)
        return block

    def type_mark(self, layer, draw, mbti, y, size=520, alpha=150) -> None:
        block = T.fit_single(mbti, "display", WIDTH - 40, size, 200, tracking_em=0.01)
        hollow(layer, self.ctx, block, (WIDTH - block.width) / 2, y, self.rgba("accent", alpha), stroke=3, fill_alpha=22)

    def panel(self, layer, box) -> None:
        glass(layer, self.ctx, self.ground(), box, 40, (255, 255, 255, 22), self.rgba("soft", 70))

    def scrim(self, layer, top, bottom) -> None:
        from mbti_tiktok_bot.design.kit import vscrim

        layer.alpha_composite(vscrim(self.ctx, top, bottom, self.c["ground"], 0, 225))

    def portrait(self, mbti, box, index=0, small=False) -> Image.Image:
        ctx = self.ctx

        def treat(figure):
            lit = fx.rim(figure, self.rgba("accent2", 235), (ctx.px(-8 if small else -10), ctx.px(-4)), ctx.px(4 if small else 5))
            return fx.glow(lit, ctx.px(18 if small else 32), self.rgba("accent", 110))

        return self._fit(mbti, box, treat)


# --- BUBBLE -------------------------------------------------------------------


def _sparkle(draw, cx, cy, r, color) -> None:
    waist = r * 0.28
    draw.polygon([(cx, cy - r), (cx + waist, cy - waist), (cx + r, cy), (cx + waist, cy + waist),
                  (cx, cy + r), (cx - waist, cy + waist), (cx - r, cy), (cx - waist, cy - waist)], fill=color)


class Bubble(Look):
    name = "bubble"
    surface_key = "paper"
    headline_leading = 1.12
    headline_tracking = 0.0
    body_role = "jp-bold"
    body_leading = 1.62
    panel_pad = 48

    def colors(self) -> dict[str, str]:
        base = vivid(self.ctx.palette.accent, 0.62, 0.96)
        partner = neon_partner(base)
        return {
            "paper": fx.mix(base, "#ffffff", 0.84),
            "pastel": fx.mix(base, "#ffffff", 0.50),
            "pastel2": fx.mix(partner, "#ffffff", 0.58),
            "accent": vivid(self.ctx.palette.accent, 0.66, 0.90),
            # The number badge is a small disc carrying type, so it is deep
            # enough for white to read; the sparkles keep the bright accent.
            "badge": C.deepen(vivid(self.ctx.palette.accent, 0.72, 0.92), 0.15),
            "accent2": vivid(partner, 0.55, 0.96),
            "ink": fx.mix(self.ctx.palette.accent_deep, "#140c1c", 0.45),
            "caution": C.against("#ff5a78", fx.mix(base, "#ffffff", 0.84)),
        }

    @property
    def sub(self) -> RGBA:
        return self.rgba("ink", 235)

    def pairs(self) -> list[tuple[str, str, str]]:
        return [
            ("headline", self.c["ink"], self.c["paper"]),
            ("body", self.c["ink"], "#ffffff"),  # the body sits on a white card
            ("eyebrow", "#ffffff", self.c["ink"]),  # the eyebrow is a filled chip
            ("numeral", C.readable(self.c["badge"], self.c["ink"], "#ffffff"), self.c["badge"]),
            ("chip", self.c["ink"], self.c["pastel"]),
            ("caution", self.c["caution"], self.c["paper"]),
        ]

    def background(self) -> Image.Image:
        w, h = self.ctx.device
        s = self.ctx.scale
        image = fx.aurora(self.ctx.device, self.rgba("paper"), [
            ((w * 0.10, h * 0.12), 620 * s, self.rgba("pastel2", 170)),
            ((w * 0.95, h * 0.55), 700 * s, self.rgba("pastel", 150)),
            ((w * 0.20, h * 0.95), 560 * s, self.rgba("pastel2", 120)),
        ])
        # Kept airy: at full strength the clouds read as the subject rather
        # than the paper, and the characters have to sit on top of them.
        art = texture(self.ctx, self.name, fx.mix(self.c["accent"], "#ffffff", 0.45), "#ffffff", 100)
        if art is not None:
            image.alpha_composite(art)
        draw = canvas(image, self.ctx)
        for row, gy in enumerate(range(40, HEIGHT + 60, 88)):
            for gx in range(-40 + (row % 2) * 44, WIDTH + 60, 88):
                draw.ellipse((gx - 7, gy - 7, gx + 7, gy + 7), fill=(255, 255, 255, 120))
        rng = random.Random(self.ctx.seed)
        for _ in range(14):
            x, y = rng.uniform(40, WIDTH - 40), rng.uniform(80, HEIGHT - 80)
            _sparkle(draw, x, y, rng.uniform(10, 26), fx.rgba(rng.choice([self.c["accent"], self.c["accent2"], "#ffffff"]), 200))
        return fx.grain(image, 0.025, seed=self.ctx.seed)

    def draw_headline(self, draw, layer, block, x, y, align="left", width=None, color=None) -> None:
        T.draw(draw, block, x, y, color or self.ink, align=align, box_width=width,
               stroke=max(block.size // 9, 5), stroke_fill=(255, 255, 255, 255),
               shadow=(0, block.size * 0.08, self.rgba("accent", 170)))

    def eyebrow(self, draw, text, x, y, align="left", width=None, size=36, max_width=None) -> float:
        from mbti_tiktok_bot.design.core import chip_row

        # A chip is as wide as its text plus its padding, so the text is fitted
        # to what is left after the padding.
        size = fit_label(text, "jp-bold", size - 4, None if max_width is None else max_width - 30, 0.0)
        _, height = chip_row(draw, [self.chip(text, strong=True, size=size)], x, y, width or 600, align=align)
        return height

    def chip(self, label, strong=False, size=30) -> Chip:
        if strong:
            return Chip(label, "jp-bold", size, fill=self.ink, color=(255, 255, 255, 255))
        return Chip(label, "jp-bold", size, fill=self.rgba("pastel"), color=self.ink)

    def numeral(self, layer, draw, text, x, y, size, align="left", width=None) -> T.Block:
        block = T.single(text, "display", int(size * 0.62))
        diameter = size
        left = x if align == "left" else (x + (width or diameter) - diameter if align == "right" else x + ((width or diameter) - diameter) / 2)
        draw.ellipse((left, y, left + diameter, y + diameter), fill=self.rgba("badge"))
        T.draw(draw, block, left, y + (diameter - T.ink_height(block)) / 2,
               fx.rgba(C.readable(self.c["badge"], self.c["ink"], "#ffffff")), align="center", box_width=diameter)
        return T.Block(block.lines, block.role, block.size, block.tracking, block.leading, diameter, diameter)

    def type_mark(self, layer, draw, mbti, y, size=520, alpha=255) -> None:
        block = T.fit_single(mbti, "display", WIDTH - 40, size, 200, tracking_em=0.02)
        T.draw(draw, block, (WIDTH - block.width) / 2, y, self.rgba("pastel", 200))

    def panel(self, layer, box) -> None:
        ctx = self.ctx
        shadow = blank(ctx)
        canvas(shadow, ctx).rounded_rectangle((box[0] + 4, box[1] + 18, box[2] + 4, box[3] + 18), radius=48,
                                              fill=self.rgba("accent", 70))
        layer.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(ctx.px(14))))
        canvas(layer, ctx).rounded_rectangle(box, radius=48, fill=(255, 255, 255, 246))

    def portrait(self, mbti, box, index=0, small=False) -> Image.Image:
        ctx = self.ctx
        left, top, right, bottom = box
        tilt = (-5, 3, -2, 5, -4, 2)[(ctx.seed // 5 + index) % 6]
        layer = blank(ctx)
        radius = min(right - left, bottom - top) * 0.46
        cx, cy = (left + right) / 2, bottom - radius * 1.02
        draw = canvas(layer, ctx)
        disc = self.c["pastel"] if index % 2 == 0 else self.c["pastel2"]
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=fx.rgba(disc))
        if not small:
            draw.ellipse((cx - radius + 18, cy - radius - 10, cx + radius + 18, cy + radius - 10),
                         outline=(255, 255, 255, 190), width=5)

        def treat(figure):
            sticker = fx.outline(figure, ctx.px(8 if small else 12), (255, 255, 255, 255))
            sticker = sticker.rotate(tilt, resample=Image.Resampling.BICUBIC, expand=True)
            return fx.shadow(sticker, (ctx.px(5), ctx.px(12)), ctx.px(9), self.rgba("ink", 70))

        layer.alpha_composite(self._fit(mbti, box, treat, scale=0.96))
        return layer


# --- EDITORIAL ----------------------------------------------------------------


class Editorial(Look):
    name = "editorial"
    surface_key = "paper"
    headline_role = "serif-black"
    headline_leading = 1.18
    headline_tracking = 0.01
    body_role = "serif-light"
    body_leading = 1.85

    def colors(self) -> dict[str, str]:
        return {
            "paper": fx.mix("#f3eee5", self.ctx.palette.light, 0.12),
            "ink": "#1c1a17",
            "muted": "#5f584f",
            "accent": fx.mix(self.ctx.palette.accent_deep, "#8c7b6b", 0.18),
            "field": fx.mix(self.ctx.palette.accent, "#efe7da", 0.62),
            "caution": "#b23a2a",
        }

    @property
    def sub(self) -> RGBA:
        return self.rgba("ink", 230)

    def pairs(self) -> list[tuple[str, str, str]]:
        return [
            ("headline", self.c["ink"], self.c["paper"]),
            ("body", self.c["ink"], self.c["paper"]),
            ("eyebrow", self.c["accent"], self.c["paper"]),
            ("numeral", self.c["accent"], self.c["paper"]),
            ("chip", self.c["ink"], self.c["paper"]),
            ("strong chip", self.c["paper"], self.c["ink"]),
            ("caution", self.c["caution"], self.c["paper"]),
        ]

    def background(self) -> Image.Image:
        image = fx.solid(self.ctx.device, self.rgba("paper"))
        # Paper stock: the fibres and the raking light, in the palette's own
        # off-white, so the page has a surface instead of a flat fill.
        art = texture(self.ctx, self.name, fx.mix(self.c["paper"], self.c["ink"], 0.16), self.c["paper"], 190)
        if art is not None:
            image.alpha_composite(art)
        return fx.grain(image, 0.045, seed=self.ctx.seed)

    def _label_face(self, text):
        return ("label", 0.3) if text.isascii() else ("jp-medium", 0.14)

    def eyebrow(self, draw, text, x, y, align="left", width=None, size=34, max_width=None) -> float:
        return super().eyebrow(draw, text, x, y, align, width, size, max_width)

    def chip(self, label, strong=False, size=28) -> Chip:
        if strong:
            return Chip(label, "jp-medium", size, fill=self.ink, color=self.rgba("paper"), tracking_em=0.06)
        return Chip(label, "jp-medium", size, fill=None, color=self.ink, outline=self.rgba("ink", 200), tracking_em=0.04)

    def numeral(self, layer, draw, text, x, y, size, align="left", width=None) -> T.Block:
        block = T.single(text, "serif-black", size, compress=False)
        T.draw(draw, block, x, y, self.rgba("accent"), align=align, box_width=width)
        return block

    def type_mark(self, layer, draw, mbti, y, size=520, alpha=255) -> None:
        block = T.fit_single(mbti, "serif-black", WIDTH - 80, int(size * 0.8), 160)
        T.draw(draw, block, (WIDTH - block.width) / 2, y, self.rgba("field", 150))

    def panel(self, layer, box) -> None:
        draw = canvas(layer, self.ctx)
        draw.line((box[0], box[1], box[2], box[1]), fill=self.rgba("ink", 200), width=2)

    def portrait(self, mbti, box, index=0, small=False) -> Image.Image:
        shape = "circle" if small or (box[2] - box[0]) > (box[3] - box[1]) * 0.95 else "arch"
        left, top, right, bottom = box
        if shape == "circle":
            side = min(right - left, bottom - top)
            cx = (left + right) / 2
            box = (cx - side / 2, bottom - side, cx + side / 2, bottom)
        height = (box[3] - box[1])
        return framed(self.ctx, mbti, box, shape_mask(self.ctx, box, shape), self.rgba("field"),
                      height * (1.2 if shape == "circle" else 1.06), height * (0.08 if shape == "circle" else 0.10))


# --- BRUTAL -------------------------------------------------------------------


class Brutal(Look):
    name = "brutal"
    surface_key = "field"
    headline_leading = 1.02
    headline_tracking = -0.05

    def colors(self) -> dict[str, str]:
        accent = vivid(self.ctx.palette.accent, 0.86, 0.96)
        loud = _seed_choice(self.ctx.seed, "brutal.mode", 2) == 1
        # A saturated accent sits in the middle of the range, where black reads
        # at 4:1 and white at 4:1 and the characters come out grey. The field
        # keeps the hue but goes to one end, and the ink follows from there.
        field = C.ground(accent, dark=loud)
        ink = C.readable(field, "#0d0d0d", "#f7f5f0")
        return {
            "field": field,
            "accent": C.against(C.paled(accent, 0.70) if loud else C.deepen(accent, 0.12), field),
            "ink": ink,
            "block": ink,
            "shade": C.deepen(accent, 0.02) if loud else "#0d0d0d",
            "tint": "#ffffff" if loud else C.paled(accent, 0.74),
            "caution": C.against("#ff6a58" if loud else "#d33a2c", field),
            "loud": "1" if loud else "",
        }

    def pairs(self) -> list[tuple[str, str, str]]:
        return [
            ("headline", self.c["ink"], self.c["field"]),
            ("body", self.c["ink"], self.c["field"]),
            ("eyebrow", self.c["ink"], self.c["field"]),
            ("numeral", self.c["field"], self.c["block"]),
            ("chip", self.c["ink"], self.c["field"]),
            ("accent", self.c["accent"], self.c["field"]),
            ("caution", self.c["caution"], self.c["field"]),
        ]

    @property
    def sub(self) -> RGBA:
        return self.ink

    def background(self) -> Image.Image:
        image = fx.solid(self.ctx.device, self.rgba("field"))
        # Faint enough to be a printed underlay: the slide's own type and blocks
        # have to stay the loudest thing on it.
        art = texture(self.ctx, self.name, self.c["shade"], self.c["field"], 46 if self.c["loud"] else 32)
        if art is not None:
            image.alpha_composite(art)
        draw = canvas(image, self.ctx)
        step = WIDTH / 6
        for i in range(1, 6):
            draw.line((i * step, 0, i * step, HEIGHT), fill=self.rgba("ink", 26), width=1)
        for y in range(0, HEIGHT, int(step)):
            draw.line((0, y, WIDTH, y), fill=self.rgba("ink", 16), width=1)
        for x, y, sx, sy in ((28, 28, 1, 1), (WIDTH - 28, 28, -1, 1), (28, HEIGHT - 28, 1, -1), (WIDTH - 28, HEIGHT - 28, -1, -1)):
            draw.line((x, y, x + 44 * sx, y), fill=self.rgba("ink", 200), width=2)
            draw.line((x, y, x, y + 44 * sy), fill=self.rgba("ink", 200), width=2)
        return fx.grain(image, 0.03, seed=self.ctx.seed)

    def eyebrow(self, draw, text, x, y, align="left", width=None, size=36, max_width=None) -> float:
        label = f"[{text}]" if text.isascii() else f"■ {text}"
        role, tracking = ("label", 0.14) if text.isascii() else ("jp-bold", 0.06)
        size = fit_label(label, role, size, max_width, tracking)
        block = T.single(label, role, size, tracking_em=tracking)
        T.draw(draw, block, x, y, self.ink, align=align, box_width=width)
        return T.ink_height(block)

    def chip(self, label, strong=False, size=30) -> Chip:
        if strong:
            return Chip(label, "jp-black", size, fill=self.ink, color=(255, 255, 255, 255), square=True, height_em=1.8)
        return Chip(label, "jp-bold", size, fill=None, color=self.ink, outline=self.ink, stroke=3, square=True, height_em=1.8)

    def numeral(self, layer, draw, text, x, y, size, align="left", width=None) -> T.Block:
        block = T.single(text, "display", size)
        pad = size * 0.14
        box_w = block.width + pad * 2
        left = x if align == "left" else (x + (width or box_w) - box_w if align == "right" else x + ((width or box_w) - box_w) / 2)
        draw.rectangle((left, y, left + box_w, y + block.height + pad * 2), fill=self.rgba("block"))
        T.draw(draw, block, left + pad, y + pad, self.rgba("field"))
        return T.Block(block.lines, block.role, block.size, block.tracking, block.leading, box_w, block.height + pad * 2)

    def type_mark(self, layer, draw, mbti, y, size=760, alpha=255) -> None:
        block = T.single(mbti, "display", size, tracking_em=-0.02)
        T.draw(draw, block, -24, y, self.rgba("accent"))

    def panel(self, layer, box) -> None:
        canvas(layer, self.ctx).rectangle((box[0], box[1], box[0] + 120, box[1] + 12), fill=self.ink)

    def portrait(self, mbti, box, index=0, small=False) -> Image.Image:
        ctx = self.ctx
        # Mapped between a shade and a tint of the field's own hue, so a figure
        # reads as a lit shape on the page instead of grey on colour.
        shade, tint = self.c["shade"], self.c["tint"]

        def treat(figure):
            toned = fx.duotone(figure, shade, tint)
            return fx.shadow(toned, (ctx.px(8 if small else 14), ctx.px(8 if small else 14)), 0.1,
                             fx.rgba(shade, 210))

        return self._fit(mbti, box, treat)


LOOKS = {"neon": Neon, "bubble": Bubble, "editorial": Editorial, "brutal": Brutal}
LOOK_ORDER = ("neon", "bubble", "editorial", "brutal")
