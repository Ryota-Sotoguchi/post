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
    "タイプに性別はないので「彼」「彼女」「男」「女」で人を指さず、タイプ名か「相手」「その人」と書く。"
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
    # The types the post is about come first, then the ones most searched, up
    # to the limit: a sixteen-type post had no type tag at all, so nobody
    # looking for their own type could find it.
    wanted = [*types, *K.POPULAR_TYPES][: K.TYPE_TAG_LIMIT] if fmt in ("gallery", "ranking") else types
    tags.extend(f"#{mbti}" for mbti in dict.fromkeys(wanted))
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


def gallery(config: AppConfig, seq: int, topic: str, target: date, series: str = "", series_index: int = 0) -> Post:
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
    return Post(seq, "gallery", target.isoformat(), title, hook, topic=topic, series=series, series_index=series_index,
                hashtags=_hashtags("gallery", K.POPULAR_TYPES), cards=cards, source=source)


# --- ranking ----------------------------------------------------------------


def _ranking_prompt(topic: str) -> str:
    return (
        f"お題:「{topic}ランキング」\n"
        "MBTI16タイプを1位から16位まで並べてください。\n"
        "- ranking は1位から順に16件。全タイプを1回ずつ\n"
        "- title: その順位になった決め手を一言で（10〜16字）\n"
        "- body: 理由（25〜40字）。読んだ人が「わかる」か「異議あり」と言いたくなるように\n"
        "- hook: 表紙の一文（25〜40字）。1位を知りたくて最後まで見たくなるように、1位は明かさない\n"
        "- question: 最後のスライドで聞く二択（20〜32字）。1位と、1位になりそうだった別のタイプを実名で挙げて"
        "「1位は◯◯？それとも△△？」の形にする。コメントで一言で答えられること\n"
        '形式: {"hook": "...", "question": "...", "ranking": [{"type": "ENTJ", "title": "...", "body": "..."}]}\n'
        f"タイプの参考情報:\n{_type_notes()}"
    )


def _ranking_fallback(topic: str) -> dict[str, Item]:
    order = list(TYPES)
    random.Random(topic).shuffle(order)
    return {
        mbti: Item(mbti, f"{TYPE_DATA[mbti]['archetype']}型", "・".join(TYPE_DATA[mbti]["traits"]), rank)
        for rank, mbti in enumerate(order, start=1)
    }


def ranking(config: AppConfig, seq: int, topic: str, target: date, series: str = "", series_index: int = 0) -> Post:
    data = _ask(config, _ranking_prompt(topic))
    items = _entries(data, "ranking")
    source = "llm"
    if items is None:
        items, source = _ranking_fallback(topic), "template"
    by_rank = sorted(items.values(), key=lambda item: item.rank)
    hook = _clip((data or {}).get("hook") or f"1位は意外なあのタイプ。{topic}を16位から発表", 60)
    title = K.ranking_title(topic)
    cards = [Card("cover", title=title, body=hook, label=FORMAT_LABELS["ranking"], types=TYPES)]
    # Every type gets its own slide, counted down from sixteenth. The bottom
    # twelve used to share three slides four at a time, which left most of the
    # types without a picture of their own.
    for item in reversed(by_rank):
        cards.append(Card("entry", title=item.title, body=item.body, label=f"第{item.rank}位",
                          number=item.rank, total=len(TYPES), items=(item,), types=(item.type,)))
    # A question with two named answers gets replied to; "コメントで反論して"
    # asks the viewer to compose something, which is a lot more to ask.
    question = _clip((data or {}).get("question"), 40)
    if not question or by_rank[0].type not in question:
        question = f"1位は{by_rank[0].type}？それとも{by_rank[1].type}？"
    cards.append(Card("closer", title="自分のタイプは何位だった？", body=question,
                      types=tuple(item.type for item in by_rank[:4])))
    return Post(seq, "ranking", target.isoformat(), title, hook, topic=topic, series=series, series_index=series_index,
                hashtags=_hashtags("ranking", tuple(item.type for item in by_rank[:3])),
                cards=cards, source=source)


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


def manual(config: AppConfig, seq: int, mbti: str, angle: str, target: date,
           series: str = "", series_index: int = 0, position: int = 0) -> Post:
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
                series=series, series_index=series_index, series_position=position,
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


def compat(config: AppConfig, seq: int, mbti: str, angle: str, target: date,
           series: str = "", series_index: int = 0, position: int = 0) -> Post:
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
                series=series, series_index=series_index, series_position=position,
                hashtags=_hashtags("compat", (mbti, good[0].type), angle), cards=cards, source=source)


def dumps(post: Post) -> str:
    return json.dumps(post.to_dict(), ensure_ascii=False, indent=2)


# --- a line, and four types it could have come from --------------------------


def _quiz_prompt(topic: str) -> str:
    return (
        f"お題:「{topic}」\n"
        "MBTIのセリフ当てクイズを6問作ってください。\n"
        "- quote: そのタイプが言いがちな一言（15〜28字）。誰の発言か当てられる具体性を持たせる\n"
        "- type: 正解のタイプ\n"
        "- others: 紛らわしい不正解3つ。正解と同じ傾向を持つタイプを選ぶ\n"
        "- why: 正解の理由（30〜45字）。「だからこのセリフが出る」と腑に落ちる書き方で\n"
        "- 6問で正解が重複しないこと\n"
        "- hook: 表紙の一文（25〜40字）。何問正解できるか試したくなるように\n"
        '形式: {"hook": "...", "questions": [{"quote": "...", "type": "INTJ", "others": ["INTP", "ENTJ", "ISTJ"], "why": "..."}]}\n'
        f"タイプの参考情報:\n{_type_notes()}"
    )


def _quiz_questions(data: dict | None) -> list[dict] | None:
    raw = (data or {}).get("questions")
    if not isinstance(raw, list) or len(raw) < 4:
        return None
    questions, answered = [], set()
    for entry in raw[:6]:
        if not isinstance(entry, dict):
            return None
        answer = str(entry.get("type", "")).strip().upper()
        others = [str(other).strip().upper() for other in entry.get("others", [])]
        others = [other for other in others if other in TYPES and other != answer]
        if answer not in TYPES or answer in answered or len(others) < 3 or not entry.get("quote"):
            return None
        answered.add(answer)
        questions.append({
            "quote": _clip(entry["quote"], 30),
            "type": answer,
            "others": others[:3],
            "why": _clip(entry.get("why"), BODY_LIMIT),
        })
    return questions


def _quiz_fallback(topic: str) -> list[dict]:
    picked = list(TYPES[:6])
    return [
        {"quote": _clip(TYPE_DATA[mbti]["line"], 30),
         "type": mbti,
         "others": [other for other in TYPES if other != mbti][:3],
         "why": "・".join(TYPE_DATA[mbti]["traits"])}
        for mbti in picked
    ]


def quiz(config: AppConfig, seq: int, topic: str, target: date, series: str = "", series_index: int = 0) -> Post:
    data = _ask(config, _quiz_prompt(topic))
    questions = _quiz_questions(data)
    source = "llm"
    if questions is None:
        questions, source = _quiz_fallback(topic), "template"
    title = K.quiz_title(topic)
    hook = _clip((data or {}).get("hook") or f"{topic}、何問当てられる？", 60)
    cards = [Card("cover", title=title, body=hook, label=FORMAT_LABELS["quiz"], types=TYPES)]
    for index, question in enumerate(questions, start=1):
        choices = sorted([question["type"], *question["others"]])
        cards.append(Card("quiz", title=question["quote"], label=topic, number=index, total=len(questions),
                          chips=tuple(choices)))
        cards.append(Card("answer", title=question["type"], body=question["why"], label=question["quote"],
                          number=index, total=len(questions), types=(question["type"],)))
    cards.append(Card("closer", title="何問当たった？", body="コメントで点数を教えて。", 
                      types=tuple(question["type"] for question in questions[:4])))
    return Post(seq, "quiz", target.isoformat(), title, hook, topic=topic, series=series, series_index=series_index,
                hashtags=_hashtags("quiz", tuple(question["type"] for question in questions[:3])),
                cards=cards, source=source)


# --- the reply each type would send ------------------------------------------


def _chat_prompt(topic: str) -> str:
    return (
        f"場面:「{topic}」\n"
        "16タイプそれぞれが実際に送りそうな返信を書いてください。\n"
        "- message: 相手から届いた文面（15〜25字）。全タイプ共通の1つを最初に決める\n"
        "- reply: そのタイプの返信（20〜40字）。LINEの文面そのままで、口調や絵文字の有無まで差をつける\n"
        "- note: その返信の裏にある心理（20〜32字）\n"
        "- 16タイプすべてを1回ずつ\n"
        "- hook: 表紙の一文（25〜40字）\n"
        '形式: {"hook": "...", "message": "...", "replies": [{"type": "INTJ", "reply": "...", "note": "..."}]}\n'
        f"タイプの参考情報:\n{_type_notes()}"
    )


def _chat_replies(data: dict | None) -> dict[str, Item] | None:
    raw = (data or {}).get("replies")
    if not isinstance(raw, list):
        return None
    found: dict[str, Item] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            return None
        mbti = str(entry.get("type", "")).strip().upper()
        if mbti not in TYPES or mbti in found or not entry.get("reply"):
            return None
        found[mbti] = Item(mbti, _clip(entry["reply"], 44), _clip(entry.get("note"), 36))
    return found if len(found) == len(TYPES) else None


def chat(config: AppConfig, seq: int, topic: str, target: date, series: str = "", series_index: int = 0) -> Post:
    data = _ask(config, _chat_prompt(topic))
    replies = _chat_replies(data)
    source = "llm"
    if replies is None:
        replies = {mbti: Item(mbti, _clip(TYPE_DATA[mbti]["line"], 44), "・".join(TYPE_DATA[mbti]["traits"]))
                   for mbti in TYPES}
        source = "template"
    message = _clip((data or {}).get("message") or topic, 28)
    title = K.chat_title(topic)
    hook = _clip((data or {}).get("hook") or f"{topic}、あなたはどう返す？", 60)
    cards = [Card("cover", title=title, body=hook, label=FORMAT_LABELS["chat"], types=TYPES)]
    for index, mbti in enumerate(TYPES, start=1):
        cards.append(Card("chat", title=replies[mbti].title, body=replies[mbti].body, label=message,
                          number=index, total=len(TYPES), items=(replies[mbti],), types=(mbti,)))
    cards.append(Card("closer", title="あなたの返信はどれに近い？", body="そのままコピーして使ってね。", types=TYPES))
    return Post(seq, "chat", target.isoformat(), title, hook, topic=topic, series=series, series_index=series_index,
                hashtags=_hashtags("chat", K.POPULAR_TYPES), cards=cards, source=source)


# --- the one line that ends it -----------------------------------------------


def _landmine_prompt(topic: str) -> str:
    return (
        f"お題:「{topic}」\n"
        "16タイプそれぞれの地雷になる一言を書いてください。\n"
        "- phrase: 実際に言われる一言（12〜22字）。カギカッコの中身だけ\n"
        "- why: なぜ刺さるのか（30〜45字）。そのタイプが大事にしているものに触れる\n"
        "- 16タイプすべてを1回ずつ。悪口ではなく「すれ違いの原因」として書く\n"
        "- hook: 表紙の一文（25〜40字）\n"
        '形式: {"hook": "...", "entries": [{"type": "INTJ", "phrase": "...", "why": "..."}]}\n'
        f"タイプの参考情報:\n{_type_notes()}"
    )


def _landmine_entries(data: dict | None) -> dict[str, Item] | None:
    raw = (data or {}).get("entries")
    if not isinstance(raw, list):
        return None
    found: dict[str, Item] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            return None
        mbti = str(entry.get("type", "")).strip().upper()
        phrase = _clip(entry.get("phrase"), 24).strip("「」")
        if mbti not in TYPES or mbti in found or not phrase:
            return None
        found[mbti] = Item(mbti, phrase, _clip(entry.get("why"), BODY_LIMIT))
    return found if len(found) == len(TYPES) else None


def landmine(config: AppConfig, seq: int, topic: str, target: date, series: str = "", series_index: int = 0) -> Post:
    data = _ask(config, _landmine_prompt(topic))
    entries = _landmine_entries(data)
    source = "llm"
    if entries is None:
        entries = {mbti: Item(mbti, _clip(TYPE_DATA[mbti]["stress"], 24), "・".join(TYPE_DATA[mbti]["traits"]))
                   for mbti in TYPES}
        source = "template"
    title = K.landmine_title(topic)
    hook = _clip((data or {}).get("hook") or f"{topic}、心当たりある？", 60)
    cards = [Card("cover", title=title, body=hook, label=FORMAT_LABELS["landmine"], types=TYPES)]
    for index, mbti in enumerate(TYPES, start=1):
        cards.append(Card("nogo", title=entries[mbti].title, body=entries[mbti].body, label=topic,
                          number=index, total=len(TYPES), items=(entries[mbti],), types=(mbti,)))
    cards.append(Card("closer", title="言われたことある？", body="コメントで教えて。心当たりがある人に送ってね。", types=TYPES))
    return Post(seq, "landmine", target.isoformat(), title, hook, topic=topic, series=series,
                series_index=series_index, hashtags=_hashtags("landmine", K.POPULAR_TYPES),
                cards=cards, source=source)


# --- who each type turns into in a group -------------------------------------


def _roles_prompt(topic: str) -> str:
    return (
        f"場面:「{topic}」\n"
        "16タイプを4つの役割に、4タイプずつ分けてください。\n"
        "- name: 役割の名前（6〜12字）。「仕切り役」のように一言で\n"
        "- types: そこに入る4タイプ\n"
        "- body: その役割の動き方（35〜55字）。その場面で実際に何をしているか\n"
        "- 16タイプを重複なく4×4に分けきること\n"
        "- hook: 表紙の一文（25〜40字）。自分と友達を当てはめたくなるように\n"
        '形式: {"hook": "...", "roles": [{"name": "...", "types": ["INTJ", "ENTJ", "INTP", "ENTP"], "body": "..."}]}\n'
        f"タイプの参考情報:\n{_type_notes()}"
    )


def _roles(data: dict | None) -> list[dict] | None:
    raw = (data or {}).get("roles")
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    seen: set[str] = set()
    roles = []
    for entry in raw:
        if not isinstance(entry, dict) or not entry.get("name"):
            return None
        types = [str(mbti).strip().upper() for mbti in entry.get("types", [])]
        if len(types) != 4 or any(mbti not in TYPES or mbti in seen for mbti in types):
            return None
        seen.update(types)
        roles.append({"name": _clip(entry["name"], 12), "types": types, "body": _clip(entry.get("body"), BODY_LIMIT)})
    return roles if len(seen) == len(TYPES) else None


def _roles_fallback() -> list[dict]:
    # The four groups the catalogue already sorts the types into.
    from mbti_tiktok_bot.catalog import TYPE_DATA as DATA

    names = {"分析家": "考えて動かす役", "外交官": "空気を整える役", "番人": "支えて回す役", "探検家": "場を沸かせる役"}
    roles = []
    for group, name in names.items():
        types = [mbti for mbti in TYPES if DATA[mbti]["group"] == group]
        roles.append({"name": name, "types": types[:4],
                      "body": "・".join(DATA[types[0]]["traits"])})
    return roles


def roles(config: AppConfig, seq: int, topic: str, target: date, series: str = "", series_index: int = 0) -> Post:
    data = _ask(config, _roles_prompt(topic))
    found = _roles(data)
    source = "llm"
    if found is None:
        found, source = _roles_fallback(), "template"
    title = K.roles_title(topic)
    hook = _clip((data or {}).get("hook") or f"{topic}、あなたはどの役割？", 60)
    cards = [Card("cover", title=title, body=hook, label=FORMAT_LABELS["roles"], types=TYPES)]
    cards.append(Card("map", title=title, label=topic, total=4,
                      items=tuple(Item(role["types"][0], role["name"]) for role in found),
                      types=tuple(mbti for role in found for mbti in role["types"])))
    for index, role in enumerate(found, start=1):
        cards.append(Card("role", title=role["name"], body=role["body"], label=topic, number=index, total=4,
                          types=tuple(role["types"])))
    cards.append(Card("closer", title="あなたはどの役割だった？", body="友達のタイプと並べてみて。", types=TYPES))
    return Post(seq, "roles", target.isoformat(), title, hook, topic=topic, series=series,
                series_index=series_index, hashtags=_hashtags("roles", K.POPULAR_TYPES), cards=cards, source=source)


# --- what to do today, for one type ------------------------------------------


def _remedy_prompt(mbti: str, angle: str) -> str:
    steps = K.REMEDY_STEPS
    return (
        f"「{K.remedy_title(mbti, angle)}」を書いてください。\n"
        f"{mbti}が{angle}に、その日のうちに実行できる処方箋です。\n"
        f"手順はこの順番で{len(steps)}つ: {'、'.join(steps)}\n"
        "- do: 実際の行動（15〜26字）。「〇〇する」の形で、今日できる粒度\n"
        "- why: そのタイプに効く理由（30〜45字）\n"
        "- hook: 表紙の一文（25〜40字）。読んだ人が自分のことだと思うように\n"
        '形式: {"hook": "...", "doses": [{"do": "...", "why": "..."}]}\n'
        f"タイプの参考情報:\n{_type_notes((mbti,))}"
    )


def remedy(config: AppConfig, seq: int, mbti: str, angle: str, target: date,
           series: str = "", series_index: int = 0, position: int = 0) -> Post:
    data = _ask(config, _remedy_prompt(mbti, angle))
    steps = K.REMEDY_STEPS
    raw = (data or {}).get("doses")
    doses: list[tuple[str, str]] = []
    if isinstance(raw, list) and len(raw) >= len(steps):
        for entry in raw[: len(steps)]:
            if not isinstance(entry, dict) or not entry.get("do"):
                doses = []
                break
            doses.append((_clip(entry["do"], 28), _clip(entry.get("why"), BODY_LIMIT)))
    source = "llm"
    if not doses:
        data_for = TYPE_DATA[mbti]
        doses = [(_clip(text, 28), "・".join(data_for["traits"]))
                 for text in (data_for["stress"], data_for["攻略"], data_for["friend"], data_for["line"])]
        source = "template"
    title = K.remedy_title(mbti, angle)
    hook = _clip((data or {}).get("hook") or f"{mbti}の{angle}、気合いより順番。", 60)
    cards = [Card("cover", title=title, body=hook, label=FORMAT_LABELS["remedy"], types=(mbti,))]
    for index, ((step, (action, why))) in enumerate(zip(steps, doses), start=1):
        cards.append(Card("dose", title=action, body=why, label=step, number=index, total=len(steps), types=(mbti,)))
    cards.append(Card("closer", title=f"今日の{mbti}に効く順番", body="保存して、しんどい日に開いてね。", types=(mbti,)))
    return Post(seq, "remedy", target.isoformat(), title, hook, focus=mbti, angle=angle,
                series=series, series_index=series_index, series_position=position,
                hashtags=_hashtags("remedy", (mbti,), angle), cards=cards, source=source)


# --- two types that get mistaken for each other -------------------------------


def _versus_prompt(pair: tuple[str, str]) -> str:
    left, right = pair
    return (
        f"「{left}と{right}の違い」を書いてください。似ていて見分けがつかない2タイプです。\n"
        f"観点はこの順番で{len(K.VERSUS_AXES)}つ: {'、'.join(K.VERSUS_AXES)}\n"
        f"- left: {left}の場合（20〜32字）\n"
        f"- right: {right}の場合（20〜32字）\n"
        "- 同じ観点で並べたときに違いがはっきり出るように、対になる書き方をする\n"
        "- hook: 表紙の一文（25〜40字）。どちらか分からない人が確かめたくなるように\n"
        '形式: {"hook": "...", "axes": [{"axis": "決め方", "left": "...", "right": "..."}]}\n'
        f"タイプの参考情報:\n{_type_notes(pair)}"
    )


def versus(config: AppConfig, seq: int, pair: tuple[str, str], target: date,
           series: str = "", series_index: int = 0, position: int = 0) -> Post:
    left, right = pair
    data = _ask(config, _versus_prompt(pair))
    raw = (data or {}).get("axes")
    axes: list[tuple[str, str, str]] = []
    if isinstance(raw, list) and len(raw) >= len(K.VERSUS_AXES) - 1:
        for index, entry in enumerate(raw[: len(K.VERSUS_AXES)]):
            if not isinstance(entry, dict) or not entry.get("left") or not entry.get("right"):
                axes = []
                break
            axes.append((_clip(entry.get("axis") or K.VERSUS_AXES[index], 12),
                         _clip(entry["left"], 36), _clip(entry["right"], 36)))
    source = "llm"
    if not axes:
        axes = [(axis, _clip(TYPE_DATA[left][key], 36), _clip(TYPE_DATA[right][key], 36))
                for axis, key in zip(K.VERSUS_AXES, ("攻略", "stress", "friend", "love", "line"))]
        source = "template"
    title = K.versus_title(pair)
    hook = _clip((data or {}).get("hook") or f"{left}と{right}、自分がどっちか分かる？", 60)
    cards = [Card("cover", title=title, body=hook, label=FORMAT_LABELS["versus"], types=pair)]
    for index, (axis, a, b) in enumerate(axes, start=1):
        cards.append(Card("versus", title=axis, label=title, number=index, total=len(axes),
                          items=(Item(left, body=a), Item(right, body=b)), types=pair))
    cards.append(Card("closer", title="あなたはどっちだった？", body="迷った人はコメントで聞いて。", types=pair))
    return Post(seq, "versus", target.isoformat(), title, hook, focus=left, angle=right,
                series=series, series_index=series_index, series_position=position,
                hashtags=_hashtags("versus", pair), cards=cards, source=source)
