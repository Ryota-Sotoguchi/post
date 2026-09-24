from __future__ import annotations

import unittest
from pathlib import Path

from mbti_tiktok_bot.catalog import GROUP_PALETTE_VARIANTS, GROUP_PALETTES


def _channel(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _luminance(hex_colour: str) -> float:
    r, g, b = (_channel(int(hex_colour[i : i + 2], 16) / 255) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(left: str, right: str) -> float:
    a, b = _luminance(left), _luminance(right)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


WHITE = "#ffffff"


class PaletteContrastTests(unittest.TestCase):
    """The floors below are why accent_deep exists.

    Before it, white label text sat on the raw accent at 1.57:1 for 探検家 and
    2.00:1 for 番人, which is not readable at any size.
    """

    def test_every_palette_carries_white_text_on_its_pill_colour(self) -> None:
        for group, variants in GROUP_PALETTE_VARIANTS.items():
            for palette in variants:
                with self.subTest(group=group, palette=palette.name):
                    self.assertGreaterEqual(contrast(palette.accent_deep, WHITE), 4.5)

    def test_every_palette_carries_white_text_on_its_background(self) -> None:
        for group, variants in GROUP_PALETTE_VARIANTS.items():
            for palette in variants:
                with self.subTest(group=group, palette=palette.name):
                    self.assertGreaterEqual(contrast(palette.background, WHITE), 7.0)

    def test_light_panels_read_against_the_background(self) -> None:
        for group, variants in GROUP_PALETTE_VARIANTS.items():
            for palette in variants:
                with self.subTest(group=group, palette=palette.name):
                    self.assertGreaterEqual(contrast(palette.light, palette.background), 7.0)

    def test_accents_are_distinct(self) -> None:
        # _pill_fill maps accent to accent_deep, so a duplicate accent would
        # silently give one palette another's pill colour.
        accents = [p.accent for variants in GROUP_PALETTE_VARIANTS.values() for p in variants]
        self.assertEqual(len(accents), len(set(accents)))

    def test_legacy_alias_still_points_at_the_first_variant(self) -> None:
        for group, variants in GROUP_PALETTE_VARIANTS.items():
            self.assertEqual(
                GROUP_PALETTES[group],
                (variants[0].background, variants[0].accent, variants[0].light),
            )


if __name__ == "__main__":
    unittest.main()


class ContrastTests(unittest.TestCase):
    """Every piece of type a look sets, on every palette, at a readable ratio.

    The brutal look was setting black type on a saturated mid-lightness field,
    where neither black nor white gets past 4:1 - and mapping the characters
    between the two, which turned them grey. Colours are chosen by measurement
    now, so this walks all of them.
    """

    def test_every_look_reads_on_every_palette(self) -> None:
        from mbti_tiktok_bot.config import load_config
        from mbti_tiktok_bot.design import contrast
        from mbti_tiktok_bot.design.core import Context
        from mbti_tiktok_bot.design.looks import LOOKS

        config = load_config(Path.cwd())
        for group, variants in GROUP_PALETTE_VARIANTS.items():
            for palette in variants:
                for name, look_class in LOOKS.items():
                    # Brutal picks a loud or a quiet field from the seed; both run.
                    for seed in (1, 2):
                        look = look_class(Context(config=config, palette=palette, seed=seed, scale=1))
                        for what, ink, behind in look.pairs():
                            with self.subTest(look=name, palette=palette.name, element=what):
                                self.assertGreaterEqual(
                                    contrast.ratio(ink, behind), contrast.BODY,
                                    f"{what}: {ink} on {behind}",
                                )

    def test_a_field_is_never_left_in_the_middle(self) -> None:
        from mbti_tiktok_bot.design import contrast

        for group, variants in GROUP_PALETTE_VARIANTS.items():
            for palette in variants:
                for dark in (True, False):
                    field = contrast.ground(palette.accent, dark=dark)
                    with self.subTest(palette=palette.name, dark=dark):
                        if dark:
                            self.assertLessEqual(contrast.luminance(field), contrast.DEEP + 0.01)
                        else:
                            self.assertGreaterEqual(contrast.luminance(field), contrast.PALE - 0.01)
