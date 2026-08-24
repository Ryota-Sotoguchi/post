from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from mbti_tiktok_bot.cli import _run_daily, _run_daemon, _run_slot
from mbti_tiktok_bot.config import load_config
from mbti_tiktok_bot.daemon import DaemonState, due_slots, normalize_times, pending_slot_runs
from mbti_tiktok_bot.models import ContentPackage, Scene
from mbti_tiktok_bot.pipeline import PipelineResult, build_daily_bundles, load_daily_results
from mbti_tiktok_bot.planner import load_series_state


class CliTests(unittest.TestCase):
    def test_normalize_times_sorts_and_deduplicates(self) -> None:
        self.assertEqual(normalize_times(["18:00", "08:00", "08:00", "12:00"]), ["08:00", "12:00", "18:00"])

    def test_due_slots_uses_today_state_only(self) -> None:
        current = due_slots(
            datetime(2026, 4, 28, 12, 5),
            ["08:00", "12:00", "18:00"],
            DaemonState(current_date="2026-04-28", completed_slots=["08:00"]),
        )
        self.assertEqual(current, ["12:00"])

    def test_pending_slot_runs_backfills_previous_days_before_today(self) -> None:
        pending = pending_slot_runs(
            datetime(2026, 4, 29, 8, 5),
            ["08:00", "12:00", "18:00"],
            DaemonState(current_date="2026-04-28", completed_slots=["08:00", "12:00"]),
        )
        self.assertEqual(pending, [("2026-04-28", "18:00"), ("2026-04-29", "08:00")])

    def test_pending_slot_runs_caps_backlog_after_a_long_outage(self) -> None:
        # State left behind by an outage must not fan out into months of posts.
        pending = pending_slot_runs(
            datetime(2026, 8, 25, 19, 0),
            ["08:00", "12:00", "18:00"],
            DaemonState(current_date="2026-06-01", completed_slots=["08:00"]),
        )

        self.assertEqual(
            pending,
            [
                ("2026-08-24", "08:00"),
                ("2026-08-24", "12:00"),
                ("2026-08-24", "18:00"),
                ("2026-08-25", "08:00"),
                ("2026-08-25", "12:00"),
                ("2026-08-25", "18:00"),
            ],
        )

    def test_run_daemon_invokes_slot_runner_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = replace(
                load_config(Path.cwd()),
                project_root=root,
                output_dir=root / "out",
                state_dir=root / "state",
                phone_export_auto=False,
                phone_export_dir=root / "delivery" / "phone",
            )
            args = Namespace(times=["08:00"], poll_seconds=30, dry_run=True, run_once=True)

            with patch("mbti_tiktok_bot.cli.load_config", return_value=config), patch(
                "mbti_tiktok_bot.cli._run_slot_command",
                return_value=0,
            ) as run_slot_mock, patch("mbti_tiktok_bot.daemon.datetime") as datetime_mock:
                datetime_mock.now.return_value = datetime(2026, 4, 28, 8, 1)
                datetime_mock.strptime.side_effect = datetime.strptime
                exit_code = _run_daemon(args)

            self.assertEqual(exit_code, 0)
            run_slot_mock.assert_called_once()

    def test_run_daemon_recovers_previous_day_backlog_before_today_slot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = replace(
                load_config(Path.cwd()),
                project_root=root,
                output_dir=root / "out",
                state_dir=root / "state",
                phone_export_auto=False,
                phone_export_dir=root / "delivery" / "phone",
            )
            args = Namespace(times=["08:00", "12:00", "18:00"], poll_seconds=30, dry_run=True, run_once=True)
            state_path = config.state_dir / "phone_export_daemon_state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(
                '{\n  "current_date": "2026-04-28",\n  "completed_slots": ["08:00", "12:00"]\n}',
                encoding="utf-8",
            )

            with patch("mbti_tiktok_bot.cli.load_config", return_value=config), patch(
                "mbti_tiktok_bot.cli._run_slot_command",
                return_value=0,
            ) as run_slot_mock, patch("mbti_tiktok_bot.daemon.datetime") as datetime_mock:
                datetime_mock.now.return_value = datetime(2026, 4, 29, 8, 1)
                datetime_mock.strptime.side_effect = datetime.strptime
                exit_code = _run_daemon(args)

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                [call.args[1].isoformat() for call in run_slot_mock.call_args_list],
                ["2026-04-28", "2026-04-29"],
            )
            self.assertEqual(
                (config.state_dir / "phone_export_daemon_state.json").read_text(encoding="utf-8").replace("\r\n", "\n"),
                '{\n  "current_date": "2026-04-29",\n  "completed_slots": [\n    "08:00"\n  ]\n}',
            )

    def test_run_daemon_reconciles_existing_outputs_before_filling_missing_slots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = replace(
                load_config(Path.cwd()),
                project_root=root,
                output_dir=root / "out",
                state_dir=root / "state",
                phone_export_auto=False,
                phone_export_dir=root / "delivery" / "phone",
            )
            args = Namespace(times=["08:00", "12:00", "18:00"], poll_seconds=30, dry_run=False, run_once=True)
            target_date = date(2026, 4, 29)
            series_dir = config.output_dir / "が好きな人に見せる態度"
            first_output_dir = series_dir / "post_01_INTJ"
            first_slides_dir = first_output_dir / "slides"
            first_slides_dir.mkdir(parents=True, exist_ok=True)
            (first_slides_dir / "slide_01.png").write_bytes(b"slide")
            (first_output_dir / "package.json").write_text("{}", encoding="utf-8")
            (first_output_dir / "caption.txt").write_text("caption", encoding="utf-8")
            (series_dir / "series_plan.json").write_text(
                json.dumps(
                    [
                        {
                            "post_date": target_date.isoformat(),
                            "title": "INTJタイトル",
                            "mbti_type": "INTJ",
                            "daily_slot": 1,
                            "global_post_index": 0,
                            "output_dir": str(first_output_dir),
                        }
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            state_path = config.state_dir / "phone_export_daemon_state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(
                '{\n  "current_date": "2026-04-29",\n  "completed_slots": []\n}',
                encoding="utf-8",
            )

            def _write_missing_slot(*args, **kwargs):
                second_output_dir = series_dir / "post_02_ENTP"
                second_slides_dir = second_output_dir / "slides"
                second_slides_dir.mkdir(parents=True, exist_ok=True)
                (second_slides_dir / "slide_01.png").write_bytes(b"slide")
                (second_output_dir / "package.json").write_text("{}", encoding="utf-8")
                (second_output_dir / "caption.txt").write_text("caption", encoding="utf-8")
                (series_dir / "series_plan.json").write_text(
                    json.dumps(
                        [
                            {
                                "post_date": target_date.isoformat(),
                                "title": "INTJタイトル",
                                "mbti_type": "INTJ",
                                "daily_slot": 1,
                                "global_post_index": 0,
                                "output_dir": str(first_output_dir),
                            },
                            {
                                "post_date": target_date.isoformat(),
                                "title": "ENTPタイトル",
                                "mbti_type": "ENTP",
                                "daily_slot": 1,
                                "global_post_index": 1,
                                "output_dir": str(second_output_dir),
                            },
                        ],
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                return 0

            with patch("mbti_tiktok_bot.cli.load_config", return_value=config), patch(
                "mbti_tiktok_bot.cli._run_slot_command",
                side_effect=_write_missing_slot,
            ) as run_slot_mock, patch("mbti_tiktok_bot.cli.export_daily_results_to_phone") as export_mock, patch(
                "mbti_tiktok_bot.cli.run_daemon",
                return_value=0,
            ), patch("mbti_tiktok_bot.cli.datetime") as datetime_mock:
                datetime_mock.now.return_value = datetime(2026, 4, 29, 12, 1)
                datetime_mock.strptime.side_effect = datetime.strptime
                exit_code = _run_daemon(args)

            self.assertEqual(exit_code, 0)
            run_slot_mock.assert_called_once()
            self.assertEqual(run_slot_mock.call_args.args[1].isoformat(), "2026-04-29")
            export_mock.assert_called_once()
            self.assertEqual(
                json.loads((config.state_dir / "phone_export_daemon_state.json").read_text(encoding="utf-8")),
                {"current_date": "2026-04-29", "completed_slots": ["08:00", "12:00"]},
            )

    def test_build_daily_bundles_appends_series_summary_for_slot_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = replace(
                load_config(Path.cwd()),
                project_root=root,
                output_dir=root / "out",
                state_dir=root / "state",
                phone_export_auto=False,
                phone_export_dir=root / "delivery" / "phone",
            )
            first_package = ContentPackage(
                post_date="2026-04-24",
                mbti_type="INTJ",
                archetype_name="建築家",
                group_name="分析家",
                title="INTJタイトル",
                series_name="シリーズ",
                format_name="フォーマット",
                theme="恋愛",
                hook="フック",
                narration="ナレーション",
                caption="キャプション",
                hashtags=["#MBTI"],
                global_post_index=0,
                daily_slot=1,
                series_post_number=1,
                scenes=[Scene(title="A", body="B")],
            )
            second_package = ContentPackage(
                post_date="2026-04-24",
                mbti_type="ENTP",
                archetype_name="討論者",
                group_name="分析家",
                title="ENTPタイトル",
                series_name="シリーズ",
                format_name="フォーマット",
                theme="恋愛",
                hook="フック",
                narration="ナレーション",
                caption="キャプション",
                hashtags=["#MBTI"],
                global_post_index=1,
                daily_slot=1,
                series_post_number=2,
                scenes=[Scene(title="A", body="B")],
            )

            def _fake_render(content_package, _config, output_dir):
                slides_dir = output_dir / "slides"
                slides_dir.mkdir(parents=True, exist_ok=True)
                slide_path = slides_dir / "slide_01.png"
                slide_path.write_bytes(content_package.mbti_type.encode("utf-8"))
                (output_dir / "package.json").write_text("{}", encoding="utf-8")
                (output_dir / "caption.txt").write_text("caption", encoding="utf-8")
                return PipelineResult(
                    output_dir=output_dir,
                    package_path=output_dir / "package.json",
                    caption_path=output_dir / "caption.txt",
                    title=content_package.title,
                    mbti_type=content_package.mbti_type,
                    daily_slot=content_package.daily_slot,
                    global_post_index=content_package.global_post_index,
                    media_paths=[slide_path],
                )

            with patch("mbti_tiktok_bot.pipeline.build_daily_packages", side_effect=[[first_package], [second_package]]), patch(
                "mbti_tiktok_bot.pipeline.render_content_package",
                side_effect=_fake_render,
            ):
                build_daily_bundles(date(2026, 4, 24), config, count=1, append_summary=True)
                build_daily_bundles(date(2026, 4, 24), config, count=1, append_summary=True)

            results = load_daily_results(date(2026, 4, 24), config)
            self.assertTrue((config.output_dir / "シリーズ" / "series_plan.json").exists())
            self.assertFalse((config.output_dir / "2026-04-24").exists())
            self.assertEqual([result.mbti_type for result in results], ["INTJ", "ENTP"])

    def test_run_daily_advances_series_state_for_standard_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = replace(
                load_config(Path.cwd()),
                project_root=root,
                output_dir=root / "out",
                state_dir=root / "state",
                phone_export_auto=False,
                phone_export_dir=root / "delivery" / "phone",
            )
            output_dir = config.output_dir / "が好きな人に見せる態度" / "post_01_INTJ"
            result = PipelineResult(
                output_dir=output_dir,
                package_path=output_dir / "package.json",
                caption_path=output_dir / "caption.txt",
                title="INTJが好きな人に見せる態度",
                mbti_type="INTJ",
                daily_slot=1,
                global_post_index=0,
                media_paths=[],
            )
            args = Namespace(
                date="2026-04-24",
                mbti=None,
                format=None,
                dry_run=False,
                export_phone=False,
            )

            with patch("mbti_tiktok_bot.cli.load_config", return_value=config), patch(
                "mbti_tiktok_bot.cli._build_results",
                return_value=[result],
            ):
                exit_code = _run_daily(args)

            self.assertEqual(exit_code, 0)
            self.assertEqual(load_series_state(config)["next_post_index"], 1)

    def test_run_slot_advances_series_state_and_exports_day_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = replace(
                load_config(Path.cwd()),
                project_root=root,
                output_dir=root / "out",
                state_dir=root / "state",
                phone_export_auto=False,
                phone_export_dir=root / "delivery" / "phone",
            )
            output_dir = config.output_dir / "が好きな人に見せる態度" / "post_01_INTJ"
            result = PipelineResult(
                output_dir=output_dir,
                package_path=output_dir / "package.json",
                caption_path=output_dir / "caption.txt",
                title="INTJが好きな人に見せる態度",
                mbti_type="INTJ",
                daily_slot=1,
                global_post_index=0,
                media_paths=[],
            )
            args = Namespace(
                date="2026-04-24",
                dry_run=False,
                export_phone=True,
            )

            with patch("mbti_tiktok_bot.cli.load_config", return_value=config), patch(
                "mbti_tiktok_bot.cli._build_slot_results",
                return_value=[result],
            ), patch("mbti_tiktok_bot.cli.export_daily_results_to_phone") as export_mock:
                exit_code = _run_slot(args)

            self.assertEqual(exit_code, 0)
            self.assertEqual(load_series_state(config)["next_post_index"], 1)
            export_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()