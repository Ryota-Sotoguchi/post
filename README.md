# tiktok-poster

`保存先ディレクトリ` に溜まった MBTI カルーセルを、1日5回 TikTok の下書きへ自動送信します。
スマホでの作業は「通知を開いて投稿」だけになります。

- タイトル: `INTJがしんどい時に出るサイン`（MBTI + テーマ名）
- ハッシュタグ: `#恋愛 #MBTI #INTJ`
- 1回の送信で1テーマ分の1タイプ（7枚）を1カルーセルとして送ります

## なぜ「下書き」までなのか

TikTok の Content Posting API は、公開投稿する場合「投稿前に本人が内容を確認し同意する画面」の実装を必須にしています。

> A fully automated post with no review screen is not permitted.

審査を通していないアプリからの投稿は `SELF_ONLY` 固定かつアカウントを非公開にする必要があるため、無人での公開投稿は選べません。
そこで **MEDIA_UPLOAD（下書き送信）** を使います。タイトルと説明文は API から入るので、届いた下書きを開いて投稿するだけで済みます。

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

`.env.example` を `.env` にコピーして埋めます。

```
SOURCE_DIR=/mnt/c/Users/<user>/OneDrive - .../Microsoft Copilot Chat ファイル
PAGES_BASE_URL=https://<user>.github.io/post/media
POSTS_PER_DAY=5
TIKTOK_CLIENT_KEY=...
TIKTOK_CLIENT_SECRET=...
```

### 3. GitHub Pages を有効化

リポジトリの Settings → Pages で、Source を `main` ブランチの `/docs` に設定します。
`docs/media/` 配下が `PAGES_BASE_URL` で配信されます。

### 4. TikTok アプリを登録

1. [developers.tiktok.com](https://developers.tiktok.com) でアプリを作成
2. **Content Posting API** をプロダクトに追加し、スコープ `video.upload` を申請
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

### 6. 定期実行

```powershell
./scripts/register-task.ps1
```

8:00 / 12:00 / 18:00 / 20:00 / 22:00 に1本ずつ送ります。スリープしていた時刻は復帰後に取り返します。

## 使い方

```bash
python -m tiktok_poster status              # 在庫と次に送る5本
python -m tiktok_poster post --dry-run      # 変換して送信内容を表示（API は叩かない）
python -m tiktok_poster post                # 5本送信
python -m tiktok_poster post --count 1      # 1本だけ
python -m tiktok_poster check               # 送信済みの取り込み状況を確認
```

## 動作

1. `SOURCE_DIR/<テーマ>/post_NN_TYPE/slide_NN.png` を走査して投稿順に並べる
2. 送信済み（`state/posted.json`）を除いた先頭から必要数を取る
3. PNG を JPEG へ変換して `docs/media/<テーマのハッシュ>/post_NN_TYPE/NN.jpg` に配置
   - テーマ名は日本語なので、URL には SHA-1 の先頭10桁を使います
4. 古い公開分を削除して commit & push
5. Pages が実際に 200 を返すまで待ってから API を呼ぶ（404 を掴ませないため）
6. 下書きへ送信し、`publish_id` を記録

## テスト

```bash
.venv/bin/python -m pytest -q
```
