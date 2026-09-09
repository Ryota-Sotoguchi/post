from __future__ import annotations

import unittest

from mbti_tiktok_bot.typeset import (
    LINE_END_FORBIDDEN,
    LINE_START_FORBIDDEN,
    break_points,
    wrap_paragraph,
)


def fixed_width(text: str) -> int:
    """One unit per character, so widths in these tests are character counts."""
    return len(text)


def segments(text: str) -> list[str]:
    preferred, _ = break_points(text)
    cuts = sorted(preferred)
    return [text[a:b] for a, b in zip([0] + cuts, cuts + [len(text)])]


class BreakPointTests(unittest.TestCase):
    def test_breaks_after_a_particle_that_follows_a_content_word(self) -> None:
        self.assertIn("あなたへの返し方が", segments("あなたへの返し方がいつもより丁寧になる。"))

    def test_keeps_compound_particles_together(self) -> None:
        # への must not split into へ + の.
        self.assertNotIn("あなたへ", segments("あなたへの返し方が変わる。"))

    def test_does_not_read_yori_as_two_particles(self) -> None:
        self.assertNotIn("いつもよ", segments("返信がいつもより丁寧になる。"))

    def test_does_not_split_okurigana_as_a_particle(self) -> None:
        # The か of 急かす is not a particle.
        self.assertNotIn("急か", segments("急かさない。まず理解しようとする。"))

    def test_breaks_before_an_opening_bracket(self) -> None:
        self.assertIn("詰めずに確認する", segments("詰めずに確認する（確認＝安心になる）。"))

    def test_particle_after_hiragana_is_only_a_fallback(self) -> None:
        preferred, fallback = break_points("静かに閉じることが多い。")
        # ことが is ambiguous, so it is available but not preferred.
        self.assertNotIn(9, preferred)
        self.assertIn(9, fallback)


class WrapTests(unittest.TestCase):
    def test_short_text_stays_on_one_line(self) -> None:
        self.assertEqual(wrap_paragraph(fixed_width, "返信の温度が変わる", 20), ["返信の温度が変わる"])

    def test_every_line_fits_the_width(self) -> None:
        lines = wrap_paragraph(fixed_width, "返信は短いのに内容は本気。早さよりも、あなたへの返し方がいつもより丁寧になる。", 12)
        for line in lines:
            self.assertLessEqual(len(line), 12)

    def test_uses_a_fallback_break_instead_of_cutting_mid_word(self) -> None:
        lines = wrap_paragraph(fixed_width, "静かに閉じることが多い。", 10)
        # Without the fallback tier this became 静かに閉じることが多 / い。
        self.assertNotIn("い。", lines)

    def test_never_opens_a_line_with_forbidden_punctuation(self) -> None:
        lines = wrap_paragraph(fixed_width, "感情を決めつける、正論で押す、即レスを求めると閉じやすい。", 9)
        for line in lines[1:]:
            self.assertNotIn(line[0], LINE_START_FORBIDDEN)

    def test_never_closes_a_line_with_an_opening_bracket(self) -> None:
        lines = wrap_paragraph(fixed_width, "詰めずに確認する（確認＝安心になる）、急かさない。", 9)
        for line in lines[:-1]:
            self.assertNotIn(line[-1], LINE_END_FORBIDDEN)

    def test_evens_out_line_lengths(self) -> None:
        # Greedy packing gave 先を / 読む力や余裕が落ち、
        lines = wrap_paragraph(fixed_width, "先を読む力や余裕が落ち、いつもと違う反応が出る。", 14)
        shortest = min(len(line) for line in lines)
        longest = max(len(line) for line in lines)
        self.assertLessEqual(longest - shortest, 7)

    def test_does_not_split_a_katakana_run(self) -> None:
        lines = wrap_paragraph(fixed_width, "急かされると会話を内側でシャットダウン。", 10)
        self.assertTrue(any("シャットダウン" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
