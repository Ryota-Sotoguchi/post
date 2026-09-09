from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from mbti_tiktok_bot.config import load_config
from mbti_tiktok_bot.planner import build_template_package, resolve_target_date
from mbti_tiktok_bot.visuals import (
    ALL_MOTIFS,
    ILLUSTRATED_MOTIFS,
    _editorial_photo_plan,
    _editorial_photos,
    _motif_key,
)


class EditorialPhotoPlanTests(unittest.TestCase):
    """The pool is four photographs today, so the plan has to survive reuse."""

    def test_no_photos_produces_no_plan(self) -> None:
        self.assertEqual(_editorial_photo_plan(0, 12345, 7), [])

    def test_a_single_photo_still_fills_every_slide(self) -> None:
        plan = _editorial_photo_plan(1, 12345, 10)
        self.assertEqual(len(plan), 10)
        self.assertEqual({entry["index"] for entry in plan}, {0})
        # With one photo the crop and zoom are all that separate the slides.
        self.assertGreater(len({(e["centering"], e["zoom"]) for e in plan}), 1)

    def test_the_same_photo_never_lands_twice_in_a_row(self) -> None:
        for photo_count in (2, 3, 4, 5):
            for slides in (7, 8, 9, 10):
                with self.subTest(photos=photo_count, slides=slides):
                    order = [e["index"] for e in _editorial_photo_plan(photo_count, 999, slides)]
                    self.assertTrue(all(a != b for a, b in zip(order, order[1:])))

    def test_a_large_pool_gives_every_slide_its_own_photo(self) -> None:
        plan = _editorial_photo_plan(12, 4242, 10)
        self.assertEqual(len({entry["index"] for entry in plan}), 10)

    def test_plan_is_deterministic(self) -> None:
        self.assertEqual(_editorial_photo_plan(4, 77, 8), _editorial_photo_plan(4, 77, 8))


class EditorialMotifTests(unittest.TestCase):
    def test_motif_falls_back_when_there_are_no_photographs(self) -> None:
        config = load_config(Path.cwd())
        package = build_template_package(
            resolve_target_date("2026-04-22"), config, explicit_mbti="ENTP",
            explicit_format="が本命だけに見せる距離の縮め方",
        )
        # Same package, two pools. Without photographs the motif must resolve to
        # an illustrated one rather than producing blank slides.
        self.assertIn(_motif_key(package, available=ILLUSTRATED_MOTIFS), ILLUSTRATED_MOTIFS)
        self.assertIn(_motif_key(package, available=ALL_MOTIFS), ALL_MOTIFS)

    def test_an_empty_directory_reads_as_no_photos(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(_editorial_photos(temp_dir), ())
        self.assertEqual(_editorial_photos("/nonexistent-photo-directory"), ())

    def test_the_shipped_pool_is_found(self) -> None:
        config = load_config(Path.cwd())
        self.assertTrue(_editorial_photos(str(config.editorial_photos_dir)))


if __name__ == "__main__":
    unittest.main()
