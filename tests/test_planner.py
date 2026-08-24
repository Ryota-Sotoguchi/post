from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from mbti_tiktok_bot.config import load_config
from mbti_tiktok_bot.planner import _build_title, _generate_topics_with_llm, _naturalize_topic_name, _procedural_topic_records, build_daily_packages, build_template_package, load_series_state, maybe_polish_with_llm, persist_package, resolve_target_date, topic_for_post_index

LEGACY_SCENE_TITLE = "\u8ab0\u304b\u306b\u8a00\u3044\u305f\u304f\u306a\u308b\u7d50\u8ad6"


class PlannerTests(unittest.TestCase):
    def test_naturalize_topic_name_smooths_awkward_japanese(self) -> None:
        self.assertEqual(_naturalize_topic_name("が本命だけに見せる優先順位の上げ方", "like_attitude"), "が本命にだけ見せる優先順位の上げ方")
        self.assertEqual(_naturalize_topic_name("の攻略で効く接し方", "攻略"), "に効く接し方")

    def test_build_title_uses_naturalized_topic_name(self) -> None:
        title = _build_title("INTJ", {"name": "の攻略で効く接し方", "blueprint": "攻略", "key": "攻略"})
        self.assertEqual(title, "INTJに効く接し方")

    def test_resolve_target_date_defaults_or_parses(self) -> None:
        parsed = resolve_target_date("2026-04-22")
        self.assertEqual(parsed.isoformat(), "2026-04-22")

    def test_build_template_package_returns_five_scenes(self) -> None:
        config = load_config(Path.cwd())
        package = build_template_package(
            resolve_target_date("2026-04-22"),
            config,
            explicit_mbti="ENFP",
            explicit_format="が好きな人に見せる態度",
        )
        self.assertEqual(package.mbti_type, "ENFP")
        self.assertEqual(len(package.scenes), 5)
        self.assertIn("#ENFP", package.hashtags)
        self.assertIn("#好きな人", package.hashtags)
        self.assertEqual(package.title, "ENFPが好きな人に見せる態度")
        self.assertIn("今回のネタでは", package.caption)
        self.assertNotIn(LEGACY_SCENE_TITLE, [scene.title for scene in package.scenes])

    def test_trust_sign_scene_copy_is_distinct_by_mbti(self) -> None:
        config = load_config(Path.cwd())
        enfj_package = build_template_package(
            resolve_target_date("2026-04-22"),
            config,
            explicit_mbti="ENFJ",
            explicit_format="が本気で心を許したサイン",
        )
        enfp_package = build_template_package(
            resolve_target_date("2026-04-22"),
            config,
            explicit_mbti="ENFP",
            explicit_format="が本気で心を許したサイン",
        )

        enfj_titles = {scene.title for scene in enfj_package.scenes}
        enfp_titles = {scene.title for scene in enfp_package.scenes}

        self.assertTrue(enfj_titles.isdisjoint(enfp_titles))
        self.assertNotIn("心を許すと変わる所", enfj_titles)
        self.assertNotIn("心を許すと変わる所", enfp_titles)
        self.assertIn("ENFJが頼らせ始める", enfj_titles)
        self.assertIn("ENFPが静かに残る時", enfp_titles)

    def test_persist_package_writes_files(self) -> None:
        config = load_config(Path.cwd())
        package = build_template_package(resolve_target_date("2026-04-22"), config, explicit_mbti="INTJ")
        with tempfile.TemporaryDirectory() as temp_dir:
            package_path = persist_package(package, Path(temp_dir))
            self.assertTrue(package_path.exists())
            self.assertTrue((Path(temp_dir) / "caption.txt").exists())
            self.assertTrue((Path(temp_dir) / "caption_template.txt").exists())
            self.assertTrue((Path(temp_dir) / "script.txt").exists())
            self.assertNotIn(LEGACY_SCENE_TITLE, package_path.read_text(encoding="utf-8"))
            self.assertNotIn(LEGACY_SCENE_TITLE, (Path(temp_dir) / "script.txt").read_text(encoding="utf-8"))
            self.assertIn("#MBTI_TYPE", (Path(temp_dir) / "caption_template.txt").read_text(encoding="utf-8"))
            self.assertNotIn("#INTJ", (Path(temp_dir) / "caption_template.txt").read_text(encoding="utf-8"))

    def test_build_daily_packages_returns_three_sequential_types_for_same_topic(self) -> None:
        config = load_config(Path.cwd())
        packages = build_daily_packages(resolve_target_date("2026-04-22"), config, count=3, start_post_index=0)
        self.assertEqual([package.mbti_type for package in packages], ["INTJ", "INTP", "ENTJ"])
        self.assertEqual(len({package.series_name for package in packages}), 1)
        self.assertEqual(packages[0].title, "INTJが好きな人に見せる態度")

    def test_build_daily_packages_rolls_to_next_topic_after_sixteenth_post(self) -> None:
        config = load_config(Path.cwd())
        packages = build_daily_packages(resolve_target_date("2026-04-22"), config, count=3, start_post_index=15)
        self.assertEqual(packages[0].mbti_type, "ESFP")
        self.assertEqual(packages[0].series_name, "が好きな人に見せる態度")
        self.assertEqual(packages[1].mbti_type, "INTJ")
        self.assertEqual(packages[1].series_name, "が本気で心を許したサイン")

    def test_topic_history_expands_without_duplicates_after_seed_topics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = replace(
                load_config(Path.cwd()),
                project_root=Path(temp_dir),
                output_dir=Path(temp_dir) / "out",
                state_dir=Path(temp_dir) / "state",
                openai_api_key=None,
            )

            topic_names = [topic_for_post_index(config, cycle_index * 16)["name"] for cycle_index in range(12)]

        self.assertEqual(len(topic_names), len(set(topic_names)))
        self.assertEqual(topic_names[0], "が好きな人に見せる態度")
        self.assertEqual(topic_names[1], "が本気で心を許したサイン")

    def test_topic_history_interleaves_romance_with_other_themes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = replace(
                load_config(Path.cwd()),
                project_root=Path(temp_dir),
                output_dir=Path(temp_dir) / "out",
                state_dir=Path(temp_dir) / "state",
                openai_api_key=None,
            )

            themes = [topic_for_post_index(config, cycle_index * 16)["theme"] for cycle_index in range(8)]

        self.assertLessEqual(sum(theme == "恋愛" for theme in themes), 3)
        self.assertTrue(all(not (left == right == "恋愛") for left, right in zip(themes, themes[1:])))

    def test_topic_history_broadens_into_work_and_self_understanding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = replace(
                load_config(Path.cwd()),
                project_root=Path(temp_dir),
                output_dir=Path(temp_dir) / "out",
                state_dir=Path(temp_dir) / "state",
                openai_api_key=None,
            )

            topics = [topic_for_post_index(config, cycle_index * 16) for cycle_index in range(12)]

        themes = [topic["theme"] for topic in topics]
        self.assertIn("仕事", themes)
        self.assertIn("自己理解", themes)
        self.assertIn("コミュニケーション", themes)
        self.assertLessEqual(sum(theme == "恋愛" for theme in themes), 4)

    def test_load_series_state_rebalances_future_topics_without_touching_started_cycle(self) -> None:
        old_history = [
            {"key": "like_attitude", "name": "が好きな人に見せる態度", "theme": "恋愛", "blueprint": "like_attitude", "source": "seed"},
            {"key": "crush_actions", "name": "が脈ありの時にする行動", "theme": "恋愛", "blueprint": "crush_actions", "source": "seed"},
            {"key": "line_shift", "name": "のLINEが急に変わる瞬間", "theme": "恋愛", "blueprint": "line_shift", "source": "seed"},
            {"key": "trust_sign", "name": "が本気で心を許したサイン", "theme": "人間関係", "blueprint": "trust_sign", "source": "seed"},
            {"key": "stress_signal", "name": "がしんどい時に出るサイン", "theme": "心理", "blueprint": "stress_signal", "source": "seed"},
            {"key": "攻略", "name": "の攻略で効く接し方", "theme": "攻略", "blueprint": "攻略", "source": "seed"},
            {"key": "generated_like", "name": "が本命だけに見せる優先順位の上げ方", "theme": "恋愛", "blueprint": "like_attitude", "source": "procedural"},
            {"key": "generated_crush", "name": "が脈ありだと増える連絡の増え方", "theme": "恋愛", "blueprint": "crush_actions", "source": "procedural"},
            {"key": "generated_line", "name": "のLINEで本音が出る返信の温度", "theme": "恋愛", "blueprint": "line_shift", "source": "procedural"},
            {"key": "generated_trust", "name": "が心を許すと変わる弱さの見せ方", "theme": "人間関係", "blueprint": "trust_sign", "source": "procedural"},
            {"key": "generated_stress", "name": "が限界前に見せる口数の変化", "theme": "心理", "blueprint": "stress_signal", "source": "procedural"},
            {"key": "generated_guide", "name": "に刺さる褒め方", "theme": "攻略", "blueprint": "攻略", "source": "procedural"},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            config = replace(
                load_config(Path.cwd()),
                project_root=Path(temp_dir),
                output_dir=Path(temp_dir) / "out",
                state_dir=Path(temp_dir) / "state",
                openai_api_key=None,
            )
            config.state_dir.mkdir(parents=True, exist_ok=True)
            (config.state_dir / "series_state.json").write_text(
                json.dumps({"next_post_index": 38, "topic_history": old_history}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            loaded_state = load_series_state(config)

        loaded_names = [topic["name"] for topic in loaded_state["topic_history"]]
        future_themes = [topic["theme"] for topic in loaded_state["topic_history"][3:]]
        self.assertEqual(loaded_names[:3], [topic["name"] for topic in old_history[:3]])
        self.assertTrue(all(not (left == right == "恋愛") for left, right in zip(future_themes, future_themes[1:])))

    def test_maybe_polish_with_llm_warns_on_stdout_and_returns_template_package(self) -> None:
        config = replace(load_config(Path.cwd()), openai_api_key="test-key")
        package = build_template_package(resolve_target_date("2026-04-22"), config, explicit_mbti="ENFP")
        stdout = StringIO()
        stderr = StringIO()

        with patch("mbti_tiktok_bot.planner.requests.post", side_effect=requests.RequestException("400 Client Error")):
            with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
                polished = maybe_polish_with_llm(package, config)

        self.assertEqual(polished, package)
        self.assertIn("LLM polish skipped, continuing with template copy", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_maybe_polish_with_llm_skips_custom_temperature_for_gpt5_models(self) -> None:
        config = replace(load_config(Path.cwd()), openai_api_key="test-key", openai_model="gpt-5-nano")
        package = build_template_package(resolve_target_date("2026-04-22"), config, explicit_mbti="ENFP")
        request_payloads: list[dict[str, object]] = []

        def fake_post(*args, **kwargs):
            request_payloads.append(dict(kwargs["json"]))
            response = Mock()
            response.status_code = 200
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(package.to_dict(), ensure_ascii=False),
                        }
                    }
                ]
            }
            response.raise_for_status.return_value = None
            return response

        with patch("mbti_tiktok_bot.planner.requests.post", side_effect=fake_post):
            polished = maybe_polish_with_llm(package, config)

        self.assertEqual(polished, package)
        self.assertEqual(len(request_payloads), 1)
        self.assertNotIn("temperature", request_payloads[0])

    def test_maybe_polish_with_llm_includes_monetization_quality_guidance(self) -> None:
        config = replace(load_config(Path.cwd()), openai_api_key="test-key")
        package = build_template_package(resolve_target_date("2026-04-22"), config, explicit_mbti="ENFP")
        request_payloads: list[dict[str, object]] = []

        def fake_post(*args, **kwargs):
            request_payloads.append(dict(kwargs["json"]))
            response = Mock()
            response.status_code = 200
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(package.to_dict(), ensure_ascii=False),
                        }
                    }
                ]
            }
            response.raise_for_status.return_value = None
            return response

        with patch("mbti_tiktok_bot.planner.requests.post", side_effect=fake_post):
            polished = maybe_polish_with_llm(package, config)

        self.assertEqual(polished, package)
        self.assertEqual(len(request_payloads), 1)
        messages = request_payloads[0]["messages"]
        self.assertIn("フォロワー1万人以上", messages[0]["content"])
        self.assertIn("直近30日間の再生数10万回以上", messages[0]["content"])
        self.assertIn("一目で何が分かるか伝わる具体性", messages[0]["content"])
        self.assertIn("心理的な奥行き", messages[0]["content"])
        self.assertIn("保存・シェア・完読", messages[1]["content"])

    def test_generate_topics_with_llm_includes_quality_guidance(self) -> None:
        config = replace(load_config(Path.cwd()), openai_api_key="test-key")
        request_payloads: list[dict[str, object]] = []

        def fake_post(*args, **kwargs):
            request_payloads.append(dict(kwargs["json"]))
            response = Mock()
            response.status_code = 200
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "topics": [
                                        {
                                            "name": "が好きな相手ほど差が出る優先順位の上げ方",
                                            "theme": "恋愛",
                                            "blueprint": "like_attitude",
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            ),
                        }
                    }
                ]
            }
            response.raise_for_status.return_value = None
            return response

        history = [{"key": "like_attitude", "name": "が好きな人に見せる態度", "theme": "恋愛", "blueprint": "like_attitude", "source": "seed"}]

        with patch("mbti_tiktok_bot.planner.requests.post", side_effect=fake_post):
            topics = _generate_topics_with_llm(config, history, 1)

        self.assertEqual(len(topics), 1)
        self.assertEqual(topics[0]["name"], "が好きな相手ほど差が出る優先順位の上げ方")
        messages = request_payloads[0]["messages"]
        self.assertIn("フォロワー1万人以上", messages[0]["content"])
        self.assertIn("観察できる差分", messages[0]["content"])
        self.assertIn("防衛反応", messages[0]["content"])
        self.assertIn("保存候補になる具体性", messages[1]["content"])

    def test_procedural_topic_records_prioritize_specific_high_signal_topics(self) -> None:
        topics = _procedural_topic_records(10, set())
        self.assertEqual(
            {topic["name"] for topic in topics},
            {
                "が本命前で見せる距離を詰めたい時の葛藤",
                "が心を許す前に見せる弱さを預ける境界線",
                "が好意の手前で見せる近づきたいのに避ける瞬間",
                "が距離を許す時に出る素を見せる境界線",
                "のLINEに出る踏み込みたい時の文面",
                "が限界前に見せる防衛反応",
                "に深く刺さる本音を引き出す聞き方",
                "の仕事で信頼が深まる抱え込みのほどき方",
                "の回復に必要な心理的余白",
                "と本音で話すための否定されない聞かれ方",
            },
        )

    def test_procedural_topic_records_skip_titles_over_80_percent_similar(self) -> None:
        topics = _procedural_topic_records(
            10,
            set(),
            used_topic_names=["が限界前に見せる口数の変化"],
        )

        self.assertNotIn("が限界前に見せる口数の減り方", {topic["name"] for topic in topics})

    def test_generated_stress_topic_uses_focus_specific_scene_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = replace(
                load_config(Path.cwd()),
                project_root=Path(temp_dir),
                output_dir=Path(temp_dir) / "out",
                state_dir=Path(temp_dir) / "state",
                openai_api_key=None,
            )
            config.state_dir.mkdir(parents=True, exist_ok=True)
            (config.state_dir / "series_state.json").write_text(
                json.dumps(
                    {
                        "next_post_index": 0,
                        "topic_history": [
                            {
                                "key": "generated_stress",
                                "name": "が限界前に見せる口数の変化",
                                "theme": "心理",
                                "blueprint": "stress_signal",
                                "source": "procedural",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            package = build_template_package(
                resolve_target_date("2026-04-22"),
                config,
                explicit_mbti="ESFJ",
                explicit_format="が限界前に見せる口数の変化",
            )

        scene_titles = [scene.title for scene in package.scenes]
        self.assertIn("返事が短くなる瞬間", scene_titles)
        self.assertNotIn("しんどい時のサイン", scene_titles)
        self.assertIn("口数の減り方", package.scenes[-1].body)

    def test_build_template_package_supports_non_romance_formats(self) -> None:
        config = load_config(Path.cwd())
        package = build_template_package(
            resolve_target_date("2026-04-22"),
            config,
            explicit_mbti="INTJ",
            explicit_format="の仕事で信頼される関わり方",
        )
        self.assertEqual(package.theme, "仕事")
        self.assertIn("進め方の相性", package.hook)
        self.assertIn("職場で信頼", package.caption)
        self.assertIn("#仕事", package.hashtags)

    def test_build_template_package_uses_higher_signal_hook_and_caption_copy(self) -> None:
        config = load_config(Path.cwd())
        package = build_template_package(
            resolve_target_date("2026-04-22"),
            config,
            explicit_mbti="INTJ",
            explicit_format="が脈ありの時にする行動",
        )
        self.assertIn("行動差", package.hook)
        self.assertIn("社交辞令と脈あり", package.caption)
        self.assertIn("答え合わせ", package.caption)

    def test_maybe_polish_with_llm_rebuilds_caption_and_hashtags_after_polish(self) -> None:
        config = replace(load_config(Path.cwd()), openai_api_key="test-key")
        package = build_template_package(
            resolve_target_date("2026-04-22"),
            config,
            explicit_mbti="INTJ",
            explicit_format="が脈ありの時にする行動",
        )
        llm_payload = package.to_dict()
        llm_payload["caption"] = "短い旧式キャプション"
        llm_payload["hashtags"] = ["#MBTI", "#恋愛あるある", "#脈あり", "#INTJ"]

        def fake_post(*args, **kwargs):
            response = Mock()
            response.status_code = 200
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(llm_payload, ensure_ascii=False),
                        }
                    }
                ]
            }
            response.raise_for_status.return_value = None
            return response

        with patch("mbti_tiktok_bot.planner.requests.post", side_effect=fake_post):
            polished = maybe_polish_with_llm(package, config)

        self.assertIn("今回のネタでは", polished.caption)
        self.assertIn("#好きバレ", polished.hashtags)
        self.assertNotEqual(polished.caption, "短い旧式キャプション")

    def test_maybe_polish_keeps_trust_sign_scene_copy_locked(self) -> None:
        config = replace(load_config(Path.cwd()), openai_api_key="test-key")
        package = build_template_package(
            resolve_target_date("2026-04-22"),
            config,
            explicit_mbti="ENFJ",
            explicit_format="が本気で心を許したサイン",
        )
        llm_payload = package.to_dict()
        llm_payload["scenes"] = [
            {"title": "心を許すと変わる所", "body": "他タイプにも使える汎用コピー", "duration_seconds": 4.0}
        ]

        def fake_post(*args, **kwargs):
            response = Mock()
            response.status_code = 200
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(llm_payload, ensure_ascii=False),
                        }
                    }
                ]
            }
            response.raise_for_status.return_value = None
            return response

        with patch("mbti_tiktok_bot.planner.requests.post", side_effect=fake_post):
            polished = maybe_polish_with_llm(package, config)

        self.assertEqual(len(polished.scenes), 5)
        self.assertIn("ENFJが頼らせ始める", [scene.title for scene in polished.scenes])
        self.assertNotIn("他タイプにも使える汎用コピー", [scene.body for scene in polished.scenes])

    def test_maybe_polish_with_llm_retries_without_temperature_when_model_rejects_it(self) -> None:
        config = replace(load_config(Path.cwd()), openai_api_key="test-key", openai_model="gpt-4.1-mini")
        package = build_template_package(resolve_target_date("2026-04-22"), config, explicit_mbti="ENFP")
        request_payloads: list[dict[str, object]] = []

        def fake_post(*args, **kwargs):
            request_payloads.append(dict(kwargs["json"]))
            response = Mock()
            if len(request_payloads) == 1:
                response.status_code = 400
                response.json.return_value = {
                    "error": {
                        "message": "Unsupported value: 'temperature' does not support 0.9 with this model.",
                        "param": "temperature",
                    }
                }
                response.raise_for_status.side_effect = requests.HTTPError("400 Client Error", response=response)
                return response

            response.status_code = 200
            response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(package.to_dict(), ensure_ascii=False),
                        }
                    }
                ]
            }
            response.raise_for_status.return_value = None
            return response

        with patch("mbti_tiktok_bot.planner.requests.post", side_effect=fake_post):
            polished = maybe_polish_with_llm(package, config)

        self.assertEqual(polished, package)
        self.assertEqual(len(request_payloads), 2)
        self.assertIn("temperature", request_payloads[0])
        self.assertNotIn("temperature", request_payloads[1])


if __name__ == "__main__":
    unittest.main()
