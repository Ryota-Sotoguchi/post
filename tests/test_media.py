from __future__ import annotations

import inspect
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

from mbti_tiktok_bot.config import load_config
from mbti_tiktok_bot.fonts import load_font
from mbti_tiktok_bot.models import CLOSER_SCENE_BODY, CLOSER_SCENE_TITLE, ContentPackage, Scene
from mbti_tiktok_bot.pipeline import _build_render_package
from mbti_tiktok_bot.planner import build_template_package, resolve_target_date
from mbti_tiktok_bot.visuals import _avoid_title_panel_box, _character_box, _draw_pulse_thumbnail_overlay, _draw_thumbnail_overlay, _fit_text_block, _fit_wrapped_text, _layout_profile, _motif_key, _render_character_overlay, _scene_style_index, _scene_style_key, _scene_top_clearance, _scene_top_shift, _slam_body_layout, _slam_body_max_height, _slam_label_box, _stack_top, _thumbnail_layout, _title_layout, _topic_visual_key, _visual_identity, _wrap_text, generate_scene_assets


def _boxes_overlap(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> bool:
    return min(left[2], right[2]) > max(left[0], right[0]) and min(left[3], right[3]) > max(left[1], right[1])


class MediaTests(unittest.TestCase):
    def test_fit_wrapped_text_shrinks_into_box(self) -> None:
        image = Image.new("RGBA", (800, 800), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image)

        wrapped, font, spacing = _fit_wrapped_text(
            draw,
            "A型の人が見ても気にならないように、長い文でも枠にきれいに収めたい。",
            260,
            120,
            56,
            bold=True,
            spacing=10,
            min_size=24,
            min_spacing=4,
        )

        text_box = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=spacing)
        self.assertLessEqual(text_box[2] - text_box[0], 260)
        self.assertLessEqual(text_box[3] - text_box[1], 120)

    def test_wrap_text_avoids_starting_lines_with_punctuation(self) -> None:
        image = Image.new("RGBA", (800, 800), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()

        wrapped = _wrap_text(draw, "INTJに刺さる接し方、外すと一気に遠のく", font, 80)

        for line in wrapped.splitlines()[1:]:
            self.assertNotIn(line[:1], "、。！？")

    def test_wrap_text_avoids_orphaned_japanese_word_endings(self) -> None:
        image = Image.new("RGBA", (1080, 1920), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image)
        font = load_font(48, bold=True)

        wrapped = _wrap_text(
            draw,
            "会話じゃない、行動で分かる — INFJの脈ありサイン",
            font,
            500,
        )

        for line in wrapped.splitlines()[1:]:
            self.assertNotIn(line[:1], "るれたてないますです")
            self.assertGreater(len(line), 2)

    def test_fit_text_keeps_theme_phrases_on_one_line(self) -> None:
        image = Image.new("RGBA", (1080, 1920), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image)

        wrapped, _, _ = _fit_wrapped_text(
            draw,
            "INTJが仲良くなるほど出る素の反応",
            570,
            430,
            92,
            bold=True,
            spacing=12,
            min_size=48,
            min_spacing=6,
        )

        self.assertNotIn("ほ\nど", wrapped)
        self.assertNotIn("出\nる", wrapped)
        self.assertNotIn("素の\n反応", wrapped)

    def test_build_render_package_adds_thumbnail_and_caps_contents_at_ten(self) -> None:
        config = load_config(Path.cwd())
        package = build_template_package(resolve_target_date("2026-04-22"), config, explicit_mbti="ENFP")
        expanded_package = replace(
            package,
            scenes=[Scene(title=f"Scene {index}", body="body") for index in range(12)],
        )

        render_package = _build_render_package(expanded_package)

        self.assertEqual(len(render_package.scenes), 12)
        self.assertEqual(render_package.scenes[0].title, package.title)
        self.assertEqual(render_package.scenes[0].body, package.hook)
        self.assertEqual(render_package.scenes[-1].title, CLOSER_SCENE_TITLE)
        self.assertEqual(render_package.scenes[-1].body, CLOSER_SCENE_BODY)

    def test_thumbnail_overlays_do_not_render_a_theme_label(self) -> None:
        config = load_config(Path.cwd())
        package = build_template_package(resolve_target_date("2026-04-22"), config, explicit_mbti="ENFP")

        self.assertNotIn("テーマ：", inspect.getsource(_draw_thumbnail_overlay))
        self.assertNotIn("テーマ：", inspect.getsource(_draw_pulse_thumbnail_overlay))
        self.assertFalse(_visual_identity(package)["thumbnail_theme_label"])
        self.assertEqual(_visual_identity(package)["design_tier"], "deluxe")

    def test_scene_style_index_aligns_first_content_slide_after_thumbnail(self) -> None:
        config = load_config(Path.cwd())
        package = build_template_package(resolve_target_date("2026-04-22"), config, explicit_mbti="ENFP")
        render_package = _build_render_package(package)

        first_content_style = _scene_style_index(render_package, 1)
        second_content_style = _scene_style_index(render_package, 2)

        self.assertEqual(second_content_style, (first_content_style + 1) % 5)

    def test_scene_style_key_is_consistent_for_chat_topic_across_mbti_types(self) -> None:
        config = load_config(Path.cwd())
        first_package = build_template_package(
            resolve_target_date("2026-04-22"),
            config,
            explicit_mbti="ENFP",
            explicit_format="のLINEが急に変わる瞬間",
        )
        second_package = build_template_package(
            resolve_target_date("2026-04-22"),
            config,
            explicit_mbti="INTJ",
            explicit_format="のLINEが急に変わる瞬間",
        )

        self.assertEqual(
            _scene_style_key(first_package, first_package.scenes[0], 0),
            _scene_style_key(second_package, second_package.scenes[0], 0),
        )

    def test_motif_key_changes_with_theme(self) -> None:
        config = load_config(Path.cwd())
        package = build_template_package(resolve_target_date("2026-04-22"), config, explicit_mbti="ENFP", explicit_format="の攻略で効く接し方")

        self.assertEqual(_motif_key(package), "grid")

    def test_topic_visual_key_uses_topic_specific_illustration_direction(self) -> None:
        config = load_config(Path.cwd())
        signal_package = build_template_package(
            resolve_target_date("2026-04-22"),
            config,
            explicit_mbti="ENFP",
            explicit_format="が脈ありの時にする行動",
        )
        trust_package = build_template_package(
            resolve_target_date("2026-04-22"),
            config,
            explicit_mbti="ENFP",
            explicit_format="が本気で心を許したサイン",
        )

        self.assertEqual(_topic_visual_key(signal_package), "signal")
        self.assertEqual(_topic_visual_key(trust_package), "trust")
        self.assertNotEqual(_visual_identity(signal_package)["topic_key"], _visual_identity(trust_package)["topic_key"])

    def test_character_illustration_changes_across_topics_and_mbti_types(self) -> None:
        config = load_config(Path.cwd())
        signal_enfp = build_template_package(
            resolve_target_date("2026-04-22"),
            config,
            explicit_mbti="ENFP",
            explicit_format="が脈ありの時にする行動",
        )
        trust_enfp = build_template_package(
            resolve_target_date("2026-04-22"),
            config,
            explicit_mbti="ENFP",
            explicit_format="が本気で心を許したサイン",
        )
        signal_enfj = build_template_package(
            resolve_target_date("2026-04-22"),
            config,
            explicit_mbti="ENFJ",
            explicit_format="が脈ありの時にする行動",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = [root / "signal_enfp.png", root / "trust_enfp.png", root / "signal_enfj.png"]
            _render_character_overlay(signal_enfp, config, paths[0])
            _render_character_overlay(trust_enfp, config, paths[1])
            _render_character_overlay(signal_enfj, config, paths[2])
            with Image.open(paths[0]) as first, Image.open(paths[1]) as second, Image.open(paths[2]) as third:
                self.assertIsNotNone(ImageChops.difference(first, second).getbbox())
                self.assertIsNotNone(ImageChops.difference(first, third).getbbox())

    def test_layout_boxes_change_by_motif(self) -> None:
        config = load_config(Path.cwd())
        chat_package = build_template_package(resolve_target_date("2026-04-22"), config, explicit_mbti="ENFP", explicit_format="のLINEが急に変わる瞬間")
        grid_package = build_template_package(resolve_target_date("2026-04-22"), config, explicit_mbti="INTJ", explicit_format="の攻略で効く接し方")

        self.assertNotEqual(_title_layout(chat_package)["panel"], _title_layout(grid_package)["panel"])
        self.assertNotEqual(_thumbnail_layout(chat_package)["card"], _thumbnail_layout(grid_package)["card"])
        self.assertNotEqual(_character_box(chat_package), _character_box(grid_package))

    def test_layout_profile_nudges_same_genre_for_dense_copy(self) -> None:
        sparse_package = ContentPackage(
            post_date="2026-04-22",
            mbti_type="ENFP",
            archetype_name="運動家",
            group_name="外交官",
            title="ENFPのLINEで出る差",
            series_name="のLINEが急に変わる瞬間",
            format_name="のLINEが急に変わる瞬間",
            theme="恋愛",
            hook="返信で温度差が出る",
            narration="",
            caption="",
            hashtags=[],
            scenes=[Scene(title="返信の温度差", body="短い本文")],
        )
        dense_package = ContentPackage(
            post_date="2026-04-22",
            mbti_type="ENFP",
            archetype_name="運動家",
            group_name="外交官",
            title="ENFPのLINEが本気になると返信の空気まで変わる瞬間",
            series_name="のLINEが急に変わる瞬間",
            format_name="のLINEが急に変わる瞬間",
            theme="恋愛",
            hook="返信のテンポだけでなく、話題の残し方と温度感まで一気に変わる",
            narration="",
            caption="",
            hashtags=[],
            scenes=[Scene(title="返信の温度差", body="かなり長めの本文で、言い方や距離感、返し方の癖まで含めて見せたいケース")],
        )

        self.assertNotEqual(_layout_profile(sparse_package).thumbnail_card, _layout_profile(dense_package).thumbnail_card)

    def test_layout_profile_is_consistent_for_same_topic_across_mbti_types(self) -> None:
        config = load_config(Path.cwd())
        primary_package = build_template_package(
            resolve_target_date("2026-04-22"),
            config,
            explicit_mbti="INTJ",
            explicit_format="の攻略で効く接し方",
            global_post_index=0,
        )
        alternate_package = build_template_package(
            resolve_target_date("2026-04-22"),
            config,
            explicit_mbti="ENFP",
            explicit_format="の攻略で効く接し方",
            global_post_index=1,
        )

        self.assertEqual(_motif_key(primary_package), _motif_key(alternate_package))
        self.assertEqual(_title_layout(primary_package)["panel"], _title_layout(alternate_package)["panel"])
        self.assertEqual(_thumbnail_layout(primary_package)["card"], _thumbnail_layout(alternate_package)["card"])
        self.assertEqual(_character_box(primary_package), _character_box(alternate_package))

    def test_thumbnail_and_second_slide_use_different_material_compositions(self) -> None:
        config = load_config(Path.cwd())
        package = build_template_package(
            resolve_target_date("2026-04-22"),
            config,
            explicit_mbti="ENFP",
            explicit_format="が脈ありの時にする行動",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            thumbnail_path = root / "character_01.png"
            second_slide_path = root / "character_02.png"
            _render_character_overlay(package, config, thumbnail_path, scene_index=0)
            _render_character_overlay(package, config, second_slide_path, scene_index=1)

            with Image.open(thumbnail_path) as thumbnail, Image.open(second_slide_path) as second_slide:
                self.assertIsNotNone(ImageChops.difference(thumbnail, second_slide).getbbox())

    def test_missing_provided_material_is_an_error_instead_of_generating_an_avatar(self) -> None:
        package = build_template_package(
            resolve_target_date("2026-04-22"),
            load_config(Path.cwd()),
            explicit_mbti="ENFP",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            empty_root = Path(temp_dir)
            config = replace(
                load_config(Path.cwd()),
                assets_dir=empty_root / "assets",
                official_images_dir=empty_root / "images",
            )
            with self.assertRaises(FileNotFoundError):
                _render_character_overlay(package, config, empty_root / "character.png")

    def test_pulse_character_stays_clear_of_text_cards_for_all_variants(self) -> None:
        config = load_config(Path.cwd())
        for global_post_index in (0, 1, 2):
            with self.subTest(global_post_index=global_post_index):
                package = build_template_package(
                    resolve_target_date("2026-04-22"),
                    config,
                    explicit_mbti="INFP",
                    explicit_format="がしんどい時に出るサイン",
                    global_post_index=global_post_index,
                )

                self.assertEqual(_motif_key(package), "pulse")
                character_box = _character_box(package)
                character_visual_box = (
                    character_box[0],
                    character_box[1],
                    character_box[2],
                    character_box[3] + 30,
                )
                title_panel = _title_layout(package)["panel"]
                thumbnail_card = _thumbnail_layout(package)["card"]

                self.assertFalse(_boxes_overlap(character_visual_box, title_panel))
                self.assertFalse(_boxes_overlap(character_visual_box, thumbnail_card))
                self.assertGreaterEqual(min(title_panel[1], thumbnail_card[1]) - character_visual_box[3], 80)

    def test_visuals_source_does_not_contain_internal_helper_copy(self) -> None:
        source = (Path.cwd() / "src" / "mbti_tiktok_bot" / "visuals.py").read_text(encoding="utf-8")

        self.assertNotIn("def _draw_avatar_overlay", source)
        for phrase in (
            "会話の空気はここで出る",
            "この言い回しが温度差になる",
            "ここだけは強く伝える",
            "長文でも見る場所はここ",
            "最後はここだけ掴めばいい",
            "効くかどうかはここで分かれる",
            "感情が揺れる所はここ",
            "距離感はここで見える",
            "ここがいちばん見どころ",
        ):
            self.assertNotIn(phrase, source)

    def test_slam_layout_keeps_body_above_footer_helper(self) -> None:
        image = Image.new("RGBA", (1080, 1920), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image)

        title, _, _, _, title_height = _fit_text_block(
            draw,
            "本命だけに出る空気",
            520,
            384,
            84,
            bold=True,
            spacing=2,
            min_size=52,
            min_spacing=0,
        )
        self.assertTrue(title)
        body_card_top = max(1120, _stack_top(654, 1088, [title_height]) + title_height + 96)
        body, _, _, _, body_height = _fit_text_block(
            draw,
            "少人数で深くつながる。軽いノリだけで終わらせないならかなり強い。",
            588,
            _slam_body_max_height(body_card_top),
            46,
            spacing=18,
            min_size=30,
            min_spacing=10,
        )
        self.assertTrue(body)
        body_y, body_card_bottom = _slam_body_layout(body_card_top, body_height)

        self.assertLessEqual(body_y + body_height, body_card_bottom - 48)

    def test_avoid_title_panel_box_moves_slam_label_below_default_title_panel(self) -> None:
        config = load_config(Path.cwd())
        package = build_template_package(resolve_target_date("2026-04-22"), config, explicit_mbti="INTJ")
        shifted_box = _slam_label_box(package)
        title_panel = _title_layout(package)["panel"]

        self.assertGreaterEqual(shifted_box[1], title_panel[3] + 24)

    def test_avoid_title_panel_box_keeps_box_when_already_clear_of_low_panel(self) -> None:
        config = load_config(Path.cwd())
        package = build_template_package(resolve_target_date("2026-04-22"), config, explicit_mbti="INTJ", explicit_format="の攻略で効く接し方")
        base_box = (80, 520, 330, 604)
        shifted_box = _avoid_title_panel_box(package, base_box)

        self.assertEqual(shifted_box, base_box)

    def test_scene_top_shift_pushes_top_elements_below_title_panel(self) -> None:
        config = load_config(Path.cwd())
        package = build_template_package(resolve_target_date("2026-04-22"), config, explicit_mbti="INTJ")
        shifted_top = 560 + _scene_top_shift(package, 560)

        self.assertGreaterEqual(shifted_top, _scene_top_clearance(package))

    def test_scene_top_shift_keeps_clear_elements_in_place(self) -> None:
        config = load_config(Path.cwd())
        package = build_template_package(resolve_target_date("2026-04-22"), config, explicit_mbti="INTJ")

        self.assertEqual(_scene_top_shift(package, 676), 0)

    def test_slam_layout_keeps_title_below_dynamic_point_label(self) -> None:
        config = load_config(Path.cwd())
        package = build_template_package(resolve_target_date("2026-04-22"), config, explicit_mbti="INTJ")
        image = Image.new("RGBA", (1080, 1920), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image)

        _, _, _, _, title_height = _fit_text_block(
            draw,
            "本命だけに出る空気",
            520,
            384,
            84,
            bold=True,
            spacing=2,
            min_size=52,
            min_spacing=0,
        )
        label_box = _slam_label_box(package)
        title_top = max(_stack_top(654, 1088, [title_height]), label_box[3] + 36)

        self.assertGreaterEqual(title_top - label_box[3], 36)

    def test_generate_scene_assets_keeps_final_slides_separate_from_layer_outputs(self) -> None:
        config = replace(load_config(Path.cwd()), video_width=540, video_height=960)
        package = build_template_package(resolve_target_date("2026-04-22"), config, explicit_mbti="ENFP")

        with tempfile.TemporaryDirectory() as temp_dir:
            slides_dir = Path(temp_dir)
            assets = generate_scene_assets(package, config, slides_dir)

            self.assertEqual(len(assets), len(package.scenes))
            self.assertTrue(assets[0].background_path.exists())
            self.assertTrue(assets[0].text_overlay_path and assets[0].text_overlay_path.exists())
            self.assertTrue(assets[0].character_overlay_path and assets[0].character_overlay_path.exists())
            self.assertTrue(assets[0].accent_overlay_path and assets[0].accent_overlay_path.exists())
            self.assertTrue((slides_dir / "slide_01.png").exists())
            self.assertFalse((slides_dir / "base_01.png").exists())
            self.assertFalse((slides_dir / "accent_01.png").exists())
            self.assertFalse((slides_dir / "text_01.png").exists())
            self.assertTrue((slides_dir.parent / "_render" / "base_01.png").exists())
            with Image.open(slides_dir / "slide_01.png") as slide:
                self.assertEqual(slide.mode, "RGB")


if __name__ == "__main__":
    unittest.main()
