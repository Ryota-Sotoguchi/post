from __future__ import annotations

from dataclasses import dataclass

TYPE_DATA: dict[str, dict[str, object]] = {
    "INTJ": {
        "archetype": "戦略家",
        "group": "分析家",
        "traits": ["先を読む", "感情より設計", "必要な人には一途"],
        "love": "好きになると静かに深く追う",
        "stress": "無駄が増えると急に口数が減る",
        "line": "返信は短いのに内容は本気",
        "攻略": "結論のない駆け引きより、誠実さと頭の良さが刺さる",
        "friend": "少人数で深くつながる",
    },
    "INTP": {
        "archetype": "論理学者",
        "group": "分析家",
        "traits": ["考え込みやすい", "独自視点", "距離感に敏感"],
        "love": "好意が出るほど不器用になりやすい",
        "stress": "急かされると脳内で会話を閉じる",
        "line": "返信速度は波があるが、興味ある話は長文",
        "攻略": "結論を迫らず、話題の自由度を残すと近づく",
        "friend": "ひとり時間を守ってくれる相手と長続き",
    },
    "ENTJ": {
        "archetype": "指揮官",
        "group": "分析家",
        "traits": ["決断が速い", "目標志向", "頼られると燃える"],
        "love": "本命には未来の話をし始める",
        "stress": "段取りが崩れると圧が強くなる",
        "line": "返信が早く、要点もはっきり",
        "攻略": "尊敬できる部分を見せると一気に距離が縮む",
        "friend": "成長を応援し合える関係を好む",
    },
    "ENTP": {
        "archetype": "討論者",
        "group": "分析家",
        "traits": ["発想が軽やか", "ノリがいい", "飽きに敏感"],
        "love": "好きな相手には会話量が一気に増える",
        "stress": "制限が多いと急に別の遊びを探す",
        "line": "返信は自由だが、会話を転がすのは得意",
        "攻略": "会話のテンポと新鮮さを切らさないことが効く",
        "friend": "一緒にくだらない話で盛り上がれる人が好き",
    },
    "INFJ": {
        "archetype": "提唱者",
        "group": "外交官",
        "traits": ["空気を深く読む", "理想がある", "本音は少し遅れて出る"],
        "love": "心が通うと一気に特別扱いする",
        "stress": "無理して合わせ続けると突然消耗する",
        "line": "優しいが、距離を詰める相手には言葉が濃くなる",
        "攻略": "雑な扱いは即終了、丁寧さが最短ルート",
        "friend": "本音を安心して出せる関係が大事",
    },
    "INFP": {
        "archetype": "仲介者",
        "group": "外交官",
        "traits": ["共感力が高い", "世界観がある", "好き嫌いが静かに深い"],
        "love": "好きな人の前ほど挙動がふわつきがち",
        "stress": "価値観を否定されると一気に閉じる",
        "line": "返信はマイペースでも、気持ちは文に出やすい",
        "攻略": "安心感と否定しない姿勢がかなり効く",
        "friend": "感性を笑わない人と長く続く",
    },
    "ENFJ": {
        "archetype": "主人公",
        "group": "外交官",
        "traits": ["面倒見がいい", "人を前向きにする", "本命には尽くしがち"],
        "love": "好きになると相手の変化によく気づく",
        "stress": "気を遣いすぎて自分が後回しになる",
        "line": "返信は温度が高く、質問も自然に多い",
        "攻略": "感謝を言葉で返すと一気に信頼に変わる",
        "friend": "お互いをちゃんと気にかける関係を好む",
    },
    "ENFP": {
        "archetype": "運動家",
        "group": "外交官",
        "traits": ["テンションが明るい", "興味の幅が広い", "好きな人には分かりやすい"],
        "love": "本命には無邪気なのに独占欲が少し出る",
        "stress": "自由がないと急に元気がなくなる",
        "line": "返信の勢いで好意が出やすい",
        "攻略": "ノリだけでなく、本音を受け止めると刺さる",
        "friend": "感情も遊びも共有できる人が好き",
    },
    "ISTJ": {
        "archetype": "管理者",
        "group": "番人",
        "traits": ["安定感がある", "約束を守る", "慎重に距離を縮める"],
        "love": "好意は行動で静かに見せる",
        "stress": "予定が乱れると内心かなり疲れる",
        "line": "必要な返事はきっちり返す",
        "攻略": "誠実さと継続力が見える相手に弱い",
        "friend": "信頼を積める相手と長く付き合う",
    },
    "ISFJ": {
        "archetype": "擁護者",
        "group": "番人",
        "traits": ["気配りが細かい", "優しい", "本音は溜め込みやすい"],
        "love": "好きな人をつい世話したくなる",
        "stress": "我慢の限界まで周囲に合わせがち",
        "line": "返信は丁寧で、絵文字にも気持ちが出る",
        "攻略": "安心させる言葉と態度がかなり効く",
        "friend": "礼儀がある相手だと一気に打ち解ける",
    },
    "ESTJ": {
        "archetype": "幹部",
        "group": "番人",
        "traits": ["責任感が強い", "段取り上手", "分かりやすい努力を好む"],
        "love": "本命には時間をちゃんと割く",
        "stress": "だらだらした空気が続くと苛立ちやすい",
        "line": "返信は要点重視で速め",
        "攻略": "信頼できる人だと判断されると強い",
        "friend": "約束と礼儀を守れる関係が楽",
    },
    "ESFJ": {
        "archetype": "領事",
        "group": "番人",
        "traits": ["愛情表現が素直", "空気を和ませる", "人に尽くしやすい"],
        "love": "好きになるとかなり分かりやすい",
        "stress": "雑に扱われると笑顔のまま傷つく",
        "line": "返信に温かさがあり、会話を途切れさせない",
        "攻略": "ちゃんと反応を返すだけで信頼が積み上がる",
        "friend": "誘い合える関係が心地いい",
    },
    "ISTP": {
        "archetype": "巨匠",
        "group": "探検家",
        "traits": ["冷静", "実践派", "ベタベタしすぎると離れる"],
        "love": "好きでも言葉より行動で出る",
        "stress": "干渉が増えると距離を取りたくなる",
        "line": "返信は淡白でも、会うと優しいタイプ",
        "攻略": "詮索しすぎず、自然体でいるのが近道",
        "friend": "気楽で余白のある関係を好む",
    },
    "ISFP": {
        "archetype": "冒険家",
        "group": "探検家",
        "traits": ["感性がやわらかい", "優しい", "無理を見せない"],
        "love": "好きな人には自然と特別に優しくなる",
        "stress": "強い否定や圧に弱い",
        "line": "返信は控えめでも、気持ちは行動で出る",
        "攻略": "安心感とやさしいテンポがかなり大切",
        "friend": "感覚が合う相手と深くつながる",
    },
    "ESTP": {
        "archetype": "起業家",
        "group": "探検家",
        "traits": ["勢いがある", "行動が速い", "反応の良さで距離を縮める"],
        "love": "好きになると誘い方が分かりやすい",
        "stress": "退屈が続くと別の刺激を探す",
        "line": "返信はテンポ重視、会話を止めない",
        "攻略": "ノリの良さと芯の強さの両方が効く",
        "friend": "一緒に動ける相手だと盛り上がる",
    },
    "ESFP": {
        "archetype": "エンターテイナー",
        "group": "探検家",
        "traits": ["場を明るくする", "愛嬌がある", "好きな人には距離が近い"],
        "love": "本命には反応の濃さがかなり出る",
        "stress": "冷たい空気が続くとしんどくなる",
        "line": "返信は感情豊かで分かりやすい",
        "攻略": "楽しいだけでなく、ちゃんと向き合う姿勢が効く",
        "friend": "一緒に笑える相手が最高",
    },
}

CONTENT_FORMATS: list[dict[str, str]] = [
    {"key": "like_attitude", "name": "が好きな人に見せる態度", "theme": "恋愛"},
    {"key": "crush_actions", "name": "が脈ありの時にする行動", "theme": "恋愛"},
    {"key": "line_shift", "name": "のLINEが急に変わる瞬間", "theme": "恋愛"},
    {"key": "trust_sign", "name": "が本気で心を許したサイン", "theme": "人間関係"},
    {"key": "stress_signal", "name": "がしんどい時に出るサイン", "theme": "心理"},
    {"key": "攻略", "name": "の攻略で効く接し方", "theme": "攻略"},
    {"key": "friendship_shift", "name": "が仲良くなるほど出る素の反応", "theme": "人間関係"},
    {"key": "work_trust", "name": "の仕事で信頼される関わり方", "theme": "仕事"},
    {"key": "recharge_style", "name": "の回復が早い休み方", "theme": "自己理解"},
    {"key": "communication_style", "name": "と会話が噛み合う話し方", "theme": "コミュニケーション"},
]

MBTI_POST_ORDER: list[str] = [
    "INTJ",
    "INTP",
    "ENTJ",
    "ENTP",
    "INFJ",
    "INFP",
    "ENFJ",
    "ENFP",
    "ISTJ",
    "ISFJ",
    "ESTJ",
    "ESFJ",
    "ISTP",
    "ISFP",
    "ESTP",
    "ESFP",
]

@dataclass(frozen=True, slots=True)
class Palette:
    """One colourway.

    accent is the bright decorative colour; accent_deep is the one that can
    carry white text. They used to be the same value, which left the label
    pills at 1.57:1 for 探検家 and 2.00:1 for 番人 - effectively unreadable.
    """

    name: str
    background: str
    accent: str
    light: str
    accent_deep: str


# Six colourways per group. One is picked per topic, so all 16 types of a
# series stay on the same palette while different series differ.
GROUP_PALETTE_VARIANTS: dict[str, tuple[Palette, ...]] = {
    "分析家": (
        Palette("amethyst", "#45216b", "#8b4fd6", "#f3e8ff", "#5b2e8c"),
        Palette("plum", "#3b1a5c", "#7b3fc4", "#efe4ff", "#54258a"),
        Palette("indigo", "#2e2470", "#6d5ce0", "#ebe9ff", "#3f3496"),
        Palette("orchid", "#55205f", "#a749c9", "#fbe6ff", "#71308a"),
        Palette("nocturne", "#331a52", "#7a4fd0", "#ece3ff", "#4a2782"),
        Palette("iris", "#3d2b7a", "#7f6ae8", "#eeebff", "#4f3aa4"),
    ),
    "外交官": (
        Palette("emerald", "#184d3b", "#3fbf7f", "#e9fff2", "#1d6b4e"),
        Palette("jade", "#10453f", "#2fb39b", "#e4fff8", "#146258"),
        Palette("moss", "#1f4a2c", "#4cb96a", "#ebfced", "#2a6a3d"),
        Palette("lagoon", "#0f4448", "#2eb0ab", "#e3fdfb", "#136063"),
        Palette("fern", "#16402f", "#38a86e", "#e6fbee", "#1c5c43"),
        Palette("mint", "#1c5245", "#46c79c", "#eafff6", "#22705f"),
    ),
    "番人": (
        Palette("azure", "#0d4f6d", "#4fc3f7", "#e8f9ff", "#146287"),
        Palette("cobalt", "#12386b", "#4d8ef0", "#e8f0ff", "#1b4d92"),
        Palette("steel", "#1b4457", "#57a8c8", "#e9f8fd", "#245c75"),
        Palette("harbor", "#0a4258", "#3fb3d9", "#e4f8ff", "#0f5b78"),
        Palette("slate", "#233a5c", "#5f83cf", "#ebf0fc", "#2e4d7a"),
        Palette("glacier", "#155466", "#48bcd0", "#e6fbff", "#1a6d84"),
    ),
    # The old 探検家 background (#8a5b00) put its light panel at 5.41:1
    # against it, so these are darker.
    "探検家": (
        Palette("amber", "#6b4405", "#f6c945", "#fff6cf", "#8a5b0a"),
        Palette("copper", "#6a3410", "#e8934a", "#fff0e0", "#8a4a18"),
        Palette("brass", "#5a4409", "#dcbb46", "#fdf6da", "#77590f"),
        Palette("sunset", "#73301c", "#f08a55", "#ffeee4", "#943f26"),
        Palette("honey", "#63450c", "#eec14e", "#fff5da", "#835c14"),
        Palette("terracotta", "#6d2c1b", "#e07a52", "#ffece5", "#8c3a25"),
    ),
}

# Kept so anything still unpacking three hex strings keeps working.
GROUP_PALETTES: dict[str, tuple[str, str, str]] = {
    group: (variants[0].background, variants[0].accent, variants[0].light)
    for group, variants in GROUP_PALETTE_VARIANTS.items()
}
