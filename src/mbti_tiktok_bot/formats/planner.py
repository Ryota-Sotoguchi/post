"""Which post comes next, and the state that remembers.

Ten posts a day in a fixed pattern: two galleries, two rankings, three manuals
and three compat posts, interleaved so no format runs twice in a row. Each
format keeps its own cursor. Manuals walk the sixteen types and move to the next
angle each lap; compat does the same, offset by eight so a day never carries
the same type's manual and compat post.
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

PATTERN = ("gallery", "manual", "ranking", "compat", "manual", "gallery", "compat", "manual", "ranking", "compat")
STATE_FILE = "format_state.json"
TYPES = tuple(MBTI_POST_ORDER)
SIMILAR = 0.8


@dataclass(slots=True)
class FormatState:
    next_seq: int = 1
    cursors: dict[str, int] = field(default_factory=lambda: {name: 0 for name in FORMATS})
    extra_topics: dict[str, list[str]] = field(default_factory=lambda: {"gallery": [], "ranking": []})

    def to_dict(self) -> dict:
        return {"next_seq": self.next_seq, "cursors": self.cursors, "extra_topics": self.extra_topics}


def state_path(config: AppConfig) -> Path:
    return config.state_dir / STATE_FILE


def load_state(config: AppConfig) -> FormatState:
    path = state_path(config)
    if not path.exists():
        return FormatState()
    data = json.loads(path.read_text(encoding="utf-8"))
    state = FormatState()
    state.next_seq = int(data.get("next_seq", 1))
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


def next_spec(config: AppConfig, state: FormatState) -> Spec:
    seq = state.next_seq
    name = PATTERN[(seq - 1) % len(PATTERN)]
    cursor = state.cursors[name]
    if name in ("gallery", "ranking"):
        pool = _pool(name, state)
        if cursor >= len(pool):
            state.extra_topics[name].extend(_more_topics(config, name, state))
            pool = _pool(name, state)
        # Nothing new to be had: go round again rather than stop publishing.
        return Spec(seq, name, topic=pool[cursor % len(pool)])
    if name == "manual":
        return Spec(seq, name, focus=TYPES[cursor % 16], angle=K.MANUAL_ANGLES[(cursor // 16) % len(K.MANUAL_ANGLES)])
    return Spec(seq, name, focus=TYPES[(cursor + 8) % 16], angle=K.COMPAT_ANGLES[(cursor // 16) % len(K.COMPAT_ANGLES)])


def write(config: AppConfig, spec: Spec, target: date) -> Post:
    if spec.format == "gallery":
        return writer.gallery(config, spec.seq, spec.topic, target)
    if spec.format == "ranking":
        return writer.ranking(config, spec.seq, spec.topic, target)
    if spec.format == "manual":
        return writer.manual(config, spec.seq, spec.focus, spec.angle, target)
    return writer.compat(config, spec.seq, spec.focus, spec.angle, target)


def advance(state: FormatState, spec: Spec) -> None:
    state.next_seq = spec.seq + 1
    state.cursors[spec.format] += 1
