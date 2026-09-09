from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from mbti_tiktok_bot.visuals import ScaledDraw, _measure_draw, _scale_xy


class ScaleXYTests(unittest.TestCase):
    def test_handles_every_coordinate_shape_the_renderer_uses(self) -> None:
        self.assertEqual(_scale_xy((10, 20), 2), (20, 40))
        self.assertEqual(_scale_xy((10, 20, 30, 40), 2), (20, 40, 60, 80))
        self.assertEqual(_scale_xy([(1, 2), (3, 4)], 2), [(2, 4), (6, 8)])
        self.assertEqual(_scale_xy(((1, 2), (3, 4)), 2), [(2, 4), (6, 8)])

    def test_scale_of_one_is_the_identity(self) -> None:
        box = (10, 20, 30, 40)
        self.assertIs(_scale_xy(box, 1), box)


class ScaledDrawTests(unittest.TestCase):
    def test_geometry_lands_at_the_same_place_as_an_unscaled_draw(self) -> None:
        plain = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        ImageDraw.Draw(plain).rectangle((10, 10, 40, 40), fill=(255, 0, 0, 255))

        scaled = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        ScaledDraw(scaled, 2).rectangle((10, 10, 40, 40), fill=(255, 0, 0, 255))

        self.assertEqual(plain.getbbox(), (10, 10, 41, 41))
        # getbbox is exclusive on the right and bottom edges.
        self.assertEqual(scaled.getbbox(), (20, 20, 81, 81))

    def test_arc_angles_are_not_scaled(self) -> None:
        # start and end are degrees. Scaling them would spin the artwork, and
        # the bug would only show at scale != 1.
        quarter = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        ScaledDraw(quarter, 2).arc((10, 10, 90, 90), 0, 90, fill=(255, 0, 0, 255), width=2)
        left, top, right, bottom = quarter.getbbox()
        # A 0..90 degree arc stays in the lower-right quadrant of its box.
        self.assertGreaterEqual(left, 100)
        self.assertGreaterEqual(top, 100)
        self.assertLessEqual(right, 182)
        self.assertLessEqual(bottom, 182)

    def test_unforwarded_methods_raise_instead_of_drawing_unscaled(self) -> None:
        canvas = ScaledDraw(Image.new("RGBA", (10, 10)), 2)
        with self.assertRaisesRegex(AttributeError, "does not forward"):
            canvas.textbbox

    def test_measurement_context_is_a_plain_draw_at_logical_scale(self) -> None:
        # Measuring through a scaled canvas would let the shrink-to-fit ladder
        # settle on sizes the 1x ladder cannot reach.
        self.assertIsInstance(_measure_draw(), ImageDraw.ImageDraw)

    def test_px_converts_logical_to_device(self) -> None:
        canvas = ScaledDraw(Image.new("RGBA", (10, 10)), 2)
        self.assertEqual(canvas.px(16), 32)
        self.assertEqual(canvas.blur(14).radius, 28)


if __name__ == "__main__":
    unittest.main()
