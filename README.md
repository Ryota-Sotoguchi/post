# tiktok

MBTI の TikTok カルーセルを作って、TikTok の下書きまで自動で送るツール。

1つのネタにつき MBTI 16 タイプを順に回し、重複を避けながら台本・スライド画像・キャプションを作る。
できたものは JPEG に変換して GitHub Pages に置き、GitHub Actions が TikTok の下書き受信箱へ送る。
公開だけがスマホからの手動操作になる。

## 構成

以前は生成と投稿が別リポジトリ・別マシンに分かれていて、その間を会社の OneDrive フォルダで受け渡していた。
今は1つのリポジトリに入っていて、受け渡しは `delivery/phone/` というリポジトリ内のフォルダになっている。

```
mbti_tiktok_bot                          tiktok_poster
─────────────────                        ─────────────
ネタ選択 → 台本 → スライド描画
        ↓
   out/<ネタ>/post_NN_TYPE/slides/
        ↓ phone_export
   delivery/phone/<ネタ>/post_NN_TYPE/  ──→  scan → JPEG 変換
        （PHONE_EXPORT_DIR）                      ↓
                                          docs/media/<slug>/post_NN_TYPE/NN.jpg
                                          docs/media/manifest.json
                                                 ↓ git push
                                          GitHub Pages
                                                 ↓ PULL_FROM_URL
                                          GitHub Actions → TikTok 下書き
```

`manifest.json` が2つの半分をつなぐ契約になっている。Actions のランナーは元画像を見られないので、
投稿に必要な情報（タイトル・説明文・画像URL）はすべて manifest に書き出しておく。

| いつ | どこで | 何が動くか |
|---|---|---|
| 08/12/16/20 時 | このPC (WSL) | `run-daemon --run-once` で4本生成 → `sync` で変換して push |
| 08–22 時 毎時 | GitHub Actions | `post` が下書きへ送る（1日10本上限） |
| 1日1回 | スマホ | 認可（下記「なぜ1日1回の承認が要るのか」） |

## 生成量

**1日16本 = 4 slot × 4本。** MBTI が16タイプなので、1つのネタが1日で完走して日をまたがない。
`SLOT_POSTS` と `daemon.DEFAULT_DAEMON_TIMES` の積で決まる。

投稿側は `POSTS_PER_DAY=10` なので、毎日6本ずつ在庫が積み上がる。
TikTok の下書き受信箱は同時6件までしか受け取らないため、投稿側をこれ以上増やしても詰まる。

## できないこと

- 公開投稿の自動化（API の制約。下記）
- 提供素材がない MBTI を自動生成キャラで代用すること（`images/` に16タイプ分が要る）

## なぜ「下書き」までなのか

TikTok の Content Posting API は、公開投稿する場合「投稿前に本人が内容を確認し同意する画面」の実装を必須にしています。

> A fully automated post with no review screen is not permitted.

この制約は **DIRECT_POST（API から直接公開投稿する場合）** にかかります。審査を通していないアプリの直接投稿は `SELF_ONLY` 固定になります。

そこで **MEDIA_UPLOAD（下書き送信）** を使います。**下書き送信に審査は不要です。**
API は下書きを置くところまでで、公開するのは TikTok アプリ内での本人の操作なので、審査が求める「本人が確認して投稿する」という条件が構造的に満たされているためです。
タイトルと説明文は API から入るので、届いた下書きを開いて投稿するだけで済みます。

> App review が必要になるのは `video.publish` / Direct Post を使う場合だけです。本ツールは要求しません。

## 制約（API 仕様）

| 項目 | 内容 |
|---|---|
| 画像形式 | WebP / JPEG のみ。**PNG は不可**（本ツールが JPEG へ変換します） |
| 取得方法 | `PULL_FROM_URL` のみ。HTTPS 必須、リダイレクト不可 |
| URL | 開発者ポータルで所有権を検証したプレフィックス配下であること |
| 枚数 | 1カルーセル最大 35 枚 |
| サイズ | 1枚 20MB 以下、最大 1080p |
| タイトル | 90 文字（UTF-16）まで |


## セットアップ

```bash
python3 -m venv .venv-linux
.venv-linux/bin/pip install -e .
sudo apt install fonts-noto-cjk      # 日本語フォントが無いと描画で落ちる
```

設定は**リポジトリ直下の `.env`** に置く（`.env.example` を写して埋める）。
生成側は以前 `.venv/.env` を読んでいた。venv を作り直すと消える場所なので直下に移したが、
既存チェックアウトのために `.venv/.env` も引き続き読む（直下が優先）。

主な項目:

| 変数 | 意味 |
|---|---|
| `PHONE_EXPORT_DIR` / `SOURCE_DIR` | 受け渡しフォルダ。**両方 `delivery/phone` を指す**（生成の出口 = 投稿の入口） |
| `SLOT_POSTS` | 1 slot の生成本数（4） |
| `POSTS_PER_DAY` | 1日の送信上限（10） |
| `PAGES_BASE_URL` | 開発者ポータルで検証した URL プレフィックスと**完全一致**させること |
| `KEEP_PUBLISHED_POSTS` | 送信済みを何本ぶん `docs/media` に残すか（20） |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | コピーの推敲とネタ生成に使う。未設定ならテンプレのまま動く |

### GitHub 側

- Pages を有効化（`main` / `/docs`）
- Secrets: `TIKTOK_CLIENT_KEY` `TIKTOK_CLIENT_SECRET` `TIKTOK_ACCESS_TOKEN` `GH_PAT`
- 開発者ポータルのリダイレクト URI と URL プレフィックスを `https://ryota-sotoguchi.github.io/post/` 配下で検証する

## 使い方

```bash
# 生成
.venv-linux/bin/python -m mbti_tiktok_bot run-daemon --run-once --no-reconcile
.venv-linux/bin/python -m mbti_tiktok_bot run-slot [--date YYYY-MM-DD] [--dry-run]
.venv-linux/bin/python -m mbti_tiktok_bot refresh-visuals [--topic 名前] [--export-only]

# 投稿
.venv-linux/bin/python -m tiktok_poster status
.venv-linux/bin/python -m tiktok_poster sync [--dry-run]
.venv-linux/bin/python -m tiktok_poster post --count 10 [--dry-run]
.venv-linux/bin/python -m tiktok_poster daily --sync-secret --no-post
```

`refresh-visuals` はコピー・投稿順・series state に触らず**描画だけ**やり直す。
レンダリングを変更したときの比較用。

## 定期実行

```powershell
./scripts/register-daily-task.ps1
```

WSL の cron は WSL セッションが上がっている間しか動かないので、Windows タスクスケジューラから
`wsl.exe` を叩く。1タスクで「生成 → sync」まで通す。
古い `MBTI Daily Generate` と `TikTok Image Import` が残っていたら登録解除する。

`--no-reconcile` は `state/phone_export_daemon_state.json` を信じるという意味。
これが無いと `out/` のファイル数で進捗を判断するので、state 上は済んでいる slot を作り直す。

## 出力

```
out/<ネタ>/series_plan.json
out/<ネタ>/post_NN_<MBTI>/
    package.json  caption.txt  caption_template.txt  script.txt
    visual_identity.json
    slides/slide_01.png … slide_07.png
delivery/phone/<ネタ>/post_NN_<MBTI>/slide_NN.png   ← スライドだけ
docs/media/<sha1(ネタ)[:10]>/post_NN_<MBTI>/NN.jpg  ← 公開される JPEG
```

テーマ名が日本語で URL に使えないので、公開側は SHA-1 の先頭10文字をスラッグにしている。

## ネタが尽きたら / 被ったら

ネタは10個の seed を使い切ると LLM が8個ずつ足す。名前が既存と8割似ていれば弾く。

それでも本文が既存と8割以上かぶることがある。**その場合はそのネタを引退させて次へ進む。**
16タイプ全部が同じようにかぶるので、タイプを変えても解決しないため。
引退したネタは `state/series_state.json` の `retired_topics` に移り、名前は今後の生成でも
ブロックされ続けるが、ローテーションからは外れる。

以前はここで `ValueError` を投げて slot ごと落としていた。次のトリガーでも同じネタを引くので、
**2026-09-06 から3日間、生成が1本も通らなかった。**

## 投稿順

`SOURCE_DIR/<テーマ>/post_NN_TYPE/` の **NN の昇順**で送ります。
1テーマを16本使い切ってから次のテーマの `post_01` に移ります。

順番は次の2つの規則で決まります。

1. **テーマの順番は「最初に送った順」。** 送信を始めたテーマを最後まで片付けてから、
   未着手のテーマ（マニフェスト順）に移ります。後から完成したテーマが、
   送信中のテーマの途中に割り込むことはありません。
2. **枠が欠けたら、そこで待ちます。** 8本送ったあと9本目がまだ描かれていなければ、
   10本目にも別のテーマにも進まず待機します。順番が崩れるくらいなら止める、
   という方針です。

待機中は `post` と `status` がその枠を名指しします。

```
Waiting for   : post_09 of 「が好意の手前で見せる近づきたいのに避ける瞬間」 - draw it and run `sync`
```

描いて `sync` を実行すれば自動的に再開します。**待機は下書き送信を完全に止める**
ので、`status` の `Waiting for` 行は定期的に見てください。

## サンドボックスで確認できたこと（2026-09-02）


**確認できた事実**

| 操作 | 結果 |
|---|---|
| `grant_type=refresh_token` | HTTP 200 / `invalid_grant`。発行直後のトークンでも拒否される |
| `/v2/user/info/`（`user.info.basic` を要求・承認） | `scope_not_authorized` |
| `content/init`（PHOTO / MEDIA_UPLOAD） | `status: SEND_TO_USER_INBOX` / `error.code: ok`。**TikTok は配信成功と回答** |
| 未公開の下書きが溜まった状態 | `spam_risk_too_many_pending_share`（実測6本前後で拒否） |
| 本番アプリの `client_key` | 審査承認前は認可エラー |

**公式ドキュメントの記述**

- 写真の `MEDIA_UPLOAD` は正式にサポートされている（Photo Post リファレンス）
- サンドボックスの除外対象は原文で *"Sandbox mode does not offer access to Content Posting API for public videos or Data Portability API."* ——
  **"public videos" に限定されており、下書き/受信箱アップロードは除外されていない**
- アップロード後の導線は *"they must click on inbox notifications to continue the editing flow in TikTok"*
  ——アプリの**受信トレイの通知**から編集フローに入る

**未解決**

送信した6本がアプリ側で確認できていない。TikTok は成功を返しており、公式仕様上も不可という根拠はないため、
原因は特定できていない。受信トレイの通知を確認する必要がある。

## 毎日の運用

**1日1回、これだけ実行する。**

```bash
cd ~/projects/tiktok && .venv-linux/bin/python -m tiktok_poster daily --sync-secret --no-post
```

ブラウザで承認して、戻ってきたアドレスを貼り付ける。
取得したアクセストークンが GitHub Actions に渡り、その日の送信が自動で走る。
あとは届いた下書きを TikTok アプリで公開する。

スマホからやる場合は `https://ryota-sotoguchi.github.io/post/` を開く。
承認してリダイレクト先の URL をコピーし、`authorize.yml` の workflow_dispatch に貼る。

### なぜ1日1回の承認が要るのか

サンドボックスのアプリは `grant_type=refresh_token` が `invalid_grant` で拒否される。
アクセストークンは24時間で切れ、Actions 側では更新できないため、1日1回だけ人の承認が要る。
審査を通して本番アプリになればこの制約はなくなる。

### 下書きは6本まで

未公開の下書きが**6本**溜まると `spam_risk_too_many_pending_share` で拒否される（実測値）。
24時間あたりではなく**同時保持数**の制限なので、公開すればすぐ枠が戻る。

そのため送信を1日15スロットに分散し、満杯のときは送らずに次のスロットへ回す。
弾かれたカルーセルは飛ばされず、キューの先頭に留まる。

## docs/media の掃除

TikTok は送信時に1度だけ画像を取りに来るので、取り込み済みのカルーセルを置き続ける必要はない。
`sync` の最後に `media.prune()` が走り、未送信のキュー全部と、直近 `KEEP_PUBLISHED_POSTS` 本の
送信済みだけを残す。

この配線が無かったせいで `docs/media` は 298MB まで育っていた。

## 投稿ネタの型

16 タイプを 1 周するごとに次の基本テーマへ進み、使い切ったあとは同じ blueprint を使いながらテーマ名を重複させない形で新テーマを追加します。

- が好きな人に見せる態度 / が脈ありの時にする行動 / のLINEが急に変わる瞬間 / が本気で心を許したサイン / がしんどい時に出るサイン
- の攻略で効く接し方 / が仲良くなるほど出る素の反応 / の仕事で信頼される関わり方 / の回復が早い休み方 / と会話が噛み合う話し方

## デザイン

スライドは **1080x1920 を2倍（2160x3840）で描いて、合成の最後に一度だけ LANCZOS で縮小**する。
Pillow の `ImageDraw` はポリゴン・円弧・線・角丸をアンチエイリアスしないので、そのまま描くと
コーナー装飾も吹き出しの尻尾も五角形マスクもジャギる。座標リテラルは数百あるので書き換えず、
`ScaledDraw` が論理座標のまま受け取って拡大する。`RENDER_SCALE = 1` にすれば元の描画に戻る。

**測定だけは 1x のまま**にしてある。`_fit_wrapped_text` の縮小ループが2刻みなので、2倍で測ると
1x では届かないサイズに着地して、フォントサイズと折り返しがずれる（実コピー640通りで27件ずれた）。

### モチーフ

ネタ名から `chat` / `grid` / `pulse` / `orbit` / `ribbon` のどれかが決まる。
これとは別に、シードで約4本に1本が **`editorial`**（写真背景＋ガラスパネル＋ゴールド意匠）になる。
`MBTI_EDITORIAL_PHOTOS_DIR` が空ならこの motif はローテーションから外れる。

写真は現在4枚しかないので、7〜10枚のスライドでは必ず使い回しになる。
同じ写真が連続しないよう並べ、出るたびにクロップとズームを変えている。
**枚数を増やせばそのぶん自動で散る**（コード変更は不要）。ここがこの motif の実質的な上限。

### 配色

4グループ × 6バリアント = **24パレット**。ネタ単位のシードで選ぶので、同じネタの16タイプは
必ず同じ配色になり、ネタが変われば色が変わる。

各パレットは `accent`（装飾用の明るい色）と `accent_deep`（白文字を載せる色）を分けている。
以前は白文字を `accent` に直接載せていて、探検家で 1.57:1、番人で 2.00:1 と実質読めなかった。
`tests/generator/test_palettes.py` が全24色に対してコントラスト下限を課している。

### 装飾

キャンバスの枠は `frame_full` / `frame_hairline` / `corners_only` / `rule_top` / `bare` の5種から
シードで選ぶ。以前は全投稿・全スライドに同じ二重枠とコーナー装飾が乗っていた。

### 枚数とレイアウト

1投稿は **表紙1＋本文5〜8＋締め1＝7〜10枚**。本数はネタ名から決まり、シリーズ内では固定。
拡張シーンは既存のタイプ別素材を別角度で組み替えるので、タイプ別の新規執筆は要らない。

同じネタの16タイプは**必ず同じレイアウト**になる。レイアウト密度スコアはタイプ別のコピー長では
なくネタが決める値だけから計算している（以前は本文長を見ていて、1文字差でパネルが動いた）。

1枚目はサムネイルで、MBTI・タイトル・イラスト・スワイプ誘導を出す。2枚目以降は大見出しと
フックを再掲せず、提供素材を別トリミング・角度で加工する。カードの高さは本文量で決まる。

日本語の折り返しは [typeset.py](src/mbti_tiktok_bot/typeset.py) が行う。句読点、複数文字の助詞、
内容語に付いた助詞を優先の区切りとし、ひらがなのあとの助詞は「ことが」の「が」は助詞だが
「急かす」の「か」は違う、という曖昧さがあるため次善の区切りとして扱う。行は余白いっぱいに
詰めず、均等な長さを目標に割る。

既存の出力を、台本・キャプション・投稿順・シリーズ進行状態を変えずに再描画する:

```bash
.venv-linux/bin/python -m mbti_tiktok_bot refresh-visuals
.venv-linux/bin/python -m mbti_tiktok_bot refresh-visuals --topic "が脈ありの時にする行動"
```

`visual_identity.json` に version・パレット名・chrome・レンダースケールが残るので、
出力がどの設定で作られたか後から辿れる。

## 備考

- 収益化の前提はフォロワー1万人以上かつ直近30日間の再生数10万回以上です。企画、台本、フック、構成、キャプションは保存率、再生維持率、シェア率を意識した基準にします。
- 状態管理には `state/series_state.json` を使います。

## テスト

```bash
.venv-linux/bin/python -m pytest tests/ -q
```

`tests/generator/` と `tests/poster/` に分かれている。どちらにも `test_media.py` があり、
flat のままだと pytest が同名モジュールを import できずに collect で落ちるため。
