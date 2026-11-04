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
    # 仕事と学校
    "会議で意見を求められた時",
    "理不尽に怒られた時",
    "初出勤の朝",
    "テスト前日の夜",
    "在宅勤務の昼下がり",
    "進路に迷った時",
    "大きなミスをした直後",
    "残業が決まった瞬間",
    # お金
    "財布を落とした時",
    "衝動買いした翌朝",
    "節約を決意した日",
    "友達にお金を借りられた時",
    # 暮らし
    "寝坊した朝",
    "大掃除を始めた時",
    "冷蔵庫の中身を見た時",
    "引っ越しの荷造り",
    "休日に何もしなかった夜",
    # 人との距離
    "久しぶりの同窓会",
    "苦手な人と二人になった時",
    "頼み事を断れなかった時",
    "褒められ慣れていない時",
    # 推しと趣味
    "ライブ当日の朝",
    "新しい趣味を始めた時",
    "推しが炎上した時",
    # 心
    "急に不安になった夜",
    "全部投げ出したくなった時",
    "自分だけ置いていかれた気がした時",
    # 体と習慣
    "ダイエットを決意した時",
    "寝不足の朝",
    "ジムに入会した直後",
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
    # 仕事
    "仕事が一番早いタイプ",
    "会議で一番発言するタイプ",
    "リーダーに向いてるタイプ",
    "在宅勤務が向いてるタイプ",
    "転職を繰り返しがちなタイプ",
    "報連相が苦手なタイプ",
    # お金
    "貯金が一番できるタイプ",
    "衝動買いが止まらないタイプ",
    "お金の管理が一番細かいタイプ",
    # 暮らし
    "部屋が一番散らかってるタイプ",
    "朝が一番弱いタイプ",
    "物をなくしやすいタイプ",
    "方向音痴なタイプ",
    # 性格の裏側
    "謝るのが一番苦手なタイプ",
    "人の話を聞いてないタイプ",
    "一番心配性なタイプ",
    "実は打たれ強いタイプ",
    "一度嫌うと戻らないタイプ",
    # 友情
    "友達が一番多いタイプ",
    "一人の時間が一番必要なタイプ",
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
    "仕事でミスした時の一言",
    "お金の話になった時の一言",
    "頼み事をする時の一言",
    "焦ってる時の一言",
    "励ます時の一言",
    "久しぶりに会った時の一言",
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
    "休日に上司から連絡が来た時",
    "グループの予定が決まらない時",
    "『お金貸して』と言われた時",
    "頼んだ仕事が終わってない時",
    "ドタキャンのお詫びが来た時",
    "急に重い相談をされた時",
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
    "努力を否定する一言",
    "上司から言われると心が折れる一言",
    "見た目について言われたくない一言",
    "善意のつもりで刺さる一言",
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
    "引っ越しの手伝い",
    "大人数の食事会",
    "部活の最後の大会",
    "家族旅行",
    "災害時の避難所",
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
REMEDY_ANGLES = ("疲れた日", "落ち込んだ日", "焦ってる日", "人に会いたくない日",
                 "眠れない夜", "やる気が出ない日", "人間関係に疲れた日")
REMEDY_STEPS = ("まずこれをやめる", "最初の5分", "戻ってくる合図", "明日に残さないこと")

MANUAL_ANGLES = ("基本", "恋愛", "友達", "仕事", "家族", "お金", "ストレス")
COMPAT_ANGLES = ("恋愛", "友達", "仕事", "家族", "チーム")

# The section headings a manual is built on, per angle. The LLM writes the
# content and may reword a heading, but the skeleton keeps every manual the
# same length and in the same order, which is what makes it read as a series.
MANUAL_SECTIONS = {
    "基本": ("基本スペック", "喜ぶこと", "苦手なこと", "これは地雷", "刺さる一言", "距離の縮め方", "疲れた時のサイン", "扱い方のコツ"),
    "恋愛": ("好きな人への態度", "脈ありサイン", "冷めるポイント", "刺さる誘い方", "喧嘩した時", "本命にだけ見せる顔", "長続きのコツ", "扱い方のコツ"),
    "友達": ("第一印象", "仲良くなるきっかけ", "友達にだけ見せる顔", "苦手な付き合い方", "頼られた時", "距離を置くサイン", "長く続くコツ", "扱い方のコツ"),
    "仕事": ("仕事のスタイル", "得意な役割", "やる気が出る瞬間", "ストレスの原因", "言われて嬉しい一言", "NGな指示の出し方", "伸びる環境", "扱い方のコツ"),
    "家族": ("家でのふるまい", "親に言えないこと", "帰省した時", "心配のかけ方", "家族に求めるもの", "限界が来るきっかけ", "距離の取り方", "扱い方のコツ"),
    "お金": ("お金の使い方", "ケチになるところ", "財布の紐が緩む瞬間", "貯金のクセ", "後悔しがちな買い物", "奢る・奢られる時", "向いてる管理方法", "扱い方のコツ"),
    "ストレス": ("最初に出るサイン", "溜め込み方", "爆発する直前", "効く休ませ方", "逆効果な励まし", "立ち直るきっかけ", "周りができること", "扱い方のコツ"),
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
