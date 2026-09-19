"""Write a post's copy, then assemble its cards.

One LLM call per post, asked for strict JSON and checked hard - every gallery
and ranking has all sixteen types exactly once, a compat post never pairs a type
with itself. A reply that fails a check is not patched up; the post is written
from the type data instead, and marked source="template" so it can be spotted.
"""

from __future__ import annotations

import json
import random
from datetime import date

from mbti_tiktok_bot.catalog import MBTI_POST_ORDER, TYPE_DATA
from mbti_tiktok_bot.config import AppConfig
from mbti_tiktok_bot.formats import topics as K
from mbti_tiktok_bot.formats.model import FORMAT_LABELS, Card, Item, Post

TYPES = tuple(MBTI_POST_ORDER)

SYSTEM = (
    "あなたは日本のTikTokでMBTI系の画像カルーセルを企画・執筆するプロのコピーライターです。"
    "読者が「わかる」「これ私だ」と思わずコメントしたくなる、具体的な行動・セリフ・心の声で書いてください。"
    "「〜な性格です」のような抽象的な説明は避け、場面が浮かぶ描写にします。"
    "断定しすぎず「〜しがち」「〜かも」を適度に使い、特定のタイプを貶めないこと。"
    "短くリズムよく、一文目で掴むこと。絵文字と顔文字は使わない（画像に文字として載るため）。"
    "hook は内容の説明ではなく、続きを見ずにいられない一文にする。意外性、言い切り、読者への問いかけのどれかを使い、"
    "「紹介」「まとめ」「解説」のような説明的な言葉は使わない。"
    "出力は指定されたJSONオブジェクトのみ。"
)

TITLE_LIMIT = 24
BODY_LIMIT = 90


def _type_notes(types: tuple[str, ...] = TYPES) -> str:
    lines = []
    for mbti in types:
        data = TYPE_DATA[mbti]
        lines.append(f"{mbti}（{data['archetype']}）: {'／'.join(data['traits'])}。恋愛:{data['love']}。ストレス時:{data['stress']}")
    return "\n".join(lines)


def _clip(text: object, limit: int) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


# Sixteen entries of copy take a reasoning model most of a minute; the shared
# helper's 60s limit timed the gallery out and dropped it to templates.
TIMEOUT = 180


def _ask(config: AppConfig, prompt: str) -> dict | None:
    if not config.openai_api_key:
        return None
    import requests

    from mbti_tiktok_bot.planner import _extract_json_object

    payload: dict = {
        "model": config.openai_model,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
    }
    if config.openai_model.lower().startswith(("gpt-5", "o")):
        # Copywriting does not need deep reasoning, and the default spends
        # most of the call on it.
        payload["reasoning_effort"] = "low"
    url = f"{config.openai_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {config.openai_api_key}", "Content-Type": "application/json"}
    for attempt in range(2):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
            if response.status_code == 400 and "reasoning_effort" in payload:
                payload.pop("reasoning_effort")
                continue
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except Exception as error:
            if attempt == 0:
                continue
            print(f"LLM unavailable for this post, writing it from type data: {error}")
            return None
        data = _extract_json_object(content)
        if isinstance(data, dict):
            return data
    return None


def _hashtags(fmt: str, types: tuple[str, ...] = (), angle: str = "") -> tuple[str, ...]:
    tags = [*K.BASE_HASHTAGS, *K.FORMAT_HASHTAGS[fmt]]
    if angle in K.ANGLE_HASHTAGS:
        tags.append(K.ANGLE_HASHTAGS[angle])
    tags.extend(f"#{mbti}" for mbti in types)
    return tuple(dict.fromkeys(tags))


# --- gallery ----------------------------------------------------------------


def _gallery_prompt(topic: str) -> str:
    return (
        f"お題:「{topic}」\n"
        "MBTI16タイプそれぞれの、その瞬間の反応を書いてください。\n"
        "- title: そのタイプらしさが一目でわかるセリフか行動（12〜18字）\n"
        "- body: 心の声や補足（25〜40字）\n"
        "- 16タイプすべてを1回ずつ。内容が互いに被らないこと\n"
        "- hook: 表紙に載せる一文（25〜40字）。見た人が自分のタイプを探したくなるように\n"
        '形式: {"hook": "...", "entries": [{"type": "INTJ", "title": "...", "body": "..."}]}\n'
        f"タイプの参考情報:\n{_type_notes()}"
    )


def _entries(data: dict | None, key: str) -> dict[str, Item] | None:
    """The reply's entries by type, or None unless all sixteen are there once."""
    if not data or not isinstance(data.get(key), list):
        return None
    found: dict[str, Item] = {}
    for rank, entry in enumerate(data[key], start=1):
        if not isinstance(entry, dict):
            return None
        mbti = str(entry.get("type", "")).strip().upper()
        if mbti not in TYPES or mbti in found:
            return None
        title, body = _clip(entry.get("title"), TITLE_LIMIT), _clip(entry.get("body"), BODY_LIMIT)
        if not title:
            return None
        found[mbti] = Item(mbti, title, body, rank)
    return found if len(found) == len(TYPES) else None


def _gallery_fallback(topic: str) -> dict[str, Item]:
    field = "line" if any(word in topic for word in ("LINE", "既読", "電話", "連絡")) else (
        "stress" if any(word in topic for word in ("怒", "限界", "言い合い", "喧嘩", "ドタキャン", "忘れ")) else (
            "love" if any(word in topic for word in ("好き", "恋", "デート", "失恋", "目が合")) else "friend"))
    return {
        mbti: Item(mbti, _clip(TYPE_DATA[mbti][field], TITLE_LIMIT), "・".join(TYPE_DATA[mbti]["traits"]))
        for mbti in TYPES
    }


def gallery(config: AppConfig, seq: int, topic: str, target: date) -> Post:
    data = _ask(config, _gallery_prompt(topic))
    items = _entries(data, "entries")
    source = "llm"
    if items is None:
        items, source = _gallery_fallback(topic), "template"
    hook = _clip((data or {}).get("hook") or f"{topic}、あなたのタイプはどれ？", 60)
    title = K.gallery_title(topic)
    cards = [Card("cover", title=title, body=hook, label=FORMAT_LABELS["gallery"], types=TYPES)]
    for index, mbti in enumerate(TYPES, start=1):
        cards.append(Card("entry", title=items[mbti].title, body=items[mbti].body, label=topic,
                          number=index, total=len(TYPES), items=(items[mbti],), types=(mbti,)))
    cards.append(Card("closer", title="あなたは何タイプ？", body="コメントでタイプを教えて。当てはまった人は保存しておいてね。",
                      types=TYPES))
    return Post(seq, "gallery", target.isoformat(), title, hook, topic=topic,
                hashtags=_hashtags("gallery"), cards=cards, source=source)


# --- ranking ----------------------------------------------------------------


def _ranking_prompt(topic: str) -> str:
    return (
        f"お題:「{topic}ランキング」\n"
        "MBTI16タイプを1位から16位まで並べてください。\n"
        "- ranking は1位から順に16件。全タイプを1回ずつ\n"
        "- title: その順位になった決め手を一言で（10〜16字）\n"
        "- body: 理由（25〜40字）。読んだ人が「わかる」か「異議あり」と言いたくなるように\n"
        "- hook: 表紙の一文（25〜40字）。1位を知りたくて最後まで見たくなるように、1位は明かさない\n"
        '形式: {"hook": "...", "ranking": [{"type": "ENTJ", "title": "...", "body": "..."}]}\n'
        f"タイプの参考情報:\n{_type_notes()}"
    )


def _ranking_fallback(topic: str) -> dict[str, Item]:
    order = list(TYPES)
    random.Random(topic).shuffle(order)
    return {
        mbti: Item(mbti, f"{TYPE_DATA[mbti]['archetype']}型", "・".join(TYPE_DATA[mbti]["traits"]), rank)
        for rank, mbti in enumerate(order, start=1)
    }


def ranking(config: AppConfig, seq: int, topic: str, target: date) -> Post:
    data = _ask(config, _ranking_prompt(topic))
    items = _entries(data, "ranking")
    source = "llm"
    if items is None:
        items, source = _ranking_fallback(topic), "template"
    by_rank = sorted(items.values(), key=lambda item: item.rank)
    hook = _clip((data or {}).get("hook") or f"1位は意外なあのタイプ。{topic}を16位から発表", 60)
    title = K.ranking_title(topic)
    cards = [Card("cover", title=title, body=hook, label=FORMAT_LABELS["ranking"], types=TYPES)]
    # The bottom twelve go four to a slide; the top four get a slide each, so
    # the count slows down as it nears first place.
    for low in (16, 12, 8):
        group = tuple(item for item in reversed(by_rank) if low - 3 <= item.rank <= low)
        cards.append(Card("grid", title=f"{low}位〜{low - 3}位", label=topic, number=low, total=16,
                          items=group, types=tuple(item.type for item in group)))
    for rank in (4, 3, 2, 1):
        item = by_rank[rank - 1]
        cards.append(Card("entry", title=item.title, body=item.body, label=f"第{rank}位", number=rank, total=16,
                          items=(item,), types=(item.type,)))
    cards.append(Card("closer", title="自分のタイプは何位だった？", body="納得いかない人はコメントで反論して。",
                      types=tuple(item.type for item in by_rank[:4])))
    return Post(seq, "ranking", target.isoformat(), title, hook, topic=topic,
                hashtags=_hashtags("ranking", (by_rank[0].type,)), cards=cards, source=source)


# --- manual -----------------------------------------------------------------


def _manual_prompt(mbti: str, angle: str) -> str:
    sections = K.MANUAL_SECTIONS[angle]
    return (
        f"「{K.manual_title(mbti, angle)}」を書いてください。\n"
        f"セクションはこの順番で{len(sections)}個: {'、'.join(sections)}\n"
        "- heading: 基本はそのまま。より刺さるなら10字以内で言い換えてよい\n"
        "- body: 40〜70字。そのタイプの人が読んで「バレてる」と思うくらい具体的に\n"
        "- 最初のセクションだけ chips に、その人を表すキーワードを3〜5個（各8字以内）\n"
        "- hook: 表紙の一文（25〜40字）。そのタイプの人と、周りの人の両方が読みたくなるように\n"
        '形式: {"hook": "...", "sections": [{"heading": "...", "body": "...", "chips": ["..."]}]}\n'
        f"タイプの参考情報:\n{_type_notes((mbti,))}"
    )


def _manual_fallback(mbti: str, angle: str) -> list[tuple[str, str, tuple[str, ...]]]:
    data = TYPE_DATA[mbti]
    bodies = [data["love"], data["攻略"], data["stress"], data["stress"], data["line"], data["攻略"], data["stress"], data["攻略"]]
    return [
        (heading, str(body), tuple(data["traits"]) if index == 0 else ())
        for index, (heading, body) in enumerate(zip(K.MANUAL_SECTIONS[angle], bodies))
    ]


def manual(config: AppConfig, seq: int, mbti: str, angle: str, target: date) -> Post:
    data = _ask(config, _manual_prompt(mbti, angle))
    skeleton = K.MANUAL_SECTIONS[angle]
    sections: list[tuple[str, str, tuple[str, ...]]] = []
    raw = (data or {}).get("sections")
    if isinstance(raw, list) and len(raw) >= len(skeleton) - 2:
        for index, entry in enumerate(raw[: len(skeleton)]):
            if not isinstance(entry, dict) or not entry.get("body"):
                sections = []
                break
            heading = _clip(entry.get("heading") or skeleton[index], 12)
            chips = tuple(_clip(chip, 10) for chip in entry.get("chips") or () if str(chip).strip())[:5]
            sections.append((heading, _clip(entry["body"], BODY_LIMIT), chips))
    source = "llm"
    if not sections:
        sections, source = _manual_fallback(mbti, angle), "template"
    title = K.manual_title(mbti, angle)
    hook = _clip((data or {}).get("hook") or f"{mbti}と仲良くなりたい人は保存必須。", 60)
    cards = [Card("cover", title=title, body=hook, label=FORMAT_LABELS["manual"], types=(mbti,))]
    for index, (heading, body, chips) in enumerate(sections, start=1):
        cards.append(Card("section", title=heading, body=body, label=f"{mbti}の取扱説明書", number=index,
                          total=len(sections), chips=chips, types=(mbti,)))
    cards.append(Card("closer", title=f"周りの{mbti}に送ってみて", body="当たってたら保存。答え合わせしてみてね。", types=(mbti,)))
    return Post(seq, "manual", target.isoformat(), title, hook, focus=mbti, angle=angle,
                hashtags=_hashtags("manual", (mbti,), angle), cards=cards, source=source)


# --- compat -----------------------------------------------------------------


def _compat_prompt(mbti: str, angle: str) -> str:
    return (
        f"お題:「{K.compat_title(mbti, angle)}」\n"
        f"{mbti}から見た{angle}の相性を書いてください。\n"
        "- good: 相性がいい3タイプを1位から順に\n"
        "- caution: 要注意な3タイプを、一番注意が必要なものから順に\n"
        f"- {mbti}自身は含めない。good と caution に同じタイプを入れない\n"
        "- title: 二人の関係を一言で（10〜16字）\n"
        "- body: 理由（30〜45字）。具体的な場面で\n"
        "- hook: 表紙の一文（25〜40字）\n"
        '形式: {"hook": "...", "good": [{"type": "ENFP", "title": "...", "body": "..."}], "caution": [...]}\n'
        f"タイプの参考情報:\n{_type_notes()}"
    )


def _pairs(data: dict | None, mbti: str) -> tuple[list[Item], list[Item]] | None:
    if not data:
        return None
    result: list[list[Item]] = []
    seen = {mbti}
    for key in ("good", "caution"):
        entries = data.get(key)
        if not isinstance(entries, list) or len(entries) < 3:
            return None
        items: list[Item] = []
        for rank, entry in enumerate(entries[:3], start=1):
            other = str((entry or {}).get("type", "")).strip().upper()
            if other not in TYPES or other in seen:
                return None
            seen.add(other)
            items.append(Item(other, _clip(entry.get("title"), TITLE_LIMIT), _clip(entry.get("body"), BODY_LIMIT), rank))
        result.append(items)
    return result[0], result[1]


def compat(config: AppConfig, seq: int, mbti: str, angle: str, target: date) -> Post:
    data = _ask(config, _compat_prompt(mbti, angle))
    pairs = _pairs(data, mbti)
    source = "llm"
    if pairs is None:
        good_types, bad_types = K.COMPATIBILITY[mbti]
        pairs = (
            [Item(other, f"{TYPE_DATA[other]['archetype']}との好相性", str(TYPE_DATA[other]["攻略"]), rank)
             for rank, other in enumerate(good_types, start=1)],
            [Item(other, f"{TYPE_DATA[other]['archetype']}とはすれ違いがち", str(TYPE_DATA[other]["stress"]), rank)
             for rank, other in enumerate(bad_types, start=1)],
        )
        source = "template"
    good, caution = pairs
    title = K.compat_title(mbti, angle)
    hook = _clip((data or {}).get("hook") or f"{mbti}と{angle}で一番うまくいくのは？", 60)
    cards = [Card("cover", title=title, body=hook, label=FORMAT_LABELS["compat"],
                  types=(mbti, good[0].type))]
    # Third place first, so the best match is the reveal.
    for item in reversed(good):
        cards.append(Card("pair", title=item.title, body=item.body, label=f"相性◎ 第{item.rank}位",
                          number=item.rank, total=3, items=(Item(mbti), item), types=(mbti, item.type)))
    for item in reversed(caution):
        cards.append(Card("pair", title=item.title, body=item.body, label=f"要注意 第{item.rank}位",
                          number=item.rank, total=3, items=(Item(mbti), item), types=(mbti, item.type)))
    cards.append(Card("closer", title="相手のタイプはどうだった？", body="気になる人に送って、答え合わせしてみて。",
                      types=(mbti, good[0].type)))
    return Post(seq, "compat", target.isoformat(), title, hook, focus=mbti, angle=angle,
                hashtags=_hashtags("compat", (mbti,), angle), cards=cards, source=source)


def dumps(post: Post) -> str:
    return json.dumps(post.to_dict(), ensure_ascii=False, indent=2)
