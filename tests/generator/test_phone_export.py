from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PIL import Image, PngImagePlugin

import mbti_tiktok_bot.phone_export as phone_export
from mbti_tiktok_bot.config import load_config
from mbti_tiktok_bot.phone_export import export_daily_results_to_phone
from mbti_tiktok_bot.pipeline import PipelineResult


def _write_phone_slide(path: Path, color: tuple[int, int, int] = (24, 77, 59), size: tuple[int, int] = (1080, 1920)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


class PhoneExportTests(unittest.TestCase):
    def test_clean_rebuild_clears_all_topics_before_copying_any_topic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = replace(
                load_config(Path.cwd()),
                project_root=root,
                output_dir=root / "out",
                state_dir=root / "state",
                phone_export_auto=True,
                phone_export_dir=root / "delivery" / "phone",
            )
            results = []
            stale_markers = []
            for index, topic in enumerate(("topic-one", "topic-two"), start=1):
                output_dir = config.output_dir / topic / f"post_0{index}_INTJ"
                slide_path = output_dir / "slides" / "slide_01.png"
                _write_phone_slide(slide_path)
                results.append(
                    PipelineResult(
                        output_dir=output_dir,
                        package_path=output_dir / "package.json",
                        caption_path=output_dir / "caption.txt",
                        title=topic,
                        mbti_type="INTJ",
                        daily_slot=index,
                        global_post_index=index - 1,
                        media_paths=[slide_path],
                    )
                )
                marker = config.phone_export_dir / topic / "stale-cache.png"
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_bytes(b"stale")
                stale_markers.append(marker)

            copy_impl = phone_export._copy_post_images
            clean_phase_observations: list[bool] = []

            def copy_after_clean(*args, **kwargs):
                clean_phase_observations.append(all(not marker.exists() for marker in stale_markers))
                return copy_impl(*args, **kwargs)

            with patch("mbti_tiktok_bot.phone_export._copy_post_images", side_effect=copy_after_clean):
                export_daily_results_to_phone(config, date(2026, 4, 24), results)

            self.assertEqual(clean_phase_observations, [True, True])
            self.assertTrue(all(not marker.exists() for marker in stale_markers))

    def test_export_daily_results_copies_only_topic_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "out" / "が好きな人に見せる態度" / "post_01_INTJ"
            slides_dir = output_dir / "slides"
            slides_dir.mkdir(parents=True, exist_ok=True)
            _write_phone_slide(slides_dir / "slide_01.png")
            _write_phone_slide(slides_dir / "slide_02.png", color=(63, 191, 127))
            (output_dir / "caption.txt").write_text("caption line", encoding="utf-8")
            (output_dir / "package.json").write_text("{}", encoding="utf-8")
            (output_dir / "script.txt").write_text("script", encoding="utf-8")

            config = replace(
                load_config(Path.cwd()),
                project_root=root,
                output_dir=root / "out",
                state_dir=root / "state",
                phone_export_auto=True,
                phone_export_dir=root / "delivery" / "phone",
            )
            result = PipelineResult(
                output_dir=output_dir,
                package_path=output_dir / "package.json",
                caption_path=output_dir / "caption.txt",
                title="INTJが好きな人に見せる態度",
                mbti_type="INTJ",
                daily_slot=1,
                global_post_index=0,
                media_paths=[slides_dir / "slide_01.png", slides_dir / "slide_02.png"],
            )

            export_result = export_daily_results_to_phone(config, date(2026, 4, 24), [result])

            self.assertEqual(export_result.post_count, 1)
            self.assertEqual(export_result.export_dir, config.phone_export_dir / "が好きな人に見せる態度")
            self.assertTrue((export_result.export_dir / "post_01_INTJ" / "slide_01.png").exists())
            self.assertFalse((export_result.export_dir / "post_01_INTJ" / "caption.txt").exists())
            self.assertFalse((config.phone_export_dir / "latest").exists())

    def test_export_daily_results_can_append_to_existing_topic_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            topic_dir = root / "out" / "が好きな人に見せる態度"
            first_output_dir = topic_dir / "post_01_INTJ"
            second_output_dir = topic_dir / "post_02_ENTP"
            for output_dir, mbti in [(first_output_dir, "INTJ"), (second_output_dir, "ENTP")]:
                slides_dir = output_dir / "slides"
                slides_dir.mkdir(parents=True, exist_ok=True)
                _write_phone_slide(slides_dir / "slide_01.png")
                (output_dir / "caption.txt").write_text(f"caption {mbti}", encoding="utf-8")
                (output_dir / "package.json").write_text("{}", encoding="utf-8")
                (output_dir / "script.txt").write_text("script", encoding="utf-8")

            config = replace(
                load_config(Path.cwd()),
                project_root=root,
                output_dir=root / "out",
                state_dir=root / "state",
                phone_export_auto=True,
                phone_export_dir=root / "delivery" / "phone",
            )
            first_result = PipelineResult(
                output_dir=first_output_dir,
                package_path=first_output_dir / "package.json",
                caption_path=first_output_dir / "caption.txt",
                title="INTJが好きな人に見せる態度",
                mbti_type="INTJ",
                daily_slot=1,
                global_post_index=0,
                media_paths=[first_output_dir / "slides" / "slide_01.png"],
            )
            second_result = PipelineResult(
                output_dir=second_output_dir,
                package_path=second_output_dir / "package.json",
                caption_path=second_output_dir / "caption.txt",
                title="ENTPが好きな人に見せる態度",
                mbti_type="ENTP",
                daily_slot=1,
                global_post_index=1,
                media_paths=[second_output_dir / "slides" / "slide_01.png"],
            )

            export_daily_results_to_phone(config, date(2026, 4, 24), [first_result])
            export_daily_results_to_phone(
                config,
                date(2026, 4, 24),
                [second_result],
                reset_export_dir=False,
            )

            self.assertTrue((config.phone_export_dir / "が好きな人に見せる態度" / "post_01_INTJ").exists())
            self.assertTrue((config.phone_export_dir / "が好きな人に見せる態度" / "post_02_ENTP").exists())
            self.assertTrue((config.phone_export_dir / "が好きな人に見せる態度" / "post_01_INTJ" / "slide_01.png").exists())
            self.assertFalse((config.phone_export_dir / "latest").exists())

    def test_export_daily_results_skips_render_working_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "out" / "が好きな人に見せる態度" / "post_01_INTJ"
            slides_dir = output_dir / "slides"
            render_dir = output_dir / "_render"
            slides_dir.mkdir(parents=True, exist_ok=True)
            render_dir.mkdir(parents=True, exist_ok=True)
            _write_phone_slide(slides_dir / "slide_01.png")
            (render_dir / "base_01.png").write_bytes(b"base")
            (output_dir / "caption.txt").write_text("caption", encoding="utf-8")
            (output_dir / "package.json").write_text("{}", encoding="utf-8")
            (output_dir / "script.txt").write_text("script", encoding="utf-8")

            config = replace(
                load_config(Path.cwd()),
                project_root=root,
                output_dir=root / "out",
                state_dir=root / "state",
                phone_export_auto=True,
                phone_export_dir=root / "delivery" / "phone",
            )
            result = PipelineResult(
                output_dir=output_dir,
                package_path=output_dir / "package.json",
                caption_path=output_dir / "caption.txt",
                title="INTJが好きな人に見せる態度",
                mbti_type="INTJ",
                daily_slot=1,
                global_post_index=0,
                media_paths=[slides_dir / "slide_01.png"],
            )

            export_daily_results_to_phone(config, date(2026, 4, 24), [result])

            self.assertTrue((config.phone_export_dir / "が好きな人に見せる態度" / "post_01_INTJ" / "slide_01.png").exists())
            self.assertFalse((config.phone_export_dir / "が好きな人に見せる態度" / "post_01_INTJ" / "_render").exists())
            self.assertFalse((config.phone_export_dir / "が好きな人に見せる態度" / "post_01_INTJ" / "slides").exists())

    def test_export_daily_results_removes_legacy_latest_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "out" / "が好きな人に見せる態度" / "post_01_INTJ"
            slides_dir = output_dir / "slides"
            slides_dir.mkdir(parents=True, exist_ok=True)
            _write_phone_slide(slides_dir / "slide_01.png")
            legacy_latest_dir = root / "delivery" / "phone" / "latest"
            legacy_latest_dir.mkdir(parents=True, exist_ok=True)
            (legacy_latest_dir / "old.txt").write_text("legacy", encoding="utf-8")

            config = replace(
                load_config(Path.cwd()),
                project_root=root,
                output_dir=root / "out",
                state_dir=root / "state",
                phone_export_auto=True,
                phone_export_dir=root / "delivery" / "phone",
            )
            result = PipelineResult(
                output_dir=output_dir,
                package_path=output_dir / "package.json",
                caption_path=output_dir / "caption.txt",
                title="INTJが好きな人に見せる態度",
                mbti_type="INTJ",
                daily_slot=1,
                global_post_index=0,
                media_paths=[slides_dir / "slide_01.png"],
            )

            export_daily_results_to_phone(config, date(2026, 4, 24), [result])

            self.assertFalse(legacy_latest_dir.exists())

    def test_export_daily_results_rejects_non_rgb_phone_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "out" / "が好きな人に見せる態度" / "post_01_INTJ"
            slides_dir = output_dir / "slides"
            slides_dir.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (1080, 1920), (24, 77, 59, 180)).save(slides_dir / "slide_01.png")

            config = replace(
                load_config(Path.cwd()),
                project_root=root,
                output_dir=root / "out",
                state_dir=root / "state",
                phone_export_auto=True,
                phone_export_dir=root / "delivery" / "phone",
            )
            result = PipelineResult(
                output_dir=output_dir,
                package_path=output_dir / "package.json",
                caption_path=output_dir / "caption.txt",
                title="INTJが好きな人に見せる態度",
                mbti_type="INTJ",
                daily_slot=1,
                global_post_index=0,
                media_paths=[slides_dir / "slide_01.png"],
            )

            with self.assertRaisesRegex(ValueError, "must be RGB"):
                export_daily_results_to_phone(config, date(2026, 4, 24), [result])

    def test_export_daily_results_rejects_wrong_phone_image_size(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "out" / "が好きな人に見せる態度" / "post_01_INTJ"
            slides_dir = output_dir / "slides"
            _write_phone_slide(slides_dir / "slide_01.png", size=(540, 960))

            config = replace(
                load_config(Path.cwd()),
                project_root=root,
                output_dir=root / "out",
                state_dir=root / "state",
                phone_export_auto=True,
                phone_export_dir=root / "delivery" / "phone",
            )
            result = PipelineResult(
                output_dir=output_dir,
                package_path=output_dir / "package.json",
                caption_path=output_dir / "caption.txt",
                title="INTJが好きな人に見せる態度",
                mbti_type="INTJ",
                daily_slot=1,
                global_post_index=0,
                media_paths=[slides_dir / "slide_01.png"],
            )

            with self.assertRaisesRegex(ValueError, "must be 1080x1920"):
                export_daily_results_to_phone(config, date(2026, 4, 24), [result])

    def test_export_daily_results_rewrites_png_without_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "out" / "topic" / "post_01_INTJ"
            slides_dir = output_dir / "slides"
            slides_dir.mkdir(parents=True, exist_ok=True)
            metadata = PngImagePlugin.PngInfo()
            metadata.add_text("source", "render-cache")
            source_path = slides_dir / "slide_01.png"
            Image.new("RGB", (1080, 1920), (24, 77, 59)).save(source_path, pnginfo=metadata)

            config = replace(
                load_config(Path.cwd()),
                project_root=root,
                output_dir=root / "out",
                state_dir=root / "state",
                phone_export_auto=True,
                phone_export_dir=root / "delivery" / "phone",
            )
            result = PipelineResult(
                output_dir=output_dir,
                package_path=output_dir / "package.json",
                caption_path=output_dir / "caption.txt",
                title="INTJ topic",
                mbti_type="INTJ",
                daily_slot=1,
                global_post_index=0,
                media_paths=[source_path],
            )

            export_daily_results_to_phone(config, date(2026, 4, 24), [result])

            exported_path = config.phone_export_dir / "topic" / "post_01_INTJ" / "slide_01.png"
            with Image.open(exported_path) as exported:
                self.assertEqual(exported.mode, "RGB")
                self.assertEqual(exported.size, (1080, 1920))
                self.assertNotIn("source", exported.info)


if __name__ == "__main__":
    unittest.main()
