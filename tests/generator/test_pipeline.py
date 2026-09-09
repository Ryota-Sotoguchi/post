from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from mbti_tiktok_bot.config import load_config
from mbti_tiktok_bot.models import ContentPackage, Scene
from mbti_tiktok_bot.pipeline import ContentOverlap, build_daily_bundles, render_content_package


def _package(title: str, series_name: str) -> ContentPackage:
    scenes = [
        Scene("返事が短くなる瞬間", "普段より相づちだけになり、質問が減る。"),
        Scene("まだ笑っている段階", "表情は保つが、自分から話題を足さなくなる。"),
        Scene("声をかけるなら", "詰めずに逃げ場を残す声かけが効く。"),
    ]
    return ContentPackage(
        post_date="2026-05-27",
        mbti_type="ESFJ",
        archetype_name="領事",
        group_name="番人",
        title=title,
        series_name=series_name,
        format_name=series_name,
        theme="心理",
        hook="限界前に静かな違和感が出る",
        narration="",
        caption="",
        hashtags=["#MBTI", "#ESFJ"],
        global_post_index=1,
        daily_slot=1,
        series_post_number=1,
        scenes=scenes,
    )


class PipelineTests(unittest.TestCase):
    def test_render_blocks_existing_output_with_80_percent_content_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = replace(
                load_config(Path.cwd()),
                project_root=root,
                output_dir=root / "out",
                state_dir=root / "state",
                openai_api_key=None,
            )
            existing_dir = config.output_dir / "過去ネタ" / "post_01_ESFJ"
            existing_dir.mkdir(parents=True)
            existing_package = _package("ESFJがしんどい時に出るサイン", "がしんどい時に出るサイン")
            (existing_dir / "package.json").write_text(
                json.dumps(existing_package.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            new_package = _package("ESFJが限界前に見せる口数の変化", "が限界前に見せる口数の変化")

            with patch("mbti_tiktok_bot.pipeline.generate_scene_assets"):
                with self.assertRaisesRegex(ValueError, "overlaps an existing package"):
                    render_content_package(new_package, config, config.output_dir / "新ネタ" / "post_01_ESFJ")

    def test_overlapping_topic_is_retired_instead_of_failing_the_slot(self) -> None:
        # The slot used to die here with a ValueError and retry the same topic
        # on every trigger, which stopped generation for three days.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = replace(
                load_config(Path.cwd()),
                project_root=root,
                output_dir=root / "out",
                state_dir=root / "state",
                openai_api_key=None,
            )
            good = _package("ESFJが別ネタで見せる反応", "が別ネタで見せる反応")
            calls = {"n": 0}

            def render(package, cfg, output_dir):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise ContentOverlap("overlaps an existing package", 0)
                return object()

            with patch("mbti_tiktok_bot.pipeline.build_daily_packages", return_value=[good]), \
                 patch("mbti_tiktok_bot.pipeline.render_content_package", side_effect=render), \
                 patch(
                     "mbti_tiktok_bot.pipeline.retire_topic_at",
                     return_value={"name": "が入れ替わったネタ", "theme": "心理", "blueprint": "stress_signal"},
                 ) as retire:
                results = build_daily_bundles(
                    target_date=date(2026, 5, 27), config=config, count=1
                )

            self.assertEqual(len(results), 1)
            retire.assert_called_once()
            self.assertEqual(retire.call_args.args[1], 0)

    def test_slot_still_fails_once_the_retirement_budget_is_spent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = replace(
                load_config(Path.cwd()),
                project_root=root,
                output_dir=root / "out",
                state_dir=root / "state",
                openai_api_key=None,
            )
            good = _package("ESFJが別ネタで見せる反応", "が別ネタで見せる反応")

            def always_overlap(package, cfg, output_dir):
                raise ContentOverlap("overlaps an existing package", 0)

            with patch("mbti_tiktok_bot.pipeline.build_daily_packages", return_value=[good]), \
                 patch("mbti_tiktok_bot.pipeline.render_content_package", side_effect=always_overlap), \
                 patch(
                     "mbti_tiktok_bot.pipeline.retire_topic_at",
                     return_value={"name": "x", "theme": "心理", "blueprint": "stress_signal"},
                 ):
                with self.assertRaises(ContentOverlap):
                    build_daily_bundles(target_date=date(2026, 5, 27), config=config, count=1)


if __name__ == "__main__":
    unittest.main()
