from __future__ import annotations

import json
import hashlib
import re
from dataclasses import replace
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path

import requests

from mbti_tiktok_bot.catalog import CONTENT_FORMATS, MBTI_POST_ORDER, TYPE_DATA
from mbti_tiktok_bot.config import AppConfig
from mbti_tiktok_bot.models import ContentPackage, Scene

LEGACY_COPY_REWRITES = {
    "\u8ab0\u304b\u306b\u8a00\u3044\u305f\u304f\u306a\u308b\u7d50\u8ad6": "本命を見抜くポイント",
}

SERIES_TOTAL_POSTS = len(MBTI_POST_ORDER)
TOPIC_GENERATION_BLOCK_SIZE = max(len(CONTENT_FORMATS), 8)
TOPIC_SIMILARITY_BLOCK_THRESHOLD = 0.8
TOPIC_NAME_PATTERNS: dict[str, list[str]] = {
    "like_attitude": [
        "が本命にだけ見せる{aspect}",
        "が好きな相手ほど差が出る{aspect}",
        "が気になる人にだけ崩れる{aspect}",
        "が好意を隠せない{aspect}",
    ],
    "crush_actions": [
        "が脈ありだと変わる{aspect}",
        "が本命相手だけ差が出る{aspect}",
        "が好意を隠しきれない{aspect}",
        "が恋愛で急に変わる{aspect}",
    ],
    "line_shift": [
        "のLINEで本気度が出る{aspect}",
        "の返信で脈ありが漏れる{aspect}",
        "の連絡で温度差が出る{aspect}",
        "のメッセージで好意が見える{aspect}",
    ],
    "trust_sign": [
        "が心を許した相手にだけ見せる{aspect}",
        "が安心すると変わる{aspect}",
        "が信頼した相手ほど出る{aspect}",
        "が本音を出し始める{aspect}",
    ],
    "stress_signal": [
        "が限界前に見せる{aspect}",
        "がしんどい時ほど出る{aspect}",
        "が無理している時に出る{aspect}",
        "が余裕をなくすと漏れる{aspect}",
    ],
    "攻略": [
        "に刺さる{aspect}",
        "との距離が縮む{aspect}",
        "が安心する{aspect}",
        "に効く{aspect}",
    ],
    "friendship_shift": [
        "が仲良くなるほど出る{aspect}",
        "が気を許した相手にだけ見せる{aspect}",
        "が友達にだけ出す{aspect}",
        "が距離近めの相手に見せる{aspect}",
    ],
    "work_trust": [
        "の仕事で信頼される{aspect}",
        "が職場で評価されやすい{aspect}",
        "が一緒に働きやすい{aspect}",
        "の仕事で強みが出る{aspect}",
    ],
    "recharge_style": [
        "の回復が早い{aspect}",
        "が疲れを戻す{aspect}",
        "がひとり時間で整う{aspect}",
        "が消耗後に必要な{aspect}",
    ],
    "communication_style": [
        "と会話が噛み合う{aspect}",
        "が話しやすいと感じる{aspect}",
        "が理解しやすい{aspect}",
        "に伝わりやすい{aspect}",
    ],
}
TOPIC_ASPECTS: dict[str, list[str]] = {
    "like_attitude": [
        "優先順位の上げ方",
        "視線の固定",
        "会話の深め方",
        "誘いの具体性",
        "名前の呼び分け",
        "特別扱いの隠し方",
        "反応の温度差",
        "気遣いの細かさ",
        "会話の終わらせなさ",
        "照れ方",
    ],
    "crush_actions": [
        "連絡頻度",
        "予定の詰め方",
        "会う口実の作り方",
        "嫉妬のにじみ方",
        "質問の深さ",
        "優先順位の上げ方",
        "距離の詰め方",
        "好意の漏れ方",
        "反応速度",
        "行動の分かりやすさ",
    ],
    "line_shift": [
        "返信の温度感",
        "文量",
        "絵文字の使い分け",
        "話題の残し方",
        "質問の増え方",
        "既読後の動き",
        "会話のつなぎ方",
        "テンポ差",
        "気遣いの入れ方",
        "誘いへの持っていき方",
    ],
    "trust_sign": [
        "弱さの見せ方",
        "相談の深さ",
        "頼り方",
        "沈黙の空気",
        "本音の出し方",
        "素の表情",
        "甘え方",
        "距離感のゆるみ",
        "話す内容の深さ",
        "安心した時の反応",
    ],
    "stress_signal": [
        "口数の減り方",
        "返信の雑さ",
        "態度の静かさ",
        "ひとり時間の取り方",
        "表情の固さ",
        "余裕の消え方",
        "会話の切り方",
        "距離の取り方",
        "頼れなくなる瞬間",
        "無理の隠し方",
    ],
    "攻略": [
        "褒め方",
        "会話の入り方",
        "距離の縮め方",
        "誘い方",
        "安心させ方",
        "踏み込み方",
        "LINEの続け方",
        "信頼の積み方",
        "気持ちの伝え方",
        "空気の合わせ方",
    ],
    "friendship_shift": [
        "素の反応",
        "雑談のノリ",
        "頼り方",
        "距離感",
        "気遣いの抜き方",
        "会話の続け方",
        "本音の混ぜ方",
        "テンション差",
        "甘え方",
        "空気のゆるみ",
    ],
    "work_trust": [
        "任され方",
        "報連相",
        "段取り",
        "会議での立ち回り",
        "詰まった時の動き",
        "締切前の強さ",
        "改善の進め方",
        "役割分担",
        "準備の細かさ",
        "頼られ方",
    ],
    "recharge_style": [
        "休み方",
        "気分転換",
        "ひとり時間",
        "切り替え方",
        "頭の休ませ方",
        "人との距離",
        "回復ルーティン",
        "週末の使い方",
        "静けさの作り方",
        "回復サイン",
    ],
    "communication_style": [
        "話し方",
        "説明の順番",
        "質問の仕方",
        "リアクション",
        "相談の切り出し",
        "頼み方",
        "否定しない返し方",
        "テンポ",
        "情報量",
        "結論の置き方",
    ],
}
DEEP_TOPIC_NAME_PATTERNS: dict[str, list[str]] = {
    "like_attitude": [
        "が本命前で見せる{aspect}",
        "が好きな相手にだけ出す{aspect}",
    ],
    "crush_actions": [
        "が好意の手前で見せる{aspect}",
        "が脈ありなのに隠す{aspect}",
    ],
    "line_shift": [
        "のLINEに出る{aspect}",
        "の返信で分かる{aspect}",
    ],
    "trust_sign": [
        "が心を許す前に見せる{aspect}",
        "が信頼した相手に預ける{aspect}",
    ],
    "stress_signal": [
        "が限界前に見せる{aspect}",
        "がしんどい時に隠しきれない{aspect}",
    ],
    "攻略": [
        "に深く刺さる{aspect}",
        "との距離が縮む{aspect}",
    ],
    "friendship_shift": [
        "が距離を許す時に出る{aspect}",
        "が仲良くなる前に見せる{aspect}",
    ],
    "work_trust": [
        "の仕事で信頼が深まる{aspect}",
        "が職場で安心して動ける{aspect}",
    ],
    "recharge_style": [
        "の回復に必要な{aspect}",
        "が消耗後に戻る{aspect}",
    ],
    "communication_style": [
        "と本音で話すための{aspect}",
        "と会話が深まる{aspect}",
    ],
}
DEEP_TOPIC_ASPECTS: dict[str, list[str]] = {
    "like_attitude": [
        "距離を詰めたい時の葛藤",
        "特別扱いに出る防衛反応",
        "本命前で崩れる平常心",
        "好き避けの奥にある安心欲求",
    ],
    "crush_actions": [
        "近づきたいのに避ける瞬間",
        "好意を隠す時の防衛反応",
        "相手を試してしまう癖",
        "優先順位を上げるまでの迷い",
    ],
    "line_shift": [
        "踏み込みたい時の文面",
        "安心した相手への返信の素",
        "考えすぎた後の一言",
        "本音を隠す時の温度差",
    ],
    "trust_sign": [
        "弱さを預ける境界線",
        "本音を出す前の沈黙",
        "安心して崩れる瞬間",
        "頼りたい時の不器用さ",
    ],
    "stress_signal": [
        "防衛反応",
        "助けを求められない癖",
        "平気なふりの崩れ方",
        "心を閉じる前のサイン",
    ],
    "攻略": [
        "本音を引き出す聞き方",
        "警戒心をほどく距離感",
        "踏み込みすぎない深掘り",
        "安心して弱音を出せる返し方",
    ],
    "friendship_shift": [
        "素を見せる境界線",
        "気を許す前の試し行動",
        "離れたくない時の不器用さ",
        "本音が混じる雑談",
    ],
    "work_trust": [
        "抱え込みのほどき方",
        "任された時の安心条件",
        "詰まった時の相談の出し方",
        "責任を渡すまでの迷い",
    ],
    "recharge_style": [
        "心理的余白",
        "刺激を減らす休み方",
        "感情を戻す静けさ",
        "自分に戻るひとり時間",
    ],
    "communication_style": [
        "否定されない聞かれ方",
        "前提の置き方",
        "感情を急かさない聞き方",
        "本音が出る質問の深さ",
    ],
}
TOPIC_FOCUS_ALIASES: dict[str, dict[str, str]] = {
    "stress_signal": {
        "口数の変化": "口数の減り方",
        "話数の減り方": "口数の減り方",
    },
    "line_shift": {
        "返信の温度": "返信の温度感",
    },
}
DISCOVERY_HASHTAGS = ["#MBTI", "#mbti診断", "#16personalities"]
MBTI_HASHTAG_PLACEHOLDER = "#MBTI_TYPE"
TOPIC_HASHTAG_CANDIDATES: dict[str, list[str]] = {
    "like_attitude": ["#恋愛", "#好きな人", "#本命", "#脈あり", "#恋愛心理"],
    "crush_actions": ["#恋愛", "#脈あり", "#好きバレ", "#恋愛あるある", "#恋愛心理"],
    "line_shift": ["#恋愛", "#LINE", "#返信", "#脈あり", "#恋愛心理"],
    "trust_sign": ["#人間関係", "#本音", "#信頼", "#心理学", "#あるある"],
    "stress_signal": ["#心理", "#ストレス", "#メンタル", "#人間関係", "#あるある"],
    "攻略": ["#攻略", "#接し方", "#好かれる方法", "#人間関係", "#コミュニケーション"],
    "friendship_shift": ["#人間関係", "#友達", "#距離感", "#本音", "#あるある"],
    "work_trust": ["#仕事", "#職場", "#働き方", "#信頼関係", "#仕事術"],
    "recharge_style": ["#自己理解", "#セルフケア", "#休み方", "#メンタル", "#あるある"],
    "communication_style": ["#コミュニケーション", "#会話術", "#伝え方", "#人間関係", "#あるある"],
}
CAPTION_CTA_BY_BLUEPRINT = {
    "like_attitude": "気になる人の態度と重なるなら、あとで見返せるように保存しておくと便利です。",
    "crush_actions": "相手の行動と一致するものがあれば、コメントで答え合わせしてみてください。",
    "line_shift": "LINE の空気感は見返すと差が分かりやすいので、気になる相手がいる人ほど保存向きです。",
    "trust_sign": "信頼サインは静かに出るので、大切な相手を思い浮かべながら見ると違いが見えやすいです。",
    "stress_signal": "無理している時ほど小さな変化に出るので、自分や身近な人のチェック用にも残しておくのがおすすめです。",
    "攻略": "距離を縮めたい相手がいるなら、会話前に見返せるように保存しておくと使いやすいです。",
    "friendship_shift": "人間関係の距離感はあとで見返すと差が分かりやすいので、友達付き合いの整理用に保存向きです。",
    "work_trust": "職場での相性は毎回同じ所で差が出るので、一緒に働く相手を思い浮かべながら保存しておくと使いやすいです。",
    "recharge_style": "疲れ方と休み方の相性は忘れやすいので、自分の整え方メモとして保存しておくのがおすすめです。",
    "communication_style": "会話の噛み合わせは実戦で見返すほど効くので、話しにくい相手がいる時ほど保存向きです。",
}
MONETIZATION_QUALITY_GUIDANCE = (
    "収益化条件はフォロワー1万人以上、直近30日間の再生数10万回以上で、"
    "動画パフォーマンスに応じて報酬が発生する前提です。"
    "1万人超えを狙う運用として、量産感よりも保存したくなる具体性、"
    "冒頭で止まる強さ、誰かに送りたくなる解像度を優先してください。"
)
TOPIC_QUALITY_GUIDANCE = (
    "テーマ名は一目で何が分かるか伝わる具体性を持たせ、抽象語やふわっとした言い換えは避けてください。"
    "優先順位、温度差、距離感、返信内容、信頼サインのように観察できる差分を軸にしてください。"
)
DEEP_TOPIC_QUALITY_GUIDANCE = (
    "今回は表層のあるあるではなく、心理的な奥行きがあるディープなテーマを優先してください。"
    "行動の裏にある葛藤、防衛反応、安心条件、境界線、弱さの預け方、回復に必要な余白など、"
    "視聴者が自分や相手を深く理解できる観察軸にしてください。"
    "ただし病名・診断・決めつけには寄せず、日常で観察できる具体行動に落としてください。"
)
HOOK_COPY_BY_BLUEPRINT = {
    "like_attitude": "{mbti_type}の本命サイン、優しさより優先順位の差で見ると外しにくい",
    "crush_actions": "{mbti_type}の脈あり、会話より行動差で見た方がかなり早い",
    "line_shift": "{mbti_type}のLINE、本気だと返信速度より温度感が変わる",
    "trust_sign": "{mbti_type}が心を許した時、盛り上がりより安心感の出方で分かる",
    "stress_signal": "{mbti_type}がしんどい時、不機嫌になる前に静かな違和感が出る",
    "攻略": "{mbti_type}に刺さる接し方、距離を縮める人は安心感を外さない",
    "friendship_shift": "{mbti_type}が仲良くなる時、盛り上がりより素の反応の出方で分かる",
    "work_trust": "{mbti_type}が仕事で信頼する相手、成果より進め方の相性で決まりやすい",
    "recharge_style": "{mbti_type}の回復スイッチ、気合いより合う休み方で戻り方が変わる",
    "communication_style": "{mbti_type}と会話が噛み合う人、話す順番だけでかなり変わる",
}
CAPTION_SUMMARY_BY_BLUEPRINT = {
    "like_attitude": "今回のネタでは『{highlights}』を中心に、優しさと本命対応の違いが見分けやすい所だけを短くまとめました。",
    "crush_actions": "今回のネタでは『{highlights}』を中心に、社交辞令と脈ありを分けやすい行動差だけを短くまとめました。",
    "line_shift": "今回のネタでは『{highlights}』を中心に、返信速度ではなく温度差を見るポイントだけを短くまとめました。",
    "trust_sign": "今回のネタでは『{highlights}』を中心に、盛り上がりより安心感で分かる信頼サインだけを短くまとめました。",
    "stress_signal": "今回のネタでは『{highlights}』を中心に、大きな不機嫌になる前に出やすい静かな違和感だけを短くまとめました。",
    "攻略": "今回のネタでは『{highlights}』を中心に、距離を縮める人が外しにくい接し方だけを短くまとめました。",
    "friendship_shift": "今回のネタでは『{highlights}』を中心に、仲良くなった相手にだけ出やすい素の反応を短くまとめました。",
    "work_trust": "今回のネタでは『{highlights}』を中心に、職場で信頼を積みやすい進め方だけを短くまとめました。",
    "recharge_style": "今回のネタでは『{highlights}』を中心に、消耗した時に戻りやすい整え方だけを短くまとめました。",
    "communication_style": "今回のネタでは『{highlights}』を中心に、会話が噛み合いやすくなる伝え方だけを短くまとめました。",
}

TRUST_SIGN_SCENE_COPY: dict[str, list[tuple[str, str]]] = {
    "INTJ": [
        ("INTJが計画を外す時", "普段は先読みで守るのに、予定にない弱音や迷いを短く見せる。説明より本音が先に出たらかなり近い。"),
        ("静かな一途さが出る", "感情表現は大きくなくても、あなたのために時間や選択肢を調整する。優先順位の変化が信頼の形。"),
        ("任せる範囲が広がる", "自分で抱え込まず、判断材料や不安を共有する。結論前の考えを見せるなら心を開いている。"),
        ("雑な茶化しで閉じる", "本音を急にいじる、秘密を軽くする、矛盾だけ責める。この扱いをされると一気に防御が戻る。"),
        ("沈黙が共同作業になる", "無言でも気まずくなく、同じ方向を見て考えられる。安心して頭の中を見せられる相手はかなり特別。"),
    ],
    "INTP": [
        ("INTPが思考を渡す時", "完成した答えだけでなく、途中の仮説や迷走まで話す。脳内メモを見せるのはかなり深い信頼。"),
        ("返事の波を隠さない", "返信速度を取り繕うより、興味ある話を長く掘る。マイペースを許せる相手には素が出やすい。"),
        ("頼るより相談が増える", "結論を迫られない安心があると、小さな違和感まで共有する。相談の自由度が心の開き方。"),
        ("急かされると閉じる", "即答を求める、感情を決めつける、沈黙を責める。この3つで一気に距離を取る。"),
        ("くだらない脱線が合図", "真面目な話から急に変な例えへ飛ぶ。遠慮なく思考を遊ばせるなら、かなり安心している。"),
    ],
    "ENTJ": [
        ("ENTJが弱点を見せる時", "強く見せるだけをやめて、迷い・疲れ・失敗の原因まで共有する。改善前の本音を出すなら近い。"),
        ("未来の段取りに入れる", "予定や目標の話に自然とあなたが入る。時間を割く相手として扱うのが信頼の分かりやすい形。"),
        ("任せる判断が増える", "全部を主導せず、意見や役割を預ける。頼られるだけでなく頼る側に回れたら深い。"),
        ("無責任さで冷める", "約束を軽くする、努力を笑う、秘密を雑に扱う。信頼より管理モードが戻りやすい地雷。"),
        ("対等に戦略を話す", "成果だけでなく不安や狙いまで共有する。あなたと組む前提で考え始めたら本気で心を許している。"),
    ],
    "ENTP": [
        ("ENTPが退屈を脱ぐ時", "ふざけた会話の奥に、珍しく本音の理由を置く。笑いで逃げずに弱さを見せたらかなり近い。"),
        ("議論が遊びから本音へ", "ただ勝ちたい話ではなく、あなたの反応を見ながら深いテーマへ入る。知的な安心感が信頼の合図。"),
        ("自由な予定に誘う", "縛られるのは苦手でも、あなたとは次の面白い時間を作りたがる。共有したい発想が増える。"),
        ("退屈より否定で閉じる", "発想を雑に切る、好奇心を笑う、秘密をネタにする。軽さの裏の本気を踏むと一気に冷める。"),
        ("脱線を戻してくる", "話題が飛んでも、最後はあなたに戻ってくる。自由さの中に継続が見えたら信頼度は高め。"),
    ],
    "INFJ": [
        ("INFJが奥の本音を置く時", "優しい言葉の裏にある不安や理想まで少し話す。説明しすぎずに本音を預けるならかなり近い。"),
        ("沈黙の読み合いが楽になる", "空気を読みすぎる癖がゆるみ、黙っていても責任を感じすぎない。静かな安心が深いサイン。"),
        ("特別扱いが丁寧になる", "心が通う相手には言葉の濃さや気配りが変わる。大げさではなく、長く見てくれる。"),
        ("雑さで一気に遠のく", "善意を利用する、理想を笑う、秘密を軽く扱う。信じた分だけ静かに距離を戻しやすい。"),
        ("未来の願いを話す", "人に見せない願望や怖さを少し混ぜる。あなたの前で理想と弱さを同時に出せたら深い。"),
    ],
    "INFP": [
        ("INFPが世界観を渡す時", "好き嫌いや大事にしている価値観を、説明抜きでそっと見せる。笑われない安心がある証拠。"),
        ("感情の揺れを隠さない", "ふわっとした返事の奥に、本当は傷ついたことや嬉しかったことが出る。感情を預けるのが信頼。"),
        ("否定されない前提で甘える", "小さなお願いや弱音が増える。価値観を守ってくれる相手には、静かに距離が縮まる。"),
        ("価値観いじりで閉じる", "大切なものを軽く見る、急に正論で潰す、秘密を笑う。この扱いはかなり危険。"),
        ("素のやさしさが戻る", "気を遣った優しさではなく、自然に気持ちを分けてくれる。安心して感性を出せるなら本気のサイン。"),
    ],
    "ENFJ": [
        ("ENFJが頼らせ始める", "いつも支える側なのに、『実は少し疲れた』を置ける。相談を一方通行にしないならかなり近い。"),
        ("気配りが自然体になる", "良い人モードの笑顔より、肩の力が抜けた世話焼きが出る。沈黙を無理に埋めなくなる。"),
        ("感謝に素直に甘える", "助かったと言われるだけでなく、自分からも頼む。完璧な励まし役を降りられる相手は特別。"),
        ("当然扱いで閉じる", "頑張りを当たり前にする、弱音を茶化す、秘密を広げる。この3つで一気に距離が戻る。"),
        ("支える側から並ぶ側へ", "あなたの前でだけ弱音と希望を同じ温度で話すなら、本気で心を許しているサイン。"),
    ],
    "ENFP": [
        ("ENFPが静かに残る時", "明るく盛り上げるだけでなく、落ち着いた時間にもそばにいる。沈黙を怖がらないなら近い。"),
        ("感情の奥まで共有する", "楽しい話だけで終わらず、不安や寂しさも混ぜる。遊びと本音を同じ相手に渡すのが信頼。"),
        ("自由さの中に継続が出る", "気分屋に見えても、あなたとの約束や会話には戻ってくる。興味の矢印が続くなら強い。"),
        ("否定の連打でしぼむ", "ノリを雑に切る、本音を重いと扱う、秘密を軽くする。この扱いで一気に心が引きやすい。"),
        ("無邪気さが素に戻る", "盛り上げるためではなく、ただ一緒にいたくて笑う。自然体の明るさが出る相手はかなり特別。"),
    ],
    "ISTJ": [
        ("ISTJが予定外を話す時", "普段は整えてから話すのに、不安や迷いをぽつりと出す。未整理の本音を見せるなら近い。"),
        ("約束より気持ちを足す", "きっちり守るだけでなく、あなたの負担や安心まで気にする。継続した誠実さが信頼の形。"),
        ("小さく頼るようになる", "全部を自分で処理せず、確認や相談を挟む。慎重な人が助けを求めるのは深いサイン。"),
        ("雑な否定で扉が閉じる", "最初に否定する、約束を軽く見る、秘密を漏らす。積み上げた信頼ほど一瞬で戻りにくい。"),
        ("静かな安堵が続く", "盛り上がらなくても、同じペースでいられる。無理に明るくしなくていい空気が本気の合図。"),
    ],
    "ISFJ": [
        ("ISFJが本音を小出しにする", "我慢して合わせるだけをやめて、少し困った・少し嫌だったを言える。遠慮がほどけた証拠。"),
        ("気配りが義務から素へ", "世話を焼くより、安心して一緒に休める。優しさの奥にある疲れまで見せられたら近い。"),
        ("頼まれるだけで終わらない", "相手のために動く人が、自分の希望やお願いも出す。受け取ってもらえる前提が信頼。"),
        ("笑顔のまま傷つく地雷", "雑に扱う、感謝を省く、秘密を軽くする。表では平気そうでも内側で距離が空きやすい。"),
        ("安心の丁寧さが増える", "返信や気配りが穏やかに続く。頑張りすぎない優しさが出るなら、本気で心を許している。"),
    ],
    "ESTJ": [
        ("ESTJが段取りを預ける時", "責任を抱えるだけでなく、相談や役割を任せる。自分の弱い部分まで共有するなら近い。"),
        ("時間の使い方が変わる", "本当に信頼した相手には予定をちゃんと空ける。言葉より、具体的な時間配分に本気が出る。"),
        ("厳しさの奥を見せる", "正しさだけで押さず、なぜ大事にしたいかまで話す。価値観の理由を渡すのが信頼。"),
        ("無責任さで閉じる", "約束を破る、努力を茶化す、秘密を軽く扱う。安心より管理モードが強く戻りやすい。"),
        ("頼れる相手として並べる", "指示する側から、同じ目線で相談する側へ変わる。任せ方が増えたら深いサイン。"),
    ],
    "ESFJ": [
        ("ESFJが寂しさを言える時", "明るく合わせるだけでなく、実は寂しかった・気にしてたを出す。弱音を責めない相手には近い。"),
        ("誘いが義務から本音へ", "みんなのためではなく、あなたと過ごしたい気持ちが混ざる。温かい継続が信頼の形。"),
        ("気遣いの見返りを求めない", "反応を気にしすぎず自然に尽くす。安心できる相手には、世話焼きがやわらかくなる。"),
        ("反応の薄さで傷つく", "感謝を流す、気持ちを雑に扱う、秘密を笑い話にする。笑顔でも内心は閉じやすい。"),
        ("素直な愛情が戻る", "頑張って盛り上げるより、自然に名前を呼び、近況を気にする。温かさが続くなら本気のサイン。"),
    ],
    "ISTP": [
        ("ISTPが手を貸し続ける時", "言葉で盛らず、必要な時に動く。頼まれる前に小さく助けるなら、かなり心を許している。"),
        ("余白を共有できる", "ベタベタしなくても同じ場所にいられる。沈黙や別行動を許せる相手には素が出やすい。"),
        ("弱音を短く置く", "長く説明しなくても、疲れた・面倒だったを一言だけ出す。受け流されない安心がある証拠。"),
        ("干渉されると離れる", "詮索しすぎる、行動を縛る、秘密を軽くする。この扱いで一気に距離を取りたくなる。"),
        ("行動の継続が合図", "派手な言葉より、会う・手伝う・戻ってくるが続く。自然にそばへ来るなら深い信頼。"),
    ],
    "ISFP": [
        ("ISFPが感覚を預ける時", "好きなものや嫌だったことを、説明しすぎず見せる。否定されない安心がある相手には近い。"),
        ("優しさが義務から素へ", "気を遣う優しさではなく、自然に隣へいる感じが増える。無理のない温度が信頼の形。"),
        ("無理を見せられる", "平気なふりをやめて、疲れた・今日は静かでいたいを言える。弱さを置けるならかなり深い。"),
        ("強い圧で閉じる", "決めつける、急かす、感性を笑う。穏やかに見えても内側では一気に距離が空きやすい。"),
        ("小さな特別扱いが続く", "派手ではなく、好きなものを覚えている・そっと気遣うが増える。自然な優しさが本気の合図。"),
    ],
    "ESTP": [
        ("ESTPが勢いを落とす時", "楽しいノリだけでなく、少し真面目な悩みも置く。走りながら本音を見せる相手はかなり特別。"),
        ("行動の予定に入れる", "思いつきの誘いだけでなく、あなたと動く前提が増える。会う流れを作るのが信頼の形。"),
        ("弱さを笑いで逃がさない", "茶化して終わらせず、実は気にしていたことを短く話す。反応を信じている証拠。"),
        ("冷たい空気で離れる", "反応を無視する、挑戦を笑う、秘密をネタにする。楽しさより安全が消えると一気に引く。"),
        ("戻ってくる頻度が合図", "刺激を探すタイプでも、最後にあなたへ戻る。行動の継続が見えたら本気で心を許している。"),
    ],
    "ESFP": [
        ("ESFPが静かな顔を見せる時", "明るい反応だけでなく、疲れた時の素の表情を隠さない。盛り上げなくていい相手は特別。"),
        ("楽しさに本音が混ざる", "笑いながらも、寂しさや不安を少し話す。感情豊かな人が弱さも出すならかなり近い。"),
        ("距離の近さが自然になる", "大げさなサービスではなく、隣にいるのが普通になる。反応の濃さより安心感が続く。"),
        ("冷たさで一気にしぼむ", "無視する、テンションを否定する、秘密を軽く扱う。この扱いで笑顔の奥が閉じやすい。"),
        ("素の明るさが戻る", "気を引くためではなく、一緒に笑いたくて近づく。自然な楽しさが続くなら深い信頼のサイン。"),
    ],
}


def _topic_theme(topic: dict[str, str]) -> str:
    return str(topic.get("theme") or "").strip()


def _uses_deep_topics(topic_depth: str | None) -> bool:
    normalized_depth = str(topic_depth or "deep").strip().lower()
    return normalized_depth not in {"standard", "normal", "basic", "light"}


def _topic_quality_guidance(config: AppConfig) -> str:
    guidance = TOPIC_QUALITY_GUIDANCE
    if _uses_deep_topics(config.topic_depth):
        guidance += DEEP_TOPIC_QUALITY_GUIDANCE
    return guidance


def _topic_patterns_for_blueprint(blueprint: str, topic_depth: str | None) -> list[str]:
    patterns = TOPIC_NAME_PATTERNS[blueprint]
    if _uses_deep_topics(topic_depth):
        return DEEP_TOPIC_NAME_PATTERNS.get(blueprint, []) + patterns
    return patterns


def _topic_aspects_for_blueprint(blueprint: str, topic_depth: str | None) -> list[str]:
    aspects = TOPIC_ASPECTS[blueprint]
    if _uses_deep_topics(topic_depth):
        return DEEP_TOPIC_ASPECTS.get(blueprint, []) + aspects
    return aspects


def _all_topic_aspects(blueprint: str) -> list[str]:
    return DEEP_TOPIC_ASPECTS.get(blueprint, []) + TOPIC_ASPECTS.get(blueprint, [])


def _balance_topics_by_theme(topics: list[dict[str, str]], previous_theme: str | None = None) -> list[dict[str, str]]:
    buckets: dict[str, list[dict[str, str]]] = {}
    first_seen: dict[str, int] = {}
    for index, topic in enumerate(topics):
        theme = _topic_theme(topic)
        buckets.setdefault(theme, []).append(dict(topic))
        first_seen.setdefault(theme, index)

    ordered: list[dict[str, str]] = []
    last_theme = previous_theme
    while True:
        available_themes = [theme for theme, items in buckets.items() if items]
        if not available_themes:
            return ordered
        candidate_count = len(available_themes)
        available_themes.sort(
            key=lambda theme: (
                1 if last_theme and theme == last_theme and candidate_count > 1 else 0,
                -len(buckets[theme]),
                first_seen[theme],
            )
        )
        chosen_theme = available_themes[0]
        ordered.append(buckets[chosen_theme].pop(0))
        last_theme = chosen_theme


def _started_topic_count(next_post_index: int) -> int:
    completed_cycles, cycle_offset = divmod(next_post_index, SERIES_TOTAL_POSTS)
    return completed_cycles + (1 if cycle_offset else 0)


def _topic_block_lengths(history_length: int) -> list[int]:
    if history_length <= 0:
        return []

    lengths = [min(len(BASE_TOPICS), history_length)]
    remaining = history_length - lengths[0]
    while remaining > 0:
        block_length = min(TOPIC_GENERATION_BLOCK_SIZE, remaining)
        lengths.append(block_length)
        remaining -= block_length
    return lengths


def _rebalance_topic_history(history: list[dict[str, str]], next_post_index: int) -> list[dict[str, str]]:
    preserve_count = min(_started_topic_count(next_post_index), len(history))
    if preserve_count >= len(history):
        return history

    balanced_history: list[dict[str, str]] = []
    previous_theme: str | None = None
    remaining_preserve = preserve_count
    cursor = 0

    for block_length in _topic_block_lengths(len(history)):
        block = history[cursor : cursor + block_length]
        preserve_in_block = min(remaining_preserve, block_length)
        if preserve_in_block:
            balanced_history.extend(block[:preserve_in_block])
            previous_theme = _topic_theme(balanced_history[-1])
        if preserve_in_block < block_length:
            balanced_block = _balance_topics_by_theme(block[preserve_in_block:], previous_theme=previous_theme)
            balanced_history.extend(balanced_block)
            previous_theme = _topic_theme(balanced_history[-1])
        cursor += block_length
        remaining_preserve -= preserve_in_block

    return balanced_history


def _base_topics() -> list[dict[str, str]]:
    return _balance_topics_by_theme(
        [
            {
                "key": str(item["key"]),
                "name": str(item["name"]),
                "theme": str(item["theme"]),
                "blueprint": str(item["key"]),
                "source": "seed",
            }
            for item in CONTENT_FORMATS
        ]
    )


BASE_TOPICS = _base_topics()
BASE_TOPIC_BY_NAME = {item["name"]: item for item in BASE_TOPICS}
BASE_THEME_BY_BLUEPRINT = {item["blueprint"]: item["theme"] for item in BASE_TOPICS}


def _state_path(config: AppConfig) -> Path:
    return config.state_dir / "series_state.json"


def _valid_format_names() -> list[str]:
    return [item["name"] for item in CONTENT_FORMATS]


def _topic_signature(topic_name: str) -> str:
    return re.sub(r"\W+", "", topic_name.casefold())


def _similarity_text(text: str) -> str:
    return re.sub(r"\s+", "", text.casefold())


def _text_similarity(left: str, right: str) -> float:
    normalized_left = _similarity_text(left)
    normalized_right = _similarity_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    return SequenceMatcher(None, normalized_left, normalized_right).ratio()


def _is_too_similar_to_existing_topic(topic_name: str, existing_names: list[str]) -> bool:
    return any(
        _text_similarity(topic_name, existing_name) >= TOPIC_SIMILARITY_BLOCK_THRESHOLD
        for existing_name in existing_names
    )


def _generated_topic_key(topic_name: str) -> str:
    return "generated_" + hashlib.sha1(topic_name.encode("utf-8")).hexdigest()[:12]


def _normalize_topic_record(raw_topic: object) -> dict[str, str] | None:
    if isinstance(raw_topic, str):
        base_topic = BASE_TOPIC_BY_NAME.get(raw_topic)
        return dict(base_topic) if base_topic else None
    if not isinstance(raw_topic, dict):
        return None
    topic_name = str(raw_topic.get("name") or "").strip()
    if not topic_name:
        return None
    base_topic = BASE_TOPIC_BY_NAME.get(topic_name)
    if base_topic is not None:
        return dict(base_topic)
    blueprint = str(raw_topic.get("blueprint") or raw_topic.get("key") or "").strip()
    if blueprint not in BASE_THEME_BY_BLUEPRINT:
        return None
    return {
        "key": str(raw_topic.get("key") or _generated_topic_key(topic_name)),
        "name": topic_name,
        "theme": str(raw_topic.get("theme") or BASE_THEME_BY_BLUEPRINT[blueprint]),
        "blueprint": blueprint,
        "source": str(raw_topic.get("source") or "generated"),
    }


def _bootstrap_topic_history(next_post_index: int, topic_depth: str | None = "deep") -> list[dict[str, str]]:
    used_cycle_count = (next_post_index // SERIES_TOTAL_POSTS) + 1 if next_post_index > 0 else 0
    history: list[dict[str, str]] = []
    used_signatures: set[str] = set()
    for base_topic in BASE_TOPICS:
        if len(history) >= used_cycle_count:
            break
        history.append(dict(base_topic))
        used_signatures.add(_topic_signature(base_topic["name"]))
    if len(history) < used_cycle_count:
        history.extend(
            _procedural_topic_records(
                used_cycle_count - len(history),
                used_signatures,
                previous_theme=_topic_theme(history[-1]) if history else None,
                used_topic_names=[topic["name"] for topic in history],
                topic_depth=topic_depth,
            )
        )
    return history


def _normalize_topic_history(raw_history: object, next_post_index: int, topic_depth: str | None = "deep") -> list[dict[str, str]]:
    if not isinstance(raw_history, list):
        return _bootstrap_topic_history(next_post_index, topic_depth)
    normalized = [topic for item in raw_history if (topic := _normalize_topic_record(item)) is not None]
    if normalized:
        return _rebalance_topic_history(normalized, next_post_index)
    return _bootstrap_topic_history(next_post_index, topic_depth)


def _history_signatures(history: list[dict[str, str]]) -> set[str]:
    return {_topic_signature(topic["name"]) for topic in history}


def _resolve_topic_from_state(config: AppConfig, format_name: str) -> dict[str, str] | None:
    base_topic = BASE_TOPIC_BY_NAME.get(format_name)
    if base_topic is not None:
        return dict(base_topic)
    state = load_series_state(config)
    for topic in state.get("topic_history", []):
        normalized = _normalize_topic_record(topic)
        if normalized and normalized["name"] == format_name:
            return normalized
    return None


def load_series_state(config: AppConfig) -> dict[str, object]:
    state_path = _state_path(config)
    if not state_path.exists():
        return {"next_post_index": 0, "topic_history": []}
    data = json.loads(state_path.read_text(encoding="utf-8"))
    next_post_index = int(data.get("next_post_index", 0))
    topic_history = _normalize_topic_history(data.get("topic_history", []), next_post_index, config.topic_depth)
    return {"next_post_index": next_post_index, "topic_history": topic_history}


def save_series_state(config: AppConfig, next_post_index: int, topic_history: list[dict[str, str]] | None = None) -> Path:
    state_path = _state_path(config)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    current_topic_history = topic_history
    if current_topic_history is None:
        current_topic_history = load_series_state(config).get("topic_history", [])
    state_path.write_text(
        json.dumps(
            {
                "next_post_index": next_post_index,
                "topic_history": current_topic_history,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return state_path


def advance_series_state(config: AppConfig, posted_count: int) -> int:
    state = load_series_state(config)
    current = int(state["next_post_index"])
    next_post_index = current + posted_count
    save_series_state(config, next_post_index, list(state.get("topic_history", [])))
    return next_post_index


def _choose_type(target_date: date) -> str:
    return MBTI_POST_ORDER[target_date.toordinal() % len(MBTI_POST_ORDER)]


def _choose_format(target_date: date) -> dict[str, str]:
    return dict(BASE_TOPICS[target_date.toordinal() % len(BASE_TOPICS)])


def _topic_for_post_index(post_index: int) -> dict[str, str]:
    base_topic = BASE_TOPICS[(post_index // SERIES_TOTAL_POSTS) % len(BASE_TOPICS)]
    return dict(base_topic)


def _procedural_topic_records(
    count: int,
    used_signatures: set[str],
    previous_theme: str | None = None,
    used_topic_names: list[str] | None = None,
    topic_depth: str | None = "deep",
) -> list[dict[str, str]]:
    generated: list[dict[str, str]] = []
    existing_names = list(used_topic_names or [])
    blueprint_order = [topic["blueprint"] for topic in BASE_TOPICS]
    candidates_by_blueprint: dict[str, list[str]] = {}
    for blueprint in blueprint_order:
        topic_names: list[str] = []
        for pattern in _topic_patterns_for_blueprint(blueprint, topic_depth):
            for aspect in _topic_aspects_for_blueprint(blueprint, topic_depth):
                topic_names.append(pattern.format(aspect=aspect))
        candidates_by_blueprint[blueprint] = topic_names

    max_candidate_count = max(len(topic_names) for topic_names in candidates_by_blueprint.values())
    for candidate_index in range(max_candidate_count):
        for blueprint in blueprint_order:
            topic_names = candidates_by_blueprint[blueprint]
            if candidate_index >= len(topic_names):
                continue
            topic_name = topic_names[candidate_index]
            signature = _topic_signature(topic_name)
            if signature in used_signatures or _is_too_similar_to_existing_topic(topic_name, existing_names):
                continue
            used_signatures.add(signature)
            existing_names.append(topic_name)
            generated.append(
                {
                    "key": _generated_topic_key(topic_name),
                    "name": topic_name,
                    "theme": BASE_THEME_BY_BLUEPRINT[blueprint],
                    "blueprint": blueprint,
                    "source": "procedural",
                }
            )
            if len(generated) >= count:
                return _balance_topics_by_theme(generated, previous_theme=previous_theme)
    return _balance_topics_by_theme(generated, previous_theme=previous_theme)


def _extract_json_object(raw_text: str) -> dict[str, object] | None:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    try:
        return json.loads(raw_text[start : end + 1])
    except Exception:
        return None


def _chat_completion_fallback_payload(request_payload: dict[str, object], response: requests.Response) -> dict[str, object] | None:
    try:
        error_payload = response.json().get("error", {})
    except Exception:
        error_payload = {}

    param = str(error_payload.get("param") or "")
    message = str(error_payload.get("message") or "").lower()

    if "temperature" in request_payload and (param == "temperature" or "temperature" in message):
        fallback_payload = dict(request_payload)
        fallback_payload.pop("temperature", None)
        return fallback_payload

    if "response_format" in request_payload and (param == "response_format" or "response_format" in message):
        fallback_payload = dict(request_payload)
        fallback_payload.pop("response_format", None)
        return fallback_payload

    return None


def _prepare_chat_completion_payload(config: AppConfig, request_payload: dict[str, object]) -> dict[str, object]:
    prepared_payload = dict(request_payload)
    model_name = config.openai_model.strip().lower()

    if model_name.startswith("gpt-5") and prepared_payload.get("temperature") not in (None, 1, 1.0):
        prepared_payload.pop("temperature", None)

    return prepared_payload


def _post_chat_completion(config: AppConfig, request_payload: dict[str, object]) -> requests.Response:
    current_payload = _prepare_chat_completion_payload(config, request_payload)

    for _ in range(3):
        response = requests.post(
            f"{config.openai_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=current_payload,
            timeout=60,
        )
        if response.status_code != 400:
            return response

        fallback_payload = _chat_completion_fallback_payload(current_payload, response)
        if fallback_payload is None or fallback_payload == current_payload:
            return response
        current_payload = fallback_payload

    return response


def _generate_topics_with_llm(config: AppConfig, history: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    if not config.openai_api_key:
        return []
    known_names = [topic["name"] for topic in history][-120:]
    recent_themes = [_topic_theme(topic) for topic in history][-12:]
    request_payload = {
        "model": config.openai_model,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "あなたは MBTI の TikTok 企画編集者です。"
                    + MONETIZATION_QUALITY_GUIDANCE
                    + _topic_quality_guidance(config)
                    +
                    "各テーマは 16 タイプ全員に横展開できる必要があります。"
                    "既存テーマと重複しない、短くて分かりやすい日本語のテーマ名だけを返してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "次の条件で新しいテーマを "
                    f"{count} 個作ってください。"
                    "各テーマは JSON の topics 配列に入れ、"
                    "name, theme, blueprint を返してください。"
                    "テーマ名は見た瞬間に内容が伝わり、保存候補になる具体性を持たせてください。"
                    "抽象語、説明不足、広すぎる概念は避け、1テーマにつき1つの観察軸に絞ってください。"
                    "blueprint は like_attitude, crush_actions, line_shift, trust_sign, stress_signal, 攻略, friendship_shift, work_trust, recharge_style, communication_style のいずれか。"
                    "name は MBTI 名を前につけた時に自然な日本語にしてください。"
                    "恋愛だけに偏らせず、人間関係・心理・攻略・仕事・自己理解・コミュニケーションも混ぜてください。"
                    "返す topics では、可能なら恋愛テーマを全体の3分の1以下にして、同じ theme が連続しない順にしてください。"
                    "既存テーマと意味も文面もかぶらないようにしてください。"
                    f"最近のテーマ: {json.dumps(recent_themes, ensure_ascii=False)}"
                    f"既存テーマ: {json.dumps(known_names, ensure_ascii=False)}"
                ),
            },
        ],
        "temperature": 1.0,
    }
    try:
        response = _post_chat_completion(config, request_payload)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        payload = _extract_json_object(content or "") or {}
    except Exception:
        return []

    topics: list[dict[str, str]] = []
    used_signatures = _history_signatures(history)
    used_topic_names = [topic["name"] for topic in history]
    for raw_topic in payload.get("topics", []):
        normalized = _normalize_topic_record(raw_topic)
        if normalized is None:
            continue
        signature = _topic_signature(normalized["name"])
        if signature in used_signatures or _is_too_similar_to_existing_topic(normalized["name"], used_topic_names):
            continue
        used_signatures.add(signature)
        used_topic_names.append(normalized["name"])
        normalized["source"] = "llm"
        if normalized["key"] in BASE_THEME_BY_BLUEPRINT:
            normalized["key"] = _generated_topic_key(normalized["name"])
        topics.append(normalized)
        if len(topics) >= count:
            break
    return _balance_topics_by_theme(topics, previous_theme=_topic_theme(history[-1]) if history else None)


def _expand_topic_history(config: AppConfig, history: list[dict[str, str]], minimum_length: int) -> list[dict[str, str]]:
    expanded = list(history)
    used_signatures = _history_signatures(expanded)

    while len(expanded) < minimum_length and len(expanded) < len(BASE_TOPICS):
        candidate = dict(BASE_TOPICS[len(expanded)])
        signature = _topic_signature(candidate["name"])
        if signature in used_signatures:
            break
        expanded.append(candidate)
        used_signatures.add(signature)

    while len(expanded) < minimum_length:
        generated_topics = _generate_topics_with_llm(config, expanded, TOPIC_GENERATION_BLOCK_SIZE)
        if not generated_topics:
            generated_topics = _procedural_topic_records(
                TOPIC_GENERATION_BLOCK_SIZE,
                used_signatures,
                previous_theme=_topic_theme(expanded[-1]) if expanded else None,
                used_topic_names=[topic["name"] for topic in expanded],
                topic_depth=config.topic_depth,
            )
        if not generated_topics:
            raise RuntimeError("No additional topics could be generated")
        expanded.extend(generated_topics)
        used_signatures = _history_signatures(expanded)
    return expanded


def _ensure_topic_history(config: AppConfig, cycle_index: int) -> list[str]:
    state = load_series_state(config)
    history = list(state.get("topic_history", []))
    if not history and cycle_index >= 0:
        history = _bootstrap_topic_history(int(state["next_post_index"]))

    history = _expand_topic_history(config, history, cycle_index + 1)

    if history != state.get("topic_history", []):
        save_series_state(config, int(state["next_post_index"]), history)
    return history


def topic_for_post_index(config: AppConfig, post_index: int) -> dict[str, str]:
    cycle_index = post_index // SERIES_TOTAL_POSTS
    history = _ensure_topic_history(config, cycle_index)
    return dict(history[cycle_index])


def _topic_by_name(config: AppConfig, format_name: str) -> dict[str, str]:
    topic = _resolve_topic_from_state(config, format_name)
    if topic is None:
        raise ValueError(f"Unsupported format: {format_name}")
    return topic


def _behavior_summary(mbti_type: str, details: dict[str, object]) -> str:
    traits = [str(item) for item in details["traits"]]
    return f"普段の {traits[0]} 空気のまま、近い相手にだけ {traits[-1]} 一面が混ざりやすい"


def _hook_for_topic(topic_key: str, mbti_type: str) -> str:
    return HOOK_COPY_BY_BLUEPRINT[topic_key].format(mbti_type=mbti_type)


def _build_trust_sign_scenes(mbti_type: str) -> list[Scene]:
    scene_copy = TRUST_SIGN_SCENE_COPY[mbti_type]
    return [Scene(title, body) for title, body in scene_copy]


def _build_narration(title: str, hook: str, scenes: list[Scene]) -> str:
    return "。".join(
        [title, hook] + [f"{scene.title}。{scene.body.replace(chr(10), '。')}" for scene in scenes]
    )


def _topic_focus(topic: dict[str, str]) -> str:
    topic_key = str(topic.get("blueprint") or topic.get("key") or "")
    topic_name = str(topic.get("name") or "")
    for aspect in _all_topic_aspects(topic_key):
        if aspect in topic_name:
            return aspect
    for cue, focus in TOPIC_FOCUS_ALIASES.get(topic_key, {}).items():
        if cue in topic_name:
            return focus
    return ""


def _build_focus_scenes(
    mbti_type: str,
    topic_key: str,
    focus: str,
    *,
    archetype: str,
    love: str,
    stress: str,
    line_style: str,
    strategy: str,
    friend: str,
    traits: str,
) -> list[Scene]:
    if topic_key == "stress_signal" and "口数" in focus:
        return [
            Scene("返事が短くなる瞬間", f"{stress}。普段なら場を温める{mbti_type}ほど、限界前は相づちだけで済ませがち。"),
            Scene("まだ笑っている段階", "表情は保っていても、自分から話題を足さない／質問が減る／語尾だけ柔らかいなら早めのサイン。"),
            Scene("声をかけるなら", "『話したくなったら聞くよ』くらいがちょうどいい。詰めるより、逃げ場を残す方が戻りやすい。"),
            Scene("やると逆に閉じる事", "原因を即特定しようとする、明るさを求める、みんなの前で確認する。この3つは口数をさらに減らしやすい。"),
            Scene("見るべきポイント", f"{mbti_type}の{focus}は、怒りより先に出る小さなSOS。普段の会話量との差で見ると気づきやすい。"),
        ]

    focus_builders: dict[str, list[Scene]] = {
        "like_attitude": [
            Scene(f"{focus}が出る瞬間", f"{love}。特に{focus}は、他の人と扱いを分ける時に出やすい。"),
            Scene("普段との違い", f"{line_style}。言葉より、時間や反応の置き方に{focus}がにじむ。"),
            Scene("見逃しやすい差", f"{friend}。距離の詰め方が静かでも、小さな優先でかなり本気が見える。"),
            Scene("勘違いしやすい所", f"{archetype}らしく自然に見せるので、派手なアピールだけで判断すると外しやすい。"),
            Scene("本命判定のコツ", f"{mbti_type}は好きな相手ほど、{focus}を一回ではなく何度も積み重ねやすい。"),
        ],
        "crush_actions": [
            Scene(f"{focus}が変わる入口", f"脈ありだと {line_style}。最初に変わるのは距離感より{focus}の出方。"),
            Scene("本命だけに出る濃さ", f"{love}。会話や予定の中で、相手に合わせる具体性が増えやすい。"),
            Scene("見るべき行動", f"{friend}。軽いノリに見えても、続ける・合わせる・戻ってくるならかなり強い。"),
            Scene("誤読しやすい所", "一回の勢いだけで決めると外しやすい。何度も同じ方向に変わるかを見るのが大事。"),
            Scene("脈あり判定の軸", f"{mbti_type}の{focus}は、言葉の甘さより優先順位の動きで見ると分かりやすい。"),
        ],
        "line_shift": [
            Scene(f"{focus}に出る本音", f"{line_style}。本気度は返信速度より、{focus}の変わり方に出やすい。"),
            Scene("普段との差", "雑談を残す、確認が増える、次の会話に続く一言が入るなら温度が上がっているサイン。"),
            Scene("見落としやすい所", f"{strategy}。押すよりテンポを合わせた方が、相手の本音が出やすい。"),
            Scene("逆に外しやすい見方", "長文か短文かだけで判断しないこと。内容の濃さと戻ってくる頻度をセットで見る。"),
            Scene("LINE判定のコツ", f"{mbti_type}は{focus}に気持ちが乗ると、会話を終わらせない工夫が増えやすい。"),
        ],
        "trust_sign": [
            Scene(f"{focus}が見える時", f"{friend}。信頼した相手には、普段隠す部分が{focus}として出やすい。"),
            Scene("安心している証拠", f"{traits}。強く見せるより、少し力を抜いた反応が増えるならかなり近い。"),
            Scene("受け止め方", "大げさに拾わず、否定せず、同じ温度で聞く。ここで安心できると一気に信頼が深まる。"),
            Scene("壊しやすい対応", "茶化す、正論で直す、すぐ周りに話す。この3つは本音をしまわせやすい。"),
            Scene("信頼判定のコツ", f"{mbti_type}の{focus}は、弱さではなく安心のサインとして見ると分かりやすい。"),
        ],
        "stress_signal": [
            Scene(f"{focus}の出始め", f"{stress}。余裕が減ると、まず普段と違う{focus}として出やすい。"),
            Scene("普段との差", f"{traits}。いつもの強みと逆方向の反応が出たら、疲れが溜まっているサイン。"),
            Scene("周りができる事", "急かさず、理由を決めつけず、選択肢を少なくする。小さく整える方が戻りやすい。"),
            Scene("逆効果の対応", "感情を決めつける、正論で押す、すぐ答えを求めると負荷が増えやすい。"),
            Scene("不調判定のコツ", f"{mbti_type}の{focus}は、大きな不機嫌より先に出るので早めに拾うのが大事。"),
        ],
        "攻略": [
            Scene(f"{focus}で刺さる入口", f"{strategy}。相手のテンポを崩さずに{focus}を出せるとかなり効く。"),
            Scene("会話で効く所", f"{archetype}らしさを理解して、雑にいじらず具体的に返すと距離が縮みやすい。"),
            Scene("好印象になる動き", f"{friend}。距離感を尊重できると、押しつけ感がなく自然に近づける。"),
            Scene("やりがちな地雷", "駆け引きだけで揺さぶる、分かったふりをする、圧で詰めるのは逆効果。"),
            Scene("距離が縮む決め手", f"{mbti_type}には、派手な演出より相手に合う{focus}の方が残りやすい。"),
        ],
        "friendship_shift": [
            Scene(f"{focus}が増える合図", f"{friend}。仲良くなるほど、礼儀より自然な{focus}が出やすい。"),
            Scene("会話で見える変化", f"{traits}。雑談の軽さやツッコミの距離に素が混ざるとかなり近い。"),
            Scene("頼り方の差", "小さく相談する、任せる、沈黙でも気まずくない。このどれかが増えると距離が近い。"),
            Scene("誤解しやすい所", f"{archetype}らしく淡く見えても、近い相手には反応の差が出やすい。"),
            Scene("仲良し判定の軸", f"{mbti_type}は盛り上がりより、{focus}が自然に出るかで距離が見えやすい。"),
        ],
        "work_trust": [
            Scene(f"{focus}で信頼される理由", f"{traits}。職場ではこの強みが、{focus}の安定感に出やすい。"),
            Scene("任されやすい場面", f"{strategy}。詰まった時の進め方で、信頼の差がかなり出る。"),
            Scene("一緒に働きやすい所", f"{friend}。仕事でも距離感の取り方が合うと、かなり組みやすい。"),
            Scene("信頼を削る対応", "意図のない丸投げ、曖昧な指示、雑なフィードバックは相性を落としやすい。"),
            Scene("信頼を積むコツ", f"{mbti_type}には、能力だけでなく{focus}の任せ方まで整えると長く信頼されやすい。"),
        ],
        "recharge_style": [
            Scene(f"{focus}が必要なサイン", f"{stress}。この変化が出たら、{focus}を見直す合図になりやすい。"),
            Scene("回復しやすい時間", f"{friend}。人との距離感を整えるだけで、戻り方がかなり変わりやすい。"),
            Scene("休み方の相性", f"{traits}。刺激を足すより、今の負荷を減らす方が回復しやすい。"),
            Scene("消耗しやすい休み方", "予定を詰める、気を遣う場を増やす、無理に切り替えると回復が遅れやすい。"),
            Scene("整え方のコツ", f"{mbti_type}は気合いより、合う{focus}を先に決める方が立て直しやすい。"),
        ],
        "communication_style": [
            Scene(f"{focus}で噛み合う入口", f"{line_style}。最初の一往復で{focus}が合うと、会話が進みやすい。"),
            Scene("伝わりやすい順番", f"{strategy}。情報の順番や温度感が合うと、かなり理解されやすい。"),
            Scene("安心する会話", f"{friend}。無理に盛り上げるより、相手のリズムを崩さない方が刺さりやすい。"),
            Scene("ズレやすい所", "結論だけ急ぐ、感情だけ押す、前提を飛ばすと噛み合いにくい。"),
            Scene("会話を安定させるコツ", f"{mbti_type}とは、何を先に話すかと{focus}を合わせると自然に続きやすい。"),
        ],
    }
    return focus_builders.get(topic_key, [])


def _build_scenes(mbti_type: str, topic: dict[str, str], details: dict[str, object]) -> list[Scene]:
    archetype = str(details["archetype"])
    love = str(details["love"])
    stress = str(details["stress"])
    line_style = str(details["line"])
    strategy = str(details["攻略"])
    friend = str(details["friend"])
    traits = " / ".join(details["traits"])
    topic_key = str(topic.get("blueprint") or topic["key"])
    focus = _topic_focus(topic)

    if focus:
        focus_scenes = _build_focus_scenes(
            mbti_type,
            topic_key,
            focus,
            archetype=archetype,
            love=love,
            stress=stress,
            line_style=line_style,
            strategy=strategy,
            friend=friend,
            traits=traits,
        )
        if focus_scenes:
            return focus_scenes

    if topic_key == "trust_sign":
        return _build_trust_sign_scenes(mbti_type)

    format_builders: dict[str, list[Scene]] = {
        "like_attitude": [
            Scene("見逃しやすい最初の変化", f"{love}。表向きより、相手への温度差で本気が出やすい。"),
            Scene("会話で急に出る", f"{line_style}。いつもより会話を切らせないなら本命寄り。"),
            Scene("態度の決定打", f"{friend}。好きな相手にも、距離の詰め方はこの延長線に出やすい。"),
            Scene("周りが誤解しやすい所", f"{archetype}らしく平常心に見えても、実はかなり相手を見ている。"),
            Scene("本命を見抜くポイント", f"{mbti_type}は押しの強さより、小さい特別扱いに本気が出やすい。"),
        ],
        "crush_actions": [
            Scene("まず増える行動", f"脈ありだと {line_style}。反応の回数か、優先順位の上げ方に差が出る。"),
            Scene("誘い方で分かる", f"{love}。会う流れや予定の詰め方が、いつもより具体的になる。"),
            Scene("本命だけに出る空気", f"{friend}。軽いノリだけで終わらせないならかなり強い。"),
            Scene("勘違いしやすい点", f"愛想の良さではなく、継続して相手に時間を使うかを見ると外しにくい。"),
            Scene("脈ありを見抜く軸", f"{mbti_type}の脈ありは、言葉より優先順位と温度差に出やすい。"),
        ],
        "line_shift": [
            Scene("返信の温度差", f"{line_style}。普段より話題をつなぐなら、本気度はかなり高め。"),
            Scene("本命にだけ増える要素", f"雑談の中に気遣い、確認、次の会話の種が入ると強い。"),
            Scene("逆に誤読しやすい所", f"返信速度だけで決めると外しやすい。見るべきは内容の濃さ。"),
            Scene("追いLINEの相性", f"{strategy}。相手のテンポを尊重した方がちゃんと刺さる。"),
            Scene("LINEで見るべき所", f"{mbti_type}のLINEは、短文か長文かより温度の乗り方で見ると分かりやすい。"),
        ],
        "stress_signal": [
            Scene("しんどい時のサイン", f"{stress}。いつもの余裕が消えると、態度の静かさに出やすい。"),
            Scene("表面で見える変化", f"{traits}。普段と逆方向の反応が出たら疲れている可能性が高い。"),
            Scene("周りがやると助かる事", "詰めずに確認する、急かさない、理解しようとする。この3つでかなり違う。"),
            Scene("逆効果になりやすい事", "感情を決めつける、正論で押す、即レスを求めると閉じやすい。"),
            Scene("不調を見抜くポイント", f"{mbti_type}の不調は大声より、静かな違和感で出ることが多い。"),
        ],
        "攻略": [
            Scene("最初に効く接し方", f"{strategy}。相手のテンポを尊重しながら近づくのがかなり大事。"),
            Scene("会話で刺さるポイント", f"{archetype}らしさを理解したうえで、雑にいじらない方が強い。"),
            Scene("好印象になりやすい行動", f"{friend}。その距離感を尊重できると一気に縮みやすい。"),
            Scene("やりがちな地雷", "駆け引きだけで揺さぶる、理解したふりをする、圧だけで詰めるのは逆効果。"),
            Scene("距離が縮む決め手", f"{mbti_type}攻略は、派手さより相手に合う安心感を出せるかで決まる。"),
        ],
        "friendship_shift": [
            Scene("距離が縮む最初の合図", f"{friend}。礼儀だけでなく、気を抜いた反応が増えるとかなり近い。"),
            Scene("仲良くなると変わる会話", f"{traits}。雑談の内容やツッコミの強さに素が出やすい。"),
            Scene("頼り方で分かる", "小さく相談する、任せる、沈黙でも気まずくない。このどれかが増えると近い。"),
            Scene("誤解しやすい所", f"{archetype}らしく淡く見えても、距離が近い相手には反応の差が出やすい。"),
            Scene("仲良し判定の軸", f"{mbti_type}は盛り上がりより、気を遣わず自然体でいられるかで距離が縮みやすい。"),
        ],
        "work_trust": [
            Scene("仕事で信頼される強み", f"{traits}。このどれかが、職場での安心感に直結しやすい。"),
            Scene("任せられやすい場面", f"{strategy}。詰まった時の進め方で、信頼の差がかなり出る。"),
            Scene("一緒に働きやすい理由", f"{friend}。仕事でも距離感の取り方が合うと、かなり組みやすい。"),
            Scene("逆に信頼を削る所", "意図のない丸投げ、曖昧な指示、雑なフィードバックは一気に相性を落としやすい。"),
            Scene("職場で信頼を積むコツ", f"{mbti_type}には、能力だけでなく進め方の相性まで整えると長く信頼されやすい。"),
        ],
        "recharge_style": [
            Scene("消耗した時のサイン", f"{stress}。この変化が出たら、休み方を変える合図になりやすい。"),
            Scene("回復しやすい時間", f"{friend}。人との距離感を整えるだけで、戻り方がかなり変わりやすい。"),
            Scene("休み方の相性", f"{traits}。刺激を足すより、今の負荷を減らす方が回復しやすいタイプ。"),
            Scene("逆に消耗しやすい休み方", "予定を詰める、気を遣う場を増やす、無理に切り替えると回復が遅れやすい。"),
            Scene("整え方のコツ", f"{mbti_type}は気合いより、合う休み方を先に決める方が立て直しやすい。"),
        ],
        "communication_style": [
            Scene("話が噛み合う入り方", f"{line_style}。最初の一往復でテンポが合うと、会話がかなり進みやすい。"),
            Scene("伝わりやすい説明", f"{strategy}。情報の順番や温度感が合うと、かなり理解されやすい。"),
            Scene("会話で安心するポイント", f"{friend}。無理に盛り上げるより、相手のリズムを崩さない方が刺さりやすい。"),
            Scene("ズレやすい所", "結論だけ急ぐ、感情だけ押す、前提を飛ばすと噛み合いにくい。"),
            Scene("噛み合うコツ", f"{mbti_type}とは、何を先に話すかと、どこまで踏み込むかを合わせると会話が安定しやすい。"),
        ],
    }

    return format_builders[topic_key]


def _normalize_legacy_copy(text: str) -> str:
    normalized = text
    for old, new in LEGACY_COPY_REWRITES.items():
        normalized = normalized.replace(old, new)
    return normalized


def _naturalize_topic_name(topic_name: str, blueprint: str) -> str:
    normalized = topic_name
    if blueprint == "攻略" and topic_name == "の攻略で効く接し方":
        return "に効く接し方"

    replacements = {
        "本命だけに": "本命にだけ",
        "連絡の増え方": "連絡頻度",
        "返信の温度": "返信の温度感",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized


def _build_title(mbti_type: str, topic: dict[str, str]) -> str:
    blueprint = str(topic.get("blueprint") or topic["key"])
    normalized_name = _naturalize_topic_name(str(topic["name"]), blueprint)
    return f"{mbti_type}{normalized_name}"


def _unique_text_items(values: list[str]) -> list[str]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = str(raw_value).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized_values.append(value)
    return normalized_values


def _build_hashtags(config: AppConfig, topic: dict[str, str], mbti_type: str) -> list[str]:
    blueprint = str(topic.get("blueprint") or topic["key"])
    theme = str(topic.get("theme") or "").strip()
    return _unique_text_items(
        config.default_hashtags
        + DISCOVERY_HASHTAGS
        + ([f"#{theme}"] if theme else [])
        + TOPIC_HASHTAG_CANDIDATES.get(blueprint, [])
        + [f"#{mbti_type}"]
    )


def _build_caption_copy(title: str, hook: str, scenes: list[Scene], hashtags: list[str], topic: dict[str, str]) -> str:
    blueprint = str(topic.get("blueprint") or topic["key"])
    highlight_titles = [scene.title.strip() for scene in scenes[:3] if scene.title.strip()]
    lines = [title, hook]
    if highlight_titles:
        summary_template = CAPTION_SUMMARY_BY_BLUEPRINT.get(
            blueprint,
            "今回のネタでは『{highlights}』を中心に、違いが見えやすいポイントだけを短くまとめました。",
        )
        lines.append(
            summary_template.format(highlights=" / ".join(highlight_titles))
        )
    lines.append(
        CAPTION_CTA_BY_BLUEPRINT.get(
            blueprint,
            "当てはまると思ったら、あとで見返せるように保存しておくのがおすすめです。",
        )
    )
    lines.append("当てはまると思ったら保存して、気になる相手や友達に送って反応の答え合わせに使ってください。")
    lines.append(" ".join(hashtags))
    return "\n".join(lines)


def _build_caption_template(caption: str, hashtags: list[str], mbti_type: str) -> str:
    actual_mbti_hashtag = f"#{mbti_type}"
    template = caption.replace(actual_mbti_hashtag, MBTI_HASHTAG_PLACEHOLDER)
    if MBTI_HASHTAG_PLACEHOLDER in template:
        return template

    template_hashtags = _unique_text_items([
        tag for tag in hashtags if tag != actual_mbti_hashtag
    ] + [MBTI_HASHTAG_PLACEHOLDER])
    lines = template.rstrip().splitlines()
    hashtag_line = " ".join(template_hashtags)
    if lines and lines[-1].lstrip().startswith("#"):
        lines[-1] = hashtag_line
    else:
        lines.append(hashtag_line)
    return "\n".join(lines)


def _topic_for_content_package(config: AppConfig, content_package: ContentPackage) -> dict[str, str]:
    resolved_topic = _resolve_topic_from_state(config, content_package.format_name)
    if resolved_topic is not None:
        return resolved_topic

    return {
        "key": content_package.format_name,
        "name": content_package.format_name,
        "theme": content_package.theme,
        "blueprint": content_package.format_name,
    }


def _refresh_caption_fields(config: AppConfig, content_package: ContentPackage) -> ContentPackage:
    topic = _topic_for_content_package(config, content_package)
    hashtags = _build_hashtags(config, topic, content_package.mbti_type)
    caption = _build_caption_copy(
        content_package.title,
        content_package.hook,
        content_package.scenes,
        hashtags,
        topic,
    )
    return replace(content_package, caption=caption, hashtags=hashtags)


def _normalize_content_package(content_package: ContentPackage) -> ContentPackage:
    normalized_scenes = [
        Scene(
            title=_normalize_legacy_copy(scene.title),
            body=_normalize_legacy_copy(scene.body),
            duration_seconds=scene.duration_seconds,
        )
        for scene in content_package.scenes
    ]
    return replace(
        content_package,
        title=_normalize_legacy_copy(content_package.title),
        hook=_normalize_legacy_copy(content_package.hook),
        narration=_normalize_legacy_copy(content_package.narration),
        caption=_normalize_legacy_copy(content_package.caption),
        scenes=normalized_scenes,
    )


def _lock_distinct_scene_copy(config: AppConfig, content_package: ContentPackage) -> ContentPackage:
    topic = _topic_for_content_package(config, content_package)
    blueprint = str(topic.get("blueprint") or topic["key"])
    if blueprint != "trust_sign" and not _topic_focus(topic):
        return content_package

    details = TYPE_DATA.get(content_package.mbti_type)
    if not details:
        return content_package

    scenes = _build_scenes(content_package.mbti_type, topic, details)
    return replace(
        content_package,
        scenes=scenes,
        narration=_build_narration(content_package.title, content_package.hook, scenes),
    )


def build_template_package(
    target_date: date,
    config: AppConfig,
    explicit_mbti: str | None = None,
    explicit_format: str | None = None,
    global_post_index: int | None = None,
    daily_slot: int = 1,
) -> ContentPackage:
    resolved_mbti = explicit_mbti
    if resolved_mbti is None and global_post_index is not None:
        resolved_mbti = MBTI_POST_ORDER[global_post_index % SERIES_TOTAL_POSTS]
    mbti_type = (resolved_mbti or _choose_type(target_date)).upper()
    if mbti_type not in TYPE_DATA:
        raise ValueError(f"Unsupported MBTI type: {mbti_type}")

    if explicit_format:
        selected_format = _topic_by_name(config, explicit_format)
    elif global_post_index is not None:
        selected_format = topic_for_post_index(config, global_post_index)
    else:
        selected_format = dict(_choose_format(target_date))
        selected_format["blueprint"] = selected_format["key"]

    details = TYPE_DATA[mbti_type]
    scenes = _build_scenes(mbti_type, selected_format, details)
    archetype = str(details["archetype"])
    group = str(details["group"])
    hook = _hook_for_topic(str(selected_format.get("blueprint") or selected_format["key"]), mbti_type)
    title = _build_title(mbti_type, selected_format)
    narration = _build_narration(title, hook, scenes)
    hashtags = _build_hashtags(config, selected_format, mbti_type)
    series_post_number = (global_post_index % SERIES_TOTAL_POSTS) + 1 if global_post_index is not None else MBTI_POST_ORDER.index(mbti_type) + 1
    caption = _build_caption_copy(title, hook, scenes, hashtags, selected_format)

    return _normalize_content_package(ContentPackage(
        post_date=target_date.isoformat(),
        mbti_type=mbti_type,
        archetype_name=archetype,
        group_name=group,
        title=title,
        series_name=selected_format["name"],
        format_name=selected_format["name"],
        theme=selected_format["theme"],
        hook=hook,
        narration=narration,
        caption=caption,
        hashtags=hashtags,
        global_post_index=global_post_index or 0,
        daily_slot=daily_slot,
        series_post_number=series_post_number,
        series_total_posts=SERIES_TOTAL_POSTS,
        scenes=scenes,
    ))


def build_daily_packages(
    target_date: date,
    config: AppConfig,
    count: int | None = None,
    start_post_index: int | None = None,
    explicit_format: str | None = None,
    explicit_mbti: str | None = None,
) -> list[ContentPackage]:
    resolved_count = 1 if explicit_mbti else (count or config.daily_posts)
    base_post_index = load_series_state(config)["next_post_index"] if start_post_index is None else start_post_index
    use_stateful_topics = start_post_index is None and explicit_format is None
    packages: list[ContentPackage] = []
    for offset in range(resolved_count):
        post_index = base_post_index + offset
        mbti_type = explicit_mbti or MBTI_POST_ORDER[post_index % SERIES_TOTAL_POSTS]
        resolved_format = explicit_format
        if resolved_format is None and not use_stateful_topics:
            resolved_format = _topic_for_post_index(post_index)["name"]
        packages.append(
            build_template_package(
                target_date=target_date,
                config=config,
                explicit_mbti=mbti_type,
                explicit_format=resolved_format,
                global_post_index=post_index,
                daily_slot=offset + 1,
            )
        )
    return packages


def maybe_polish_with_llm(content_package: ContentPackage, config: AppConfig) -> ContentPackage:
    if not config.openai_api_key:
        return content_package

    request_payload = {
        "model": config.openai_model,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "あなたは TikTok 用の日本語ショート動画台本編集者です。"
                    + MONETIZATION_QUALITY_GUIDANCE
                    +
                    _topic_quality_guidance(config)
                    +
                    "最初の1〜2秒で止まるフックと、誰かに送りたくなる言い回しを優先してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "TikTok 向けに短く自然な日本語へ整えてください。"
                    "収益化条件を満たすアカウントを育てる前提で、保存・シェア・完読を取りやすい密度にしてください。"
                    "MBTI の断定は避けつつ、あるある表現にしてください。"
                    "タイトルは維持しつつ、フックは強めにしてください。"
                    "JSON で返してください。"
                    + json.dumps(content_package.to_dict(), ensure_ascii=False)
                ),
            },
        ],
        "temperature": 0.9,
    }

    try:
        response = _post_chat_completion(config, request_payload)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
    except Exception as exc:
        print(f"LLM polish skipped, continuing with template copy: {exc}")
        return content_package

    scenes = [Scene(**scene) for scene in data.get("scenes", [])] or content_package.scenes
    polished_package = _normalize_content_package(ContentPackage(
        post_date=data.get("post_date", content_package.post_date),
        mbti_type=data.get("mbti_type", content_package.mbti_type),
        archetype_name=data.get("archetype_name", content_package.archetype_name),
        group_name=data.get("group_name", content_package.group_name),
        title=data.get("title", content_package.title),
        series_name=data.get("series_name", content_package.series_name),
        format_name=data.get("format_name", content_package.format_name),
        theme=data.get("theme", content_package.theme),
        hook=data.get("hook", content_package.hook),
        narration=data.get("narration", content_package.narration),
        caption=data.get("caption", content_package.caption),
        hashtags=data.get("hashtags", content_package.hashtags),
        global_post_index=data.get("global_post_index", content_package.global_post_index),
        daily_slot=data.get("daily_slot", content_package.daily_slot),
        series_post_number=data.get("series_post_number", content_package.series_post_number),
        series_total_posts=data.get("series_total_posts", content_package.series_total_posts),
        scenes=scenes,
    ))
    polished_package = _lock_distinct_scene_copy(config, polished_package)
    return _refresh_caption_fields(config, polished_package)


def resolve_target_date(raw_value: str | None) -> date:
    if not raw_value:
        return date.today()
    return datetime.strptime(raw_value, "%Y-%m-%d").date()


def persist_package(content_package: ContentPackage, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    package_path = out_dir / "package.json"
    package_path.write_text(
        json.dumps(content_package.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "caption.txt").write_text(content_package.caption, encoding="utf-8")
    (out_dir / "caption_template.txt").write_text(
        _build_caption_template(content_package.caption, content_package.hashtags, content_package.mbti_type),
        encoding="utf-8",
    )
    (out_dir / "script.txt").write_text(content_package.narration, encoding="utf-8")
    return package_path
