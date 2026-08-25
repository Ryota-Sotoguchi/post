# MBTI Asset Bot

TikTok 用の MBTI コンテンツを画像スライドとしてまとめて作るツールです。1つのネタにつき 16 タイプを順番に回し、重複を避けながら台本、スライド画像、キャプションを出力します。生成は GitHub Actions 上で 1 日 3 回動き、完成したスライドは Telegram に届きます。

## できること / できないこと

- できること: 1日ぶんの画像スライド素材をまとめて作る
- できること: フック、各スライド文言、キャプション、ハッシュタグを生成する
- できること: `images/` や `assets/mbti_images/` の提供済み16タイプ素材を使う
- できること: 完成したスライドとキャプションを Telegram へ送る
- できないこと: 提供素材がないMBTIを自動キャラクターで代用する
- できないこと: TikTok への自動投稿

TikTok の Content Posting API は写真カルーセルに対応していますが、公開投稿には TikTok の審査が必要で、審査は「投稿前にクリエイターが内容を確認・承認する画面」を要件にしています。無人で投稿する仕組みとは構造的に噛み合わないため、投稿は手動のままにしています。

## セットアップ

### ローカル (WSL / Linux)

```bash
python3 -m venv .venv-linux
.venv-linux/bin/pip install -e .
sudo apt-get install -y fonts-noto-cjk
```

日本語フォントが 1 つも見つからない場合はエラーになります。既定では Windows の游ゴシック / メイリオ、Linux の Noto Sans CJK JP を順に探し、`MBTI_FONT_BOLD` / `MBTI_FONT_REGULAR` で上書きできます。

### 設定

`.venv/.env` に置くか、環境変数で渡します。環境変数が優先されます。

- `OPENAI_API_KEY`: 任意。未設定でもテンプレート生成で動作
- `OPENAI_MODEL=gpt-5-mini`
- `DAILY_POSTS=3`: 1日あたりに生成する本数
- `TOPIC_DEPTH=deep`: 心理的な葛藤、防衛反応、安心条件などの深掘り寄りにする。軽めに戻す場合は `standard`
- `MBTI_IMAGES_DIR=images`: 提供キャラ素材の保存先
- `DEFAULT_HASHTAGS`: 既定ハッシュタグ。ネタ別のおすすめタグも自動で補います
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`: 配信先
- `TELEGRAM_AS_DOCUMENT=true`: スライドを document として送る。Telegram は photo を再エンコードするため、既定で無劣化のこちら
- `PHONE_EXPORT_DIR=delivery/phone`: 完成スライドの書き出し先
- `MBTI_KEEP_RENDER_LAYERS=false`: レイヤ別 PNG を残すか。デバッグ用で、既定では完成スライドより嵩むため破棄します

## 使い方

その日の素材を作る:

```bash
python -m mbti_tiktok_bot run-daily
```

1 本ずつ進める:

```bash
python -m mbti_tiktok_bot run-slot
```

未実行スロットだけを埋めて終了する。GitHub Actions が使うのはこれです:

```bash
python -m mbti_tiktok_bot run-daemon --run-once
```

8:00、12:00、18:00 のうち、まだ生成していないスロットを順に実行します。`MAX_BACKLOG_DAYS` を超えて古い分は切り捨てるので、しばらく止まっていても大量生成にはなりません。

完成したスライドを Telegram へ送る:

```bash
python -m mbti_tiktok_bot send-telegram --date 2026-08-25
```

投稿1本につき、見出し → スライド7枚のアルバム → キャプション、の順に届きます。キャプションは独立したメッセージなので長押しでコピーできます。

企画だけ先に作る:

```bash
python -m mbti_tiktok_bot plan
```

MBTI タイプやフォーマットを固定する:

```bash
python -m mbti_tiktok_bot run-daily --mbti ENFP --format が好きな人に見せる態度 --dry-run
```

## GitHub Actions

[.github/workflows/daily.yml](.github/workflows/daily.yml) が JST 8:00 / 12:00 / 18:00 に動きます。GitHub は負荷時に定時実行を落とすため、各ジョブは「このジョブが1本担当する」と決め打ちせず、未実行スロットをデーモンに問い合わせて埋めます。

必要な Secrets:

- `OPENAI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

`out/` は `.gitignore` 済みなので、チェックアウト直後のリポジトリにはそのランが作ったものしか入りません。シリーズの進行状態だけが `state/series_state.json` としてコミットし戻されます。

リポジトリは private を前提にしています。`images/` の 16 タイプ素材を公開リポジトリに置かないためです。

## 出力

出力先は `out/<ネタフォルダ>/` です。1つのネタにつき 16 タイプ分が同じフォルダにたまります。

- `series_plan.json`: そのネタに属する投稿一覧
- `post_01_*/package.json`: 投稿案の全データ
- `post_01_*/caption.txt`: そのまま貼りやすい説明文とハッシュタグ
- `post_01_*/caption_template.txt`: MBTI ハッシュタグだけ `#MBTI_TYPE` にした差し替え用テンプレート
- `post_01_*/visual_identity.json`: 提供素材限定ポリシー、ネタ固有の構図ID、4グループ配色
- `post_01_*/slides/`: 完成スライド

`PHONE_EXPORT_DIR/<ネタフォルダ>/` にも完成スライドだけが書き出されます。

## カスタム画像を使う

`images/` か `assets/mbti_images/` に 16 タイプ分の素材を置きます。素材がないタイプは生成エラーになります。

## 投稿ネタの型

16 タイプを 1 周するごとに次の基本テーマへ進み、使い切ったあとは同じ blueprint を使いながらテーマ名を重複させない形で新テーマを追加します。

- が好きな人に見せる態度 / が脈ありの時にする行動 / のLINEが急に変わる瞬間 / が本気で心を許したサイン / がしんどい時に出るサイン
- の攻略で効く接し方 / が仲良くなるほど出る素の反応 / の仕事で信頼される関わり方 / の回復が早い休み方 / と会話が噛み合う話し方

## デザイン

人物表現は提供済みの16タイプ素材をベースにします。分析家・外交官・番人・探検家の4グループ配色を維持し、同じテーマの16タイプは共通のベースデザイン、レイアウト順、装飾ルールで揃えます。

1枚目はサムネイルで、MBTI、投稿タイトル、イラスト、スワイプ誘導を表示します。2枚目以降はサムネイルの大見出しとフックを再掲せず、提供素材を別トリミング、反転、角度で加工します。各スライドのカードは本文量に合わせて高さが決まります。

日本語の折り返しは [typeset.py](src/mbti_tiktok_bot/typeset.py) が行います。句読点、複数文字の助詞、内容語に付いた助詞を優先の区切りとし、ひらがなのあとの助詞は「ことが」の「が」は助詞だが「急かす」の「か」は違う、という曖昧さがあるため次善の区切りとして扱います。行は余白いっぱいに詰めず、均等な長さを目標に割ります。

既存の出力を、台本・キャプション・投稿順・シリーズ進行状態を変えずに再描画する:

```bash
python -m mbti_tiktok_bot refresh-visuals
python -m mbti_tiktok_bot refresh-visuals --topic "が脈ありの時にする行動"
python -m mbti_tiktok_bot refresh-visuals --export-only
```

## 備考

- 収益化の前提はフォロワー1万人以上かつ直近30日間の再生数10万回以上です。企画、台本、フック、構成、キャプションは保存率、再生維持率、シェア率を意識した基準にします。
- 状態管理には `state/series_state.json` を使います。
- 同じ日付で `run-daily` を再実行した場合は既存の出力を再利用します。
