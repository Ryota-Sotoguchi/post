# tiktok-poster

`保存先ディレクトリ` に溜まった MBTI カルーセルを、1日5回 TikTok の下書きへ自動送信します。
スマホでの作業は「通知を開いて投稿」だけになります。

- タイトル: `INTJがしんどい時に出るサイン`（MBTI + テーマ名）
- ハッシュタグ: `#恋愛 #MBTI #INTJ`
- 1回の送信で1テーマ分の1タイプ（7枚）を1カルーセルとして送ります

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

### 1. 依存関係

```bash
python3 -m venv --without-pip .venv
curl -sSfL https://bootstrap.pypa.io/get-pip.py | .venv/bin/python
.venv/bin/pip install -e .
```

### 2. 設定

プロジェクト直下に `.env` を作ります（リポジトリには含めません）。

```
SOURCE_DIR=/mnt/c/Users/<user>/OneDrive - .../Microsoft Copilot Chat ファイル
PAGES_BASE_URL=https://<user>.github.io/post/media
POSTS_PER_DAY=5
JPEG_QUALITY=90
KEEP_PUBLISHED_POSTS=20
TIKTOK_CLIENT_KEY=...
TIKTOK_CLIENT_SECRET=...
```

### 3. GitHub Pages を有効化

リポジトリの Settings → Pages で、Source を `main` ブランチの `/docs` に設定します。
`docs/media/` 配下が `PAGES_BASE_URL` で配信されます。

### 4. TikTok アプリを登録

1. [developers.tiktok.com](https://developers.tiktok.com) でアプリを作成
2. **Login Kit** を追加（Content Posting API の前提）→ **Content Posting API** を追加 → スコープ `video.upload` を追加
   - **Direct Post は無効のまま**にします。有効にすると `video.publish` が必要になり審査対象になります
3. **Manage URL properties** で `https://<user>.github.io/post/media/` を URL プレフィックスとして登録
4. 発行された署名ファイルを `docs/media/` に置いて push し、ポータルで Verify

> プレフィックスは完全一致で判定されます。`.../media/` を検証したなら `.../media/ab12/post_01_INTJ/01.jpg` は有効です。

### 5. 認可（初回のみ）

```bash
.venv/bin/python -m tiktok_poster authorize --redirect-uri <アプリに登録したURI>
# 表示された URL をブラウザで開いて承認 → リダイレクト先の code= をコピー
.venv/bin/python -m tiktok_poster authorize --redirect-uri <URI> --code <CODE>
```

トークンは `state/tokens.json` に保存されます（gitignore 済み・600）。
リフレッシュトークンは使うたびに更新されるため、自動で書き戻します。

### 6. 画像を一括で公開する

```bash
.venv/bin/python -m tiktok_poster sync
```

全カルーセルを JPEG に変換して `docs/media/` に配置し、`manifest.json`（タイトル・ハッシュタグ・画像URLの一覧）を書き出して push します。
**このコマンドだけが OneDrive を必要とします。** 新しい画像を追加したら再実行してください。

### 7. GitHub Actions を設定する

リポジトリの Settings → Secrets and variables → Actions で4つ登録します。

| Secret | 中身 |
|---|---|
| `TIKTOK_CLIENT_KEY` | 開発者ポータルの client key |
| `TIKTOK_CLIENT_SECRET` | 同 client secret |
| `TIKTOK_REFRESH_TOKEN` | `state/tokens.json` の `refresh_token` |
| `GH_PAT` | Secrets を書き換える PAT（下記） |

`GH_PAT` は **Fine-grained personal access token** を作り、このリポジトリに対して
**Secrets: Read and write** と **Contents: Read and write** を許可します。
リフレッシュトークンは使うたびに新しくなるため、Actions が自分で Secret を更新できないと翌日から動かなくなります。

以降 8:00 / 12:00 / 18:00 / 20:00 / 22:00 (JST) に1本ずつ自動送信されます。PC は不要です。

> Actions タブから手動実行もできます（送信本数の指定と dry-run が可能）。

## 使い方

```bash
python -m tiktok_poster sync                # 画像を変換して全部公開（要 OneDrive）
python -m tiktok_poster status              # 在庫と次に送る分
python -m tiktok_poster post --dry-run      # 送信内容を表示（API は叩かない）
python -m tiktok_poster post --count 1      # 1本送信
python -m tiktok_poster check               # 送信済みの取り込み状況を確認
```

## 動作

`sync`（ローカル）と `post`（どこでも）に分かれています。CI は OneDrive を読めないため、
必要な情報はすべて `manifest.json` に書き出しておく設計です。

**sync**

1. `SOURCE_DIR/<テーマ>/post_NN_TYPE/slide_NN.png` を走査して投稿順に並べる
2. PNG を JPEG へ変換して `docs/media/<テーマのハッシュ>/post_NN_TYPE/NN.jpg` に配置
   - テーマ名は日本語なので、URL には SHA-1 の先頭10桁を使います
3. `docs/media/manifest.json` にタイトル・ハッシュタグ・画像URLを書き出して push

**post**

1. `manifest.json` から、送信済み（`state/posted.json`）を除いた先頭を取る
2. Pages が実際に 200 を返すことを確認してから API を呼ぶ（404 を掴ませないため）
3. 下書きへ送信し、`publish_id` を `state/posted.json` に記録して push

## テスト

```bash
.venv/bin/python -m pytest -q
```

## PC 上で動かす場合（代替）

GitHub Actions を使わず Windows のタスクスケジューラで回すこともできます。

```powershell
./scripts/register-task.ps1
```

同じ5つの時刻に実行しますが、**PC が起動している必要があります**。
消えていた時間帯の分は次に起動したときにまとめて送られます。
