from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from mbti_tiktok_bot.catalog import MBTI_POST_ORDER
from mbti_tiktok_bot.config import load_config
from mbti_tiktok_bot.design import text as T
from mbti_tiktok_bot.design.engine import look_name, render_post
from mbti_tiktok_bot.design.fonts import face
from mbti_tiktok_bot.design.looks import LOOK_ORDER
from mbti_tiktok_bot.formats import planner, produce, writer
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
    def test_ten_posts_follow_the_pattern_and_never_repeat_a_format_back_to_back(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _config(Path(temp_dir))
            state = planner.FormatState()
            formats = []
            for _ in range(20):
                spec = planner.next_spec(config, state)
                formats.append(spec.format)
                planner.advance(state, spec)
        self.assertEqual(tuple(formats[:10]), planner.PATTERN)
        self.assertEqual(formats[10:], formats[:10])
        self.assertTrue(all(a != b for a, b in zip(formats, formats[1:])))

    def test_manual_and_compat_on_the_same_day_are_about_different_types(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _config(Path(temp_dir))
            state = planner.FormatState()
            focus: dict[str, set[str]] = {"manual": set(), "compat": set()}
            for _ in range(10):
                spec = planner.next_spec(config, state)
                if spec.format in focus:
                    focus[spec.format].add(spec.focus)
                planner.advance(state, spec)
        self.assertFalse(focus["manual"] & focus["compat"])

    def test_manual_walks_all_sixteen_types_before_changing_angle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _config(Path(temp_dir))
            state = planner.FormatState()
            seen = []
            while len(seen) < 17:
                spec = planner.next_spec(config, state)
                if spec.format == "manual":
                    seen.append((spec.focus, spec.angle))
                planner.advance(state, spec)
        self.assertEqual([mbti for mbti, _ in seen[:16]], list(MBTI_POST_ORDER))
        self.assertEqual(len({angle for _, angle in seen[:16]}), 1)
        self.assertNotEqual(seen[16][1], seen[0][1])

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

    def test_consecutive_posts_never_share_a_look(self) -> None:
        looks = [look_name(_small_post(seq)) for seq in range(1, 12)]
        self.assertTrue(all(a != b for a, b in zip(looks, looks[1:])))


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
            self.assertEqual(keys, ["00006-gallery", "00007-compat"])
            self.assertEqual(planner.load_state(config).next_seq, 8)


if __name__ == "__main__":
    unittest.main()
