"""Which post comes next, and the state that remembers.

Work comes in two shapes. A **series** is one subject walked across the sixteen
types - the manual for 恋愛, the compatibility post for 友達 - and it runs 01 to
16 with nothing cutting in: same look, same palette, same arrangement, so the
sixteen read as one set. A **one-off** covers all sixteen types inside a single
post, which is what the gallery and the ranking are.

The order is series, one-off, series, one-off. At ten posts a day a series
takes a day and a half, and the one-off between two of them is the break.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

from mbti_tiktok_bot.catalog import MBTI_POST_ORDER
from mbti_tiktok_bot.config import AppConfig
from mbti_tiktok_bot.formats import topics as K
from mbti_tiktok_bot.formats import writer
from mbti_tiktok_bot.formats.model import FORMATS, Post

STATE_FILE = "format_state.json"
TYPES = tuple(MBTI_POST_ORDER)
SIMILAR = 0.8

# A series is one of these, taken in turn; the angle moves on each time the
# format comes round again.
SERIES_FORMATS = ("manual", "compat")
ONE_OFFS = ("gallery", "ranking")
SERIES_LENGTH = len(TYPES)


@dataclass(slots=True)
class FormatState:
    next_seq: int = 1
    series_count: int = 0  # how many series have been started, ever
    # The series being walked: its format, angle, number and how far in it is.
    series: dict | None = None
    # True when a series has just finished and the one-off between series is due.
    between: bool = False
    one_offs: int = 0
    cursors: dict[str, int] = field(default_factory=lambda: {name: 0 for name in FORMATS})
    extra_topics: dict[str, list[str]] = field(default_factory=lambda: {"gallery": [], "ranking": []})

    def to_dict(self) -> dict:
        return {
            "next_seq": self.next_seq,
            "series_count": self.series_count,
            "series": self.series,
            "between": self.between,
            "one_offs": self.one_offs,
            "cursors": self.cursors,
            "extra_topics": self.extra_topics,
        }


def state_path(config: AppConfig) -> Path:
    return config.state_dir / STATE_FILE


def load_state(config: AppConfig) -> FormatState:
    path = state_path(config)
    if not path.exists():
        return FormatState()
    data = json.loads(path.read_text(encoding="utf-8"))
    state = FormatState()
    state.next_seq = int(data.get("next_seq", 1))
    state.series_count = int(data.get("series_count", 0))
    series = data.get("series")
    state.series = dict(series) if isinstance(series, dict) else None
    state.between = bool(data.get("between", False))
    state.one_offs = int(data.get("one_offs", 0))
    state.cursors.update({name: int(value) for name, value in data.get("cursors", {}).items()})
    for name in ("gallery", "ranking"):
        state.extra_topics[name] = [str(topic) for topic in data.get("extra_topics", {}).get(name, [])]
    return state


def save_state(config: AppConfig, state: FormatState) -> Path:
    path = state_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _pool(name: str, state: FormatState) -> list[str]:
    seeds = K.GALLERY_TOPICS if name == "gallery" else K.RANKING_TOPICS
    return [*seeds, *state.extra_topics[name]]


def _similar(candidate: str, existing: list[str]) -> bool:
    return any(SequenceMatcher(None, candidate, other).ratio() >= SIMILAR for other in existing)


def _more_topics(config: AppConfig, name: str, state: FormatState, count: int = 10) -> list[str]:
    """Ask for fresh topics once the pool is used up. Empty when that fails."""
    existing = _pool(name, state)
    if name == "gallery":
        ask = ("MBTI16タイプの反応を並べる「〇〇の16タイプ」投稿のお題を考えてください。"
               "誰もが経験する具体的な瞬間を、「〇〇の時」「〇〇な夜」のような10〜16字の名詞句で。")
    else:
        ask = ("MBTI16タイプを順位づけする「〇〇ランキング」投稿のお題を考えてください。"
               "「一番〇〇なタイプ」のように、1位が気になって議論が起きる、10〜18字の名詞句で。")
    prompt = (
        f"{ask}\n{count}個。すでに使ったものと被らないこと:\n" + "、".join(existing)
        + '\n形式: {"topics": ["..."]}'
    )
    data = writer._ask(config, prompt)
    fresh: list[str] = []
    for topic in (data or {}).get("topics", []) if isinstance((data or {}).get("topics"), list) else []:
        value = " ".join(str(topic).split()).removesuffix("ランキング").removesuffix("の16タイプ")
        if 4 <= len(value) <= 22 and not _similar(value, existing + fresh):
            fresh.append(value)
    return fresh


@dataclass(frozen=True, slots=True)
class Spec:
    seq: int
    format: str
    topic: str = ""
    focus: str = ""
    angle: str = ""
    series: str = ""
    series_index: int = 0
    position: int = 0  # 1..16 inside a series, 0 for a one-off


def series_name(fmt: str, angle: str) -> str:
    return f"{fmt}:{angle}"


def _start_series(state: FormatState) -> dict:
    """The next subject to walk across the sixteen types."""
    fmt = SERIES_FORMATS[state.series_count % len(SERIES_FORMATS)]
    angles = K.MANUAL_ANGLES if fmt == "manual" else K.COMPAT_ANGLES
    lap = state.series_count // len(SERIES_FORMATS)
    return {
        "format": fmt,
        "angle": angles[lap % len(angles)],
        "number": state.series_count + 1,
        "position": 0,
    }


def _one_off(config: AppConfig, state: FormatState) -> Spec:
    name = ONE_OFFS[state.one_offs % len(ONE_OFFS)]
    cursor = state.cursors[name]
    pool = _pool(name, state)
    if cursor >= len(pool):
        state.extra_topics[name].extend(_more_topics(config, name, state))
        pool = _pool(name, state)
    # Nothing new to be had: go round again rather than stop publishing.
    topic = pool[cursor % len(pool)]
    return Spec(state.next_seq, name, topic=topic, series=f"{name}:{topic}",
                series_index=state.series_count * 2 + state.one_offs + 1)


def next_spec(config: AppConfig, state: FormatState) -> Spec:
    if state.series is None and not state.between:
        state.series = _start_series(state)
        state.series_count = int(state.series["number"])
    if state.series is not None:
        current = state.series
        position = int(current["position"])
        return Spec(
            state.next_seq,
            str(current["format"]),
            focus=TYPES[position],
            angle=str(current["angle"]),
            series=series_name(str(current["format"]), str(current["angle"])),
            series_index=int(current["number"]),
            position=position + 1,
        )
    return _one_off(config, state)


def write(config: AppConfig, spec: Spec, target: date) -> Post:
    if spec.format == "gallery":
        return writer.gallery(config, spec.seq, spec.topic, target, spec.series, spec.series_index)
    if spec.format == "ranking":
        return writer.ranking(config, spec.seq, spec.topic, target, spec.series, spec.series_index)
    if spec.format == "manual":
        return writer.manual(config, spec.seq, spec.focus, spec.angle, target,
                             spec.series, spec.series_index, spec.position)
    return writer.compat(config, spec.seq, spec.focus, spec.angle, target,
                         spec.series, spec.series_index, spec.position)


def advance(state: FormatState, spec: Spec) -> None:
    state.next_seq = spec.seq + 1
    state.cursors[spec.format] = state.cursors.get(spec.format, 0) + 1
    if spec.position:
        assert state.series is not None
        state.series["position"] = spec.position
        if spec.position >= SERIES_LENGTH:
            # The sixteen are done: one post of something else, then the next subject.
            state.series = None
            state.between = True
    else:
        state.one_offs += 1
        state.between = False
