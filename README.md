# tiktok

MBTI の TikTok カルーセルを作って、TikTok の下書きまで自動で送るツール。

1日10本、4つの形式（16タイプ一覧・ランキング・取扱説明書・相性診断）の投稿を LLM で書いて描画し、
キャプションまで付ける。できたものは JPEG に変換して GitHub Pages に置き、GitHub Actions が
TikTok の下書き受信箱へ送る。公開だけがスマホからの手動操作になる。

以前の「1ネタ×16タイプ」形式（テーマ別カルーセル）は生成を止めた。在庫は残っていて、
新形式の在庫が切れたときの穴埋めとして送られる（「投稿順」参照）。

## 構成

以前は生成と投稿が別リポジトリ・別マシンに分かれていて、その間を会社の OneDrive フォルダで受け渡していた。
今は1つのリポジトリに入っていて、受け渡しは `delivery/phone/` というリポジトリ内のフォルダになっている。

GitHub 上のリポジトリ名は **`Ryota-Sotoguchi/post`** のまま。ローカルのディレクトリ名（`~/projects/tiktok`）と
一致しないのは意図的で、リポジトリ名を変えると GitHub Pages の URL が変わり、TikTok 側で検証済みの
URL プレフィックス（`https://ryota-sotoguchi.github.io/post/media`）とリダイレクト URI を取り直すことになる。

```
mbti_tiktok_bot                          tiktok_poster
─────────────────                        ─────────────
形式を選ぶ → LLM が書く → 描画
        ↓
   out/posts/<NNNNN-形式>/slides/
        ↓
   delivery/phone/_posts/<NNNNN-形式>/  ──→  scan → JPEG 変換
        （PHONE_EXPORT_DIR）                      ↓
                                          docs/media/posts/<NNNNN-形式>/NN.jpg
                                          docs/media/manifest.json
                                                 ↓ git push
                                          GitHub Pages
                                                 ↓ PULL_FROM_URL
                                          GitHub Actions → TikTok 下書き
```

旧形式の在庫は `delivery/phone/<ネタ>/post_NN_TYPE/` → `docs/media/<slug>/post_NN_TYPE/` の経路のまま。

`manifest.json` が2つの半分をつなぐ契約になっている。Actions のランナーは元画像を見られないので、
投稿に必要な情報（タイトル・説明文・画像URL）はすべて manifest に書き出しておく。

| いつ | どこで | 何が動くか |
|---|---|---|
| 08/12/16/20 時 ＋ ログオン時 | このPC (WSL) | `scripts/scheduled-run.sh`：生成 → 格納（push）→ 古い画像の削除 → 足りなければ投稿を起動 |
| 08–22 時 毎時 | GitHub Actions | `post` が下書きへ送る（1日10本上限） |
| 1日1回 | スマホ or PC | 承認（下記「なぜ1日1回の承認が要るのか」） |

## 生成量

**1日10本。** 生成と送信は同じ `POSTS_PER_DAY` を見るので、在庫は切れも積み上がりもしない。

slot は決まった本数を作るのではなく、「その日のうち、今までに過ぎた slot の分」に足りない本数を作る。
4 slot なら 08時で2本、12時で5本、16時で7本、20時で10本が目標で、`out/posts/*/post.json` の
日付で数えた実績との差だけを作る。再実行やログオン時の取りこぼし回収でも二重には作らない。

TikTok の下書き受信箱は同時6件までしか受け取らないため、送信側をこれ以上増やしても詰まる。

## 投稿の形式

10本は次の順で回る（同じ形式が2本続かない）:

`一覧 → 取説 → ランキング → 相性 → 取説 → 一覧 → 相性 → 取説 → ランキング → 相性`

| 形式 | 枚数 | 中身 |
|---|---|---|
| 16タイプ一覧 | 18 | 「既読スルーされた時の16タイプ」。表紙に16体、1タイプ1枚、締め |
| ランキング | 9 | 16〜5位は4タイプずつ、4位から1位は1枚ずつ。1位は放射線付き |
| 取扱説明書 | 10 | 1タイプを8項目で。角度（基本/恋愛/友達/仕事）は16タイプを1周するごとに変わる |
| 相性診断 | 8 | 1タイプから見た相性◎3位→1位、要注意3位→1位 |

一覧とランキングのお題は seed を使い切ると LLM が10個ずつ足す（既存と8割似ていれば弾く）。
取説と相性は同じ日に同じタイプが重ならないよう、相性側を8タイプずらしている。

コピーは1投稿1回の LLM 呼び出し（`gpt-5-mini`, reasoning_effort=low, 約10秒）で書く。
16タイプが揃っていない・相性に自分自身が入っている、などの不正な応答はタイプ別データからの
テンプレートに落とす。`out/posts/*/post.json` の `source` が `template` なら落ちた回。

進み具合は `state/format_state.json`（次の番号・形式ごとのカーソル・追加されたお題）。
`sync` がこれもコミットする。

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
| `POSTS_PER_DAY` | 1日の生成本数と送信上限（10）。生成側と送信側で共通 |
| `PAGES_BASE_URL` | 開発者ポータルで検証した URL プレフィックスと**完全一致**させること |
| `KEEP_PUBLISHED_POSTS` | 送信済みを何本ぶん `docs/media` に残すか（20） |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | コピーの推敲とネタ生成に使う。未設定ならテンプレのまま動く |

### GitHub 側

- Pages を有効化（`main` / `/docs`）
- Secrets: `TIKTOK_CLIENT_KEY` `TIKTOK_CLIENT_SECRET` `TIKTOK_ACCESS_TOKEN` `GH_PAT`
- 開発者ポータルのリダイレクト URI は `https://ryota-sotoguchi.github.io/post/`、URL プレフィックスは `https://ryota-sotoguchi.github.io/post/media`（どちらも登録・検証済み）

## 使い方

```bash
# 生成
.venv-linux/bin/python -m mbti_tiktok_bot run-daemon --run-once --no-reconcile
.venv-linux/bin/python -m mbti_tiktok_bot run-slot [--date YYYY-MM-DD] [--dry-run] [--count N]

# 投稿
.venv-linux/bin/python -m tiktok_poster status
.venv-linux/bin/python -m tiktok_poster sync [--dry-run]
.venv-linux/bin/python -m tiktok_poster post --count 10 [--dry-run]
.venv-linux/bin/python -m tiktok_poster daily --sync-secret --no-post
```

`run-slot` は今の時刻までに必要な本数に足りない分だけ作る。`--count` を付けるとその本数を作る。
`run-daily` / `plan` / `refresh-visuals` は旧形式用で、定期実行からは使っていない。

## 定期実行

```powershell
./scripts/register-daily-task.ps1
```

WSL の cron は WSL セッションが上がっている間しか動かないので、Windows タスクスケジューラから
`wsl.exe` を叩く。タスクは1つ（`MBTI Daily`）で、中身は [scripts/scheduled-run.sh](scripts/scheduled-run.sh)。

| 順 | 手順 | やること |
|---|---|---|
| 1 | pull | Actions がコミットした送信記録と承認状態を取り込む |
| 2 | generate | 前日・当日で足りない本数を生成（`run-daemon --run-once --no-reconcile`） |
| 3 | store | JPEG 変換 → `docs/media` → push。生成側の進捗 state も一緒にコミット |
| 4 | cleanup | 送信済みから `KEEP_LOCAL_DAYS` 日（60）経った投稿・テーマの画像を削除 |
| 5 | post | 今日の下書きが `POSTS_PER_DAY` に届いていなければ Actions の `post.yml` を起動 |

**PC を起動していなかった日の取りこぼし**は、ログオン時トリガー（ログオン2分後）で拾う。
全手順が冪等なので、何も溜まっていなければ数秒で終わる。
`StartWhenAvailable` はスリープ中に過ぎた時刻を後から実行するが、電源オフ中に過ぎたものは拾わないため、ログオン時も別途走らせている。

1つの手順が失敗しても残りは走る。生成が落ちても、在庫がある以上その日の投稿まで止める理由はないため。
失敗はタスクの終了コードと `logs/task.log` に残る。

取りこぼしの範囲には上限がある:

- **生成**は前日分まで（`MAX_BACKLOG_DAYS = 1`）。それ以前の日は作り直さない。数日止まった分は旧形式の在庫（約220本）が埋める
- **投稿**は当日分だけ。1日の上限はその日の送信数で数えるので、前日の不足分を翌日に上乗せはしない（下書き受信箱も同時6件まで）

**投稿はこの PC からは送らない。** Actions の実行を起動するだけ。送信記録・1日の上限・受信箱の上限はすべて
Actions 側でコミットされた state に対して判定されていて、PC から直接送ると、まだ pull していない朝の送信分を
知らないまま数えて二重送信しうるため。

その日の承認がまだなら投稿は起動せず、代わりに**承認ページ（`https://ryota-sotoguchi.github.io/post/`）をブラウザで開く**
（1日1回まで）。サンドボックスのアプリはトークンを更新できないので、承認なしに起動しても送信の段で失敗するだけのため。
承認すれば次の実行（最長4時間後、または次のログオン）で投稿が再開する。

`--no-reconcile` は `state/phone_export_daemon_state.json` を信じるという意味。
これが無いと `out/` のファイル数で進捗を判断するので、state 上は済んでいる slot を作り直す。

## ローカルの保持期間

`out/` と `delivery/phone/` は毎日増える。`cleanup` は**送信から `KEEP_LOCAL_DAYS` 日（既定60）経った**
新形式の投稿について `delivery/phone/_posts/<番号>/` と `out/posts/<番号>/slides/` を消す。
`post.json` は残す（その日の生成本数をこれで数えているため）。

旧形式は、**テーマの全投稿が送信済み**で、**最後の送信から60日経った**テーマについて:

- `delivery/phone/<ネタ>/` を丸ごと削除
- `out/<ネタ>/post_*/slides/` を削除し、`package.json`・キャプション・台本は**残す**

台本を残すのは、生成時の重複ガードが `out/` の `package.json` と突き合わせているため。消すと数ヶ月前のネタが戻ってくる。
送信途中のテーマには触らない。

```bash
.venv-linux/bin/python -m tiktok_poster cleanup --dry-run          # 何が消えるか
.venv-linux/bin/python -m tiktok_poster cleanup --dry-run --days 0 # 送信済みテーマ全部なら
```

## 出力

```
out/posts/<NNNNN-形式>/
    post.json          ← 書いた内容すべて（カード・フック・ハッシュタグ・source）
    caption.txt        ← TikTok の説明文（フック＋CTA＋ハッシュタグ）
    visual_identity.json
    slides/slide_01.png …
delivery/phone/_posts/<NNNNN-形式>/slide_NN.png, post.json（タイトルと説明文）
docs/media/posts/<NNNNN-形式>/NN.jpg
```

旧形式:

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

**新形式が先、旧形式は穴埋め。** 新形式は番号順（作った順）に送り、未送信の新形式が無いときだけ
旧形式のテーマ別カルーセルに進みます。

旧形式は `SOURCE_DIR/<テーマ>/post_NN_TYPE/` の **NN の昇順**で送ります。
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

## デザイン

### 新形式（`design/`）

**4つのルック × 6つのレイアウト。** ルックは投稿番号で回るので、同じ見た目が2本続かない。

| ルック | 方向 | 中身 |
|---|---|---|
| NEON | かっこいい | 暗いオーロラ背景、白抜きの特大欧文、ガラスパネル、キャラにリムライトとグロー |
| BUBBLE | かわいい | パステルとドット、白フチのステッカー見出し、丸バッジの数字、キャラは傾けたステッカー |
| EDITORIAL | おしゃれ | 紙の質感、明朝の見出し、罫線、キャラは円やアーチの窓で切り抜く |
| BRUTAL | 最先端 | ベタ塗り＋グリッドとトンボ、黒ベタの数字、角チップ、キャラはダブルトーン＋ハードシャドウ |

レイアウト（`cover` `entry` `grid` `section` `pair` `closer`）は文字を下から先に組み、残った高さを
キャラに渡す。長い見出しが顔にかぶらないのはこのため。

フォントは同梱（`assets/fonts/`、すべて SIL OFL）: Zen Kaku Gothic New（Medium/Bold/Black）、
Anton、Bebas Neue。細いウェイトと明朝はシステムの Noto を使う。
Zen Kaku には `palt` が無いので、約物（「」、。）の半角詰めは [design/text.py](src/mbti_tiktok_bot/design/text.py) で自前で行う。
見出しの改行は語の途中で切らない（「既読で／とりあえず放置派」「静かに／寄り添う共鳴者」）。
切れる場所が無ければ縮めて収める。

キャラ画像は16点すべて切り抜きに揃えてある（白背景だった4点は `scripts/cutout-white-background.py` で一度だけ処理）。

描画は1投稿10〜20秒。同じ投稿は何度描いても同じ画像になる（粒子ノイズもシード固定）。

### 旧形式

以下は旧形式（テーマ別カルーセル）の描画の説明。生成は止めているが、コードは残っている。

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
