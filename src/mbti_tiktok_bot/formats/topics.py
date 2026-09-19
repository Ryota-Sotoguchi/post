"""The seed material for each format.

Gallery and ranking posts each use up one topic; when the seeds run out the
planner asks the LLM for more and keeps them in the format state. Manual and
compat posts walk the sixteen types, and each full lap moves to the next angle,
so the same type comes back as 恋愛編, then 友達編, and so on.
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
    "manual": ("#取扱説明書",),
    "compat": ("#相性", "#相性診断"),
}
ANGLE_HASHTAGS = {"恋愛": "#恋愛", "友達": "#友達", "仕事": "#仕事"}


def gallery_title(topic: str) -> str:
    return f"{topic}の16タイプ"


def ranking_title(topic: str) -> str:
    return f"{topic}ランキング"


def manual_title(mbti: str, angle: str) -> str:
    return f"{mbti}の取扱説明書" if angle == "基本" else f"{mbti}の取扱説明書【{angle}編】"


def compat_title(mbti: str, angle: str) -> str:
    return f"{mbti}と相性がいいタイプ【{angle}】"
