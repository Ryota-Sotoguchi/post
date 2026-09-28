"""The seed material for each format.

A one-off post uses up one topic; when the seeds run out the planner asks the
LLM for more and keeps them in the format state. A series walks its subjects -
the sixteen types, or the eight pairs that get mistaken for each other - and
each full lap moves to the next angle, so a type comes back as 恋愛編, then
友達編, and so on.
"""

from __future__ import annotations

# 「〇〇の16タイプ」: a moment everyone has been in, so every viewer can find
# themselves in it.
GALLERY_TOPICS = (
    "既読スルーされた時",
    "好きな人と目が合った時",
    "怒りが限界を超えた時",
    "寝る前の頭の中",
    "失恋した夜",
    "ドタキャンされた時",
    "褒められた時の本音",
    "月曜の朝",
    "急に電話がかかってきた時",
    "初デートの前日",
    "推しが尊すぎた時",
    "一人になりたい時",
    "好きバレした時",
    "グループLINEが盛り上がってる時",
    "誕生日を忘れられた時",
    "給料日",
    "旅行の計画を立てる時",
    "言い合いになった時",
    "気まずい沈黙が流れた時",
    "予定が急に空いた休日",
)

# 「〇〇タイプランキング」: a claim with a winner, so viewers swipe to find it
# and argue with the order.
RANKING_TOPICS = (
    "怒らせると一番怖いタイプ",
    "実は一番寂しがりなタイプ",
    "恋人にしたら一番幸せなタイプ",
    "人を沼らせるタイプ",
    "一番マイペースなタイプ",
    "嘘が一番下手なタイプ",
    "隠れ天才タイプ",
    "一番ヤキモチを焼くタイプ",
    "一途さが強いタイプ",
    "秘密を一番守れるタイプ",
    "第一印象と中身のギャップが大きいタイプ",
    "夜ふかし常習犯なタイプ",
    "人見知りが激しいタイプ",
    "一番モテるタイプ",
    "キレると手がつけられないタイプ",
    "実は一番繊細なタイプ",
)

# 「このセリフ、どのタイプ？」: a line anyone has heard, with four plausible
# answers, so the guess is a real one.
QUIZ_TOPICS = (
    "LINEでよく出る一言",
    "断る時の一言",
    "怒ってる時の一言",
    "照れ隠しの一言",
    "疲れてる時の一言",
    "デート中の一言",
    "職場で出る一言",
    "落ち込んでる人にかける一言",
    "褒める時の一言",
    "別れ際の一言",
)

# 「〇〇と送られた時の返信」: the reply itself is the value - it can be copied.
CHAT_TOPICS = (
    "急に『今日空いてる？』と送られた時",
    "『ちょっと相談がある』と送られた時",
    "既読無視した後に催促が来た時",
    "『怒ってる？』と聞かれた時",
    "デートに誘われた時",
    "『今から行っていい？』と言われた時",
    "落ち込んでる友達から連絡が来た時",
    "『好きかも』と言われた時",
    "予定をドタキャンされた時",
    "久しぶりの相手から連絡が来た時",
)

# 「言われたら一発で冷める一言」: what not to say, which is remembered longer
# than what to say.
LANDMINE_TOPICS = (
    "言われたら一発で冷める一言",
    "地雷を踏む褒め方",
    "仕事で言われるとやる気を失う一言",
    "恋人に言われたら終わる一言",
    "励ましのつもりで刺さる一言",
    "家族に言われるときつい一言",
    "友達に言われて距離を置く一言",
    "初対面で言ってはいけない一言",
)

# 「この場面での役割」: four roles, four types each, so everyone can place
# themselves and their friends.
ROLE_TOPICS = (
    "飲み会",
    "グループ旅行の計画",
    "職場のチーム",
    "推し活の現場",
    "文化祭の準備",
    "急なトラブル対応",
    "友達グループの日常",
    "合コン",
)

# Pairs that get mistaken for each other, and that people search as a pair.
VERSUS_PAIRS = (
    ("INFP", "INFJ"),
    ("ENFP", "ESFP"),
    ("INTJ", "INTP"),
    ("ENTJ", "ESTJ"),
    ("ISFJ", "ISTJ"),
    ("ENFJ", "ESFJ"),
    ("ISTP", "ISFP"),
    ("ENTP", "ESTP"),
)
VERSUS_AXES = ("決め方", "沈黙の意味", "疲れる相手", "好意の出し方", "本音が出る時")

# A prescription: what to do, on the day it is needed.
REMEDY_ANGLES = ("疲れた日", "落ち込んだ日", "焦ってる日", "人に会いたくない日")
REMEDY_STEPS = ("まずこれをやめる", "最初の5分", "戻ってくる合図", "明日に残さないこと")

MANUAL_ANGLES = ("基本", "恋愛", "友達", "仕事")
COMPAT_ANGLES = ("恋愛", "友達", "仕事")

# The section headings a manual is built on, per angle. The LLM writes the
# content and may reword a heading, but the skeleton keeps every manual the
# same length and in the same order, which is what makes it read as a series.
MANUAL_SECTIONS = {
    "基本": ("基本スペック", "喜ぶこと", "苦手なこと", "これは地雷", "刺さる一言", "距離の縮め方", "疲れた時のサイン", "扱い方のコツ"),
    "恋愛": ("好きな人への態度", "脈ありサイン", "冷めるポイント", "刺さる誘い方", "喧嘩した時", "本命にだけ見せる顔", "長続きのコツ", "扱い方のコツ"),
    "友達": ("第一印象", "仲良くなるきっかけ", "友達にだけ見せる顔", "苦手な付き合い方", "頼られた時", "距離を置くサイン", "長く続くコツ", "扱い方のコツ"),
    "仕事": ("仕事のスタイル", "得意な役割", "やる気が出る瞬間", "ストレスの原因", "言われて嬉しい一言", "NGな指示の出し方", "伸びる環境", "扱い方のコツ"),
}

# A fallback when the LLM is unavailable. These are the pairings commonly
# repeated in MBTI content, which is what viewers expect to see.
COMPATIBILITY = {
    "INFJ": (("ENFP", "ENTP", "INTJ"), ("ESTP", "ESFP", "ISTP")),
    "ENFP": (("INFJ", "INTJ", "ENFJ"), ("ISTJ", "ESTJ", "ISFJ")),
    "INTJ": (("ENFP", "ENTP", "INFJ"), ("ESFP", "ESFJ", "ISFP")),
    "ENTP": (("INFJ", "INTJ", "ENFP"), ("ISFJ", "ESFJ", "ISTJ")),
    "INFP": (("ENFJ", "ENTJ", "INFJ"), ("ESTJ", "ESTP", "ISTJ")),
    "ENFJ": (("INFP", "ISFP", "INFJ"), ("ISTP", "ESTP", "INTP")),
    "INTP": (("ENTJ", "ENTP", "INFJ"), ("ESFJ", "ESTJ", "ISFJ")),
    "ENTJ": (("INTP", "INFP", "INTJ"), ("ISFP", "ESFP", "ISFJ")),
    "ISFJ": (("ESFP", "ESTP", "ISTJ"), ("ENTP", "INTP", "ENFP")),
    "ESFJ": (("ISFP", "ISTP", "ESTJ"), ("INTP", "ENTP", "INTJ")),
    "ISTJ": (("ESFP", "ESTP", "ISFJ"), ("ENFP", "INFP", "ENTP")),
    "ESTJ": (("ISTP", "ISFP", "ISTJ"), ("INFP", "ENFP", "INTP")),
    "ISFP": (("ENFJ", "ESFJ", "ESTJ"), ("ENTJ", "INTJ", "ENTP")),
    "ESFP": (("ISFJ", "ISTJ", "ESTP"), ("INTJ", "INFJ", "INTP")),
    "ISTP": (("ESTJ", "ESFJ", "ESTP"), ("ENFJ", "INFJ", "ENFP")),
    "ESTP": (("ISFJ", "ISTJ", "ESFP"), ("INFJ", "INFP", "ENFJ")),
}

BASE_HASHTAGS = ("#MBTI", "#mbti診断", "#16personalities", "#性格診断")
FORMAT_HASHTAGS = {
    "gallery": ("#16タイプ", "#あるある"),
    "ranking": ("#ランキング", "#16タイプ"),
    "quiz": ("#心理テスト", "#クイズ", "#16タイプ"),
    "chat": ("#LINE", "#返信", "#16タイプ"),
    "landmine": ("#地雷", "#あるある", "#16タイプ"),
    "roles": ("#役割", "#グループ", "#16タイプ"),
    "manual": ("#取扱説明書",),
    "compat": ("#相性", "#相性診断"),
    "remedy": ("#処方箋", "#メンタルケア"),
    "versus": ("#違い", "#どっち"),
}
ANGLE_HASHTAGS = {"恋愛": "#恋愛", "友達": "#友達", "仕事": "#仕事"}

# People look for their own type by name, so a post carries the tags of the
# types it is actually about. A sixteen-type post cannot carry all sixteen
# without reading as tag spam, so it takes the ones searched most in Japan.
POPULAR_TYPES = ("INFP", "INFJ", "ENFP", "INTJ")
TYPE_TAG_LIMIT = 5


def gallery_title(topic: str) -> str:
    return f"{topic}の16タイプ"


def ranking_title(topic: str) -> str:
    return f"{topic}ランキング"


def manual_title(mbti: str, angle: str) -> str:
    return f"{mbti}の取扱説明書" if angle == "基本" else f"{mbti}の取扱説明書【{angle}編】"


def compat_title(mbti: str, angle: str) -> str:
    return f"{mbti}と相性がいいタイプ【{angle}】"


def quiz_title(topic: str) -> str:
    return f"{topic}、どのタイプ？"


def chat_title(topic: str) -> str:
    return f"{topic}の返信16タイプ"


def landmine_title(topic: str) -> str:
    return f"MBTI別・{topic}"


def roles_title(topic: str) -> str:
    return f"{topic}での役割16タイプ"


def remedy_title(mbti: str, angle: str) -> str:
    return f"{mbti}の{angle}の処方箋"


def versus_title(pair: tuple[str, str]) -> str:
    return f"{pair[0]}と{pair[1]}、どっち？"
