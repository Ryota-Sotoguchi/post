from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from mbti_tiktok_bot.catalog import GROUP_PALETTE_VARIANTS, MBTI_POST_ORDER
from mbti_tiktok_bot.config import load_config
from mbti_tiktok_bot.design import backgrounds
from mbti_tiktok_bot.design import text as T
from mbti_tiktok_bot.design.core import Context
from mbti_tiktok_bot.design.engine import look_name, palette_for, render_post
from mbti_tiktok_bot.design.fonts import face
from mbti_tiktok_bot.design.looks import LOOK_ORDER
from mbti_tiktok_bot.formats import legacy, planner, produce, writer
from mbti_tiktok_bot.formats import topics as K
from mbti_tiktok_bot.formats.model import Card, Item, Post

TARGET = date(2026, 9, 20)


def _config(root: Path):
    return replace(
        load_config(Path.cwd()),
        project_root=root,
        output_dir=root / "out",
        state_dir=root / "state",
        phone_export_dir=root / "delivery" / "phone",
        openai_api_key=None,
        keep_render_layers=False,
        posts_per_day=10,
    )


def _small_post(seq: int = 3) -> Post:
    """Two slides, enough to exercise a render without the cost of sixteen."""
    return Post(
        seq=seq,
        format="compat",
        post_date=TARGET.isoformat(),
        title="INFJと相性がいいタイプ【恋愛】",
        hook="本当は誰といると安心する？",
        focus="INFJ",
        angle="恋愛",
        hashtags=("#MBTI", "#INFJ"),
        cards=[
            Card("pair", title="静かに寄り添う共鳴者", body="価値観を夜まで語り合う。", label="相性◎ 第1位",
                 number=1, total=3, items=(Item("INFJ"), Item("INFP", "静かに寄り添う共鳴者", "", 1)),
                 types=("INFJ", "INFP")),
            Card("closer", title="相手のタイプはどうだった？", body="気になる人に送ってみて。", types=("INFJ", "INFP")),
        ],
    )


class PlannerTests(unittest.TestCase):
    def test_a_series_runs_all_sixteen_types_before_anything_else(self) -> None:
        # The point of the series: a type-by-type subject goes out 01 to 16
        # with no ranking or gallery cutting into the middle of it.
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _config(Path(temp_dir))
            state = planner.FormatState()
            specs = []
            for _ in range(34):
                spec = planner.next_spec(config, state)
                specs.append(spec)
                planner.advance(state, spec)

        first = specs[:16]
        self.assertEqual({spec.format for spec in first}, {"manual"})
        self.assertEqual([spec.focus for spec in first], list(MBTI_POST_ORDER))
        self.assertEqual([spec.position for spec in first], list(range(1, 17)))
        self.assertEqual({spec.angle for spec in first}, {"基本"})
        # Then one post of something else, then the next subject, in full.
        self.assertEqual(specs[16].format, "gallery")
        self.assertEqual({spec.format for spec in specs[17:33]}, {"compat"})
        self.assertEqual([spec.focus for spec in specs[17:33]], list(MBTI_POST_ORDER))
        self.assertEqual(specs[33].format, "ranking")

    def test_every_post_of_a_series_carries_the_same_series(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _config(Path(temp_dir))
            state = planner.FormatState()
            specs = [planner.next_spec(config, state) for _ in range(1)]
            for _ in range(15):
                planner.advance(state, specs[-1])
                specs.append(planner.next_spec(config, state))
        self.assertEqual({spec.series for spec in specs}, {"manual:基本"})
        self.assertEqual({spec.series_index for spec in specs}, {1})

    def test_the_angle_moves_on_each_time_a_format_comes_round(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _config(Path(temp_dir))
            state = planner.FormatState()
            angles = []
            while len(angles) < 4:
                spec = planner.next_spec(config, state)
                if spec.format == "manual" and spec.position == 1:
                    angles.append(spec.angle)
                planner.advance(state, spec)
        self.assertEqual(angles, list(K.MANUAL_ANGLES[:4]))

    def test_state_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _config(Path(temp_dir))
            state = planner.FormatState()
            state.next_seq = 7
            state.cursors["manual"] = 3
            state.extra_topics["gallery"].append("新しいお題")
            planner.save_state(config, state)
            loaded = planner.load_state(config)
        self.assertEqual(loaded.to_dict(), state.to_dict())


class WriterFallbackTests(unittest.TestCase):
    """Without an API key every format is still written, from type data."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.config = _config(Path(self.temp.name))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_gallery_has_every_type_once_between_a_cover_and_a_closer(self) -> None:
        post = writer.gallery(self.config, 1, "既読スルーされた時", TARGET)
        self.assertEqual(post.source, "template")
        kinds = [card.kind for card in post.cards]
        self.assertEqual(kinds, ["cover", *["entry"] * 16, "closer"])
        self.assertEqual(sorted(card.items[0].type for card in post.cards[1:-1]), sorted(MBTI_POST_ORDER))

    def test_ranking_counts_down_from_sixteen_to_one(self) -> None:
        post = writer.ranking(self.config, 3, "怒らせると一番怖いタイプ", TARGET)
        ranks = [item.rank for card in post.cards if card.kind in ("grid", "entry") for item in card.items]
        self.assertEqual(ranks, list(range(16, 0, -1)))
        types = [item.type for card in post.cards if card.kind in ("grid", "entry") for item in card.items]
        self.assertEqual(sorted(types), sorted(MBTI_POST_ORDER))

    def test_manual_has_one_section_per_heading(self) -> None:
        post = writer.manual(self.config, 2, "ESFP", "恋愛", TARGET)
        sections = [card for card in post.cards if card.kind == "section"]
        self.assertEqual(len(sections), 8)
        self.assertTrue(all(card.body for card in sections))
        self.assertEqual(post.focus, "ESFP")

    def test_compat_pairs_are_distinct_and_never_the_type_itself(self) -> None:
        post = writer.compat(self.config, 4, "INFJ", "恋愛", TARGET)
        others = [card.items[1].type for card in post.cards if card.kind == "pair"]
        self.assertEqual(len(others), 6)
        self.assertEqual(len(set(others)), 6)
        self.assertNotIn("INFJ", others)

    def test_a_reply_missing_a_type_is_rejected(self) -> None:
        entries = [{"type": mbti, "title": "t", "body": "b"} for mbti in MBTI_POST_ORDER[:15]]
        self.assertIsNone(writer._entries({"entries": entries}, "entries"))
        entries.append({"type": MBTI_POST_ORDER[0], "title": "t", "body": "b"})
        self.assertIsNone(writer._entries({"entries": entries}, "entries"))

    def test_a_pairing_with_the_type_itself_is_rejected(self) -> None:
        good = [{"type": t, "title": "a", "body": "b"} for t in ("INFJ", "ENFP", "INTJ")]
        caution = [{"type": t, "title": "a", "body": "b"} for t in ("ESTP", "ESTJ", "ENTJ")]
        self.assertIsNone(writer._pairs({"good": good, "caution": caution}, "INFJ"))

    def test_post_round_trips_through_json(self) -> None:
        post = writer.compat(self.config, 4, "INFJ", "恋愛", TARGET)
        again = Post.from_dict(json.loads(writer.dumps(post)))
        self.assertEqual(again.to_dict(), post.to_dict())


LEGACY = {
    "post_date": "2026-07-05",
    "mbti_type": "INTJ",
    "title": "INTJが本気で心を許したサイン",
    "theme": "人間関係",
    "hook": "急に予定を崩したら要チェック。",
    "hashtags": ["#MBTI", "#INTJ"],
    "scenes": [
        {"title": "INTJが計画を外す時", "body": "先を読む / 感情より設計 / 必要な人には一途。説明より本音が先に出る。"},
        {"title": "静かな一途さが出る", "body": "感情表現は 大きくなくても、優先順位が変わる。"},
        {"title": "任せる範囲が広がる", "body": "詰めずに確認する／急かさない／まず理解する。距離が開きにくい。"},
    ],
}


class LegacyConversionTests(unittest.TestCase):
    """The back catalogue, redrawn: same copy, current design."""

    def test_a_themed_post_becomes_a_cover_sections_and_a_closer(self) -> None:
        post = legacy.convert(LEGACY, 7)

        self.assertEqual(post.key, "L0007-manual")
        self.assertTrue(post.filler)
        self.assertEqual(post.source, "legacy")
        self.assertEqual([card.kind for card in post.cards], ["cover", "section", "section", "section", "closer"])
        self.assertEqual(post.cards[0].title, "INTJが本気で心を許したサイン")
        # The hook was written for every post and never drawn; now it is the cover.
        self.assertEqual(post.cards[0].body, "急に予定を崩したら要チェック。")
        self.assertEqual(post.hashtags, ("#MBTI", "#INTJ"))

    def test_the_filler_series_cannot_collide_with_the_daily_numbers(self) -> None:
        self.assertNotEqual(legacy.convert(LEGACY, 7).key, _small_post(7).key)

    def test_a_list_pasted_into_prose_becomes_chips(self) -> None:
        post = legacy.convert(LEGACY, 1)
        first, second, third = post.cards[1:4]

        self.assertEqual(first.chips, ("先を読む", "感情より設計", "必要な人には一途"))
        self.assertEqual(first.body, "説明より本音が先に出る。")
        # A fullwidth slash was used for the same thing.
        self.assertEqual(third.chips, ("詰めずに確認する", "急かさない", "まず理解する"))
        self.assertEqual(third.body, "距離が開きにくい。")
        # A card with no list of its own falls back to the type's traits.
        self.assertEqual(second.chips, ())
        # And a stray space between two Japanese characters is a typo.
        self.assertEqual(second.body, "感情表現は大きくなくても、優先順位が変わる。")

    def test_prose_with_a_nakaguro_is_left_alone(self) -> None:
        # 世話焼き・励ます人 is one phrase, not a list.
        self.assertEqual(legacy.split_chips("普段は世話焼き・励ます人が反応薄め。続く文。"),
                         ((), "普段は世話焼き・励ます人が反応薄め。続く文。"))

    def test_a_list_with_nothing_after_it_stays_prose(self) -> None:
        # 即レスを求めると閉じやすい is the predicate; chipping it would lose it.
        chips, body = legacy.split_chips("感情を決めつける／正論で押す／即レスを求めると閉じやすい。")
        self.assertEqual(chips, ())
        self.assertEqual(body, "感情を決めつける／正論で押す／即レスを求めると閉じやすい。")

    def test_a_list_left_in_prose_gets_the_separator_the_sentence_wanted(self) -> None:
        post = legacy.convert({**LEGACY, "scenes": [
            {"title": "見出し", "body": "感情を決めつける／正論で押す／即レスを求めると閉じやすい。"}]}, 1)
        self.assertEqual(post.cards[1].body, "感情を決めつける、正論で押す、即レスを求めると閉じやすい。")


class RenderTests(unittest.TestCase):
    def test_every_look_renders_full_size_opaque_slides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _config(Path(temp_dir))
            for look in LOOK_ORDER:
                slides_dir = Path(temp_dir) / look / "slides"
                render_post(_small_post(), config, slides_dir, look=look)
                slides = sorted(slides_dir.glob("slide_*.png"))
                self.assertEqual(len(slides), 2, look)
                for slide in slides:
                    with Image.open(slide) as image:
                        self.assertEqual(image.size, (1080, 1920), look)
                        self.assertEqual(image.mode, "RGB", look)

    def test_a_post_renders_the_same_twice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _config(Path(temp_dir))
            first, second = Path(temp_dir) / "a" / "slides", Path(temp_dir) / "b" / "slides"
            render_post(_small_post(), config, first, look="neon")
            render_post(_small_post(), config, second, look="neon")
            for name in ("slide_01.png", "slide_02.png"):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())

    def test_a_series_is_one_look_and_one_palette(self) -> None:
        # Sixteen posts of one subject used to arrive in four looks and four
        # colour schemes, which is what made them look unrelated.
        posts = [replace(_small_post(seq), series="manual:恋愛", series_index=3, focus=mbti)
                 for seq, mbti in enumerate(MBTI_POST_ORDER, start=40)]
        self.assertEqual({look_name(post) for post in posts}, {LOOK_ORDER[2]})
        self.assertEqual(len({palette_for(post).name for post in posts}), 1)

    def test_consecutive_series_do_not_share_a_look(self) -> None:
        looks = [look_name(replace(_small_post(1), series=f"manual:{n}", series_index=n)) for n in range(1, 5)]
        self.assertEqual(len(set(looks)), len(LOOK_ORDER))


    def test_an_empty_library_leaves_every_look_drawing_itself(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _config(Path(temp_dir))  # project_root has no assets/backgrounds
            self.assertEqual(backgrounds.library(config.project_root, "neon"), [])
            slides_dir = Path(temp_dir) / "slides"
            render_post(_small_post(), config, slides_dir, look="neon")
            self.assertEqual(len(list(slides_dir.glob("slide_*.png"))), 2)

    def test_the_same_post_always_gets_the_same_texture(self) -> None:
        config = load_config(Path.cwd())
        files = backgrounds.library(config.project_root, "neon")
        if not files:
            self.skipTest("no texture library in this checkout")
        ctx = Context(config=config, palette=GROUP_PALETTE_VARIANTS["分析家"][0], seed=12345, scale=1)
        first = backgrounds.texture(ctx, "neon", "#000000", "#ffffff")
        second = backgrounds.texture(ctx, "neon", "#000000", "#ffffff")
        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertEqual(first.size, ctx.device)

    def test_a_texture_is_recoloured_into_the_palette(self) -> None:
        config = load_config(Path.cwd())
        if not backgrounds.library(config.project_root, "brutal"):
            self.skipTest("no texture library in this checkout")
        ctx = Context(config=config, palette=GROUP_PALETTE_VARIANTS["分析家"][0], seed=7, scale=1)
        recoloured = backgrounds.texture(ctx, "brutal", "#102030", "#e0f0ff").convert("RGB")
        # Every pixel sits on the line between the two colours: blue is never
        # below the dark end or above the light end, whatever the file held.
        blues = recoloured.getchannel("B").getextrema()
        self.assertGreaterEqual(blues[0], 0x30 - 2)
        self.assertLessEqual(blues[1], 0xFF)
        reds = recoloured.getchannel("R").getextrema()
        self.assertGreaterEqual(reds[0], 0x10 - 2)
        self.assertLessEqual(reds[1], 0xE0 + 2)


class HeadlineBreakTests(unittest.TestCase):
    def test_headlines_break_between_words(self) -> None:
        font = face("jp-black", 112)
        cases = {
            "既読でとりあえず放置派": ["既読で", "とりあえず放置派"],
            "静かに寄り添う共鳴者": ["静かに", "寄り添う共鳴者"],
            "ISTJが本気で心を許したサイン": ["ISTJが本気で", "心を許したサイン"],
            "お茶を飲みながら思い出す話": ["お茶を飲みながら", "思い出す話"],
        }
        for text, expected in cases.items():
            self.assertEqual(T.headline_lines(text, font, -0.02 * 112, 936, 3), expected, text)

    def test_a_long_katakana_word_is_shrunk_rather_than_split(self) -> None:
        block = T.fit("怒らせると一番怖いタイプランキング", "jp-black", 936, 460, 128, 64,
                      leading=1.1, tracking_em=-0.02, max_lines=3, strict=True)
        self.assertIn("タイプランキング", block.lines)


class ProduceTests(unittest.TestCase):
    def test_due_by_spreads_the_day_over_its_slots(self) -> None:
        times = ["08:00", "12:00", "16:00", "20:00"]
        self.assertEqual(produce.due_by(TARGET, times, datetime(2026, 9, 20, 7, 59), 10), 0)
        self.assertEqual(produce.due_by(TARGET, times, datetime(2026, 9, 20, 8, 0), 10), 2)
        self.assertEqual(produce.due_by(TARGET, times, datetime(2026, 9, 20, 12, 30), 10), 5)
        self.assertEqual(produce.due_by(TARGET, times, datetime(2026, 9, 20, 23, 0), 10), 10)
        self.assertEqual(produce.due_by(TARGET, times, datetime(2026, 9, 21, 7, 0), 10), 10)
        self.assertEqual(produce.due_by(TARGET, times, datetime(2026, 9, 19, 23, 0), 10), 0)

    def test_a_post_is_drawn_handed_off_and_counted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _config(Path(temp_dir))
            folder = produce.make_post(config, _small_post())

            self.assertEqual(json.loads((folder / "post.json").read_text(encoding="utf-8"))["key"], "00003-compat")
            handoff = config.phone_export_dir / "_posts" / "00003-compat"
            meta = json.loads((handoff / "post.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["title"], "INFJと相性がいいタイプ【恋愛】")
            self.assertIn("#INFJ", meta["description"])
            self.assertEqual(sorted(path.name for path in handoff.glob("slide_*.png")), ["slide_01.png", "slide_02.png"])
            self.assertEqual(produce.produced_on(config, TARGET), [folder])
            self.assertEqual(produce.produced_on(config, date(2026, 9, 21)), [])

    def test_produce_advances_the_pattern_and_skips_numbers_already_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _config(Path(temp_dir))
            # A post from before the state file was lost.
            (produce.posts_root(config) / "00005-compat").mkdir(parents=True)

            def fake_write(_config, spec, target):
                return replace(_small_post(spec.seq), format=spec.format, post_date=target.isoformat())

            with patch("mbti_tiktok_bot.formats.planner.write", side_effect=fake_write), patch(
                "mbti_tiktok_bot.formats.produce.make_post",
                side_effect=lambda _config, post: produce.posts_root(config) / post.key,
            ) as make_mock:
                produce.produce(config, TARGET, 2)

            keys = [call.args[1].key for call in make_mock.call_args_list]
            self.assertEqual(keys, ["00006-manual", "00007-manual"])
            self.assertEqual(planner.load_state(config).next_seq, 8)


if __name__ == "__main__":
    unittest.main()
