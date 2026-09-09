from __future__ import annotations

import unittest

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
