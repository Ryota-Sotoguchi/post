# MBTI Asset Bot

TikTok 用の MBTI コンテンツを、まずは画像素材としてまとめて作るためのツールです。1つのネタにつき 16 タイプを順番に回し、重複を避けながら台本、スライド画像、キャプションを出力します。スマホへの受け渡しは Teams ではなく、同期アプリが拾えるローカルフォルダへ書き出します。

## できること / できないこと

- できること: 1日ぶんの画像スライド素材をまとめて作る
- できること: フック、各スライド文言、キャプション、ハッシュタグを生成する
- できること: `images/` や `assets/mbti_images/` の提供済み16タイプ素材を使う
- できること: 生成した画像一式をスマホ同期用フォルダへ日次で書き出す
- できないこと: 提供素材がないMBTIを自動キャラクターで代用する
- できないこと: TikTok への自動投稿
- できないこと: Android エミュレータ、Appium、adb を使った投稿操作

## セットアップ

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
```

`env.sample` を `.venv/.env` にコピーして必要項目を入れてください。

- `OPENAI_API_KEY`: 任意。未設定でもテンプレート生成で動作
- `DAILY_POSTS=3`: 1日あたりに生成する本数
- `TOPIC_DEPTH=deep`: 生成する話題を心理的な葛藤、防衛反応、安心条件などの深掘り寄りにする。軽めに戻す場合は `standard`
- `MBTI_IMAGES_DIR=images`: 公式キャライラストの保存先
- `DEFAULT_HASHTAGS`: キャプション生成時の既定ハッシュタグ。ここに加えて、ネタ別のおすすめタグも自動で補います
- `PHONE_EXPORT_AUTO=true`: `run-daily` のあとに同期用フォルダへ自動書き出しする
- `PHONE_EXPORT_DIR=delivery/phone`: Syncthing や FolderSync が監視する PC 側フォルダ

おすすめは Syncthing です。PC 側では `PHONE_EXPORT_DIR` を同期対象にし、スマホ側では `Pictures/MBTI` のようなローカルフォルダへ受けると、そのまま TikTok の画像選択に出しやすいです。クラウド前提なら FolderSync や OneSync で同じフォルダを拾う形でも回せます。

## 使い方

その日の素材を作る:

```powershell
python -m mbti_tiktok_bot run-daily
```

`PHONE_EXPORT_AUTO=true` の場合、このコマンドは `PHONE_EXPORT_DIR/<ネタフォルダ>/` に完成済みの PNG スライドだけを書き出します。同じネタの 16 タイプ分が 1 つのフォルダにたまっていく形です。

時刻ごとに 1 本ずつ進めたい場合:

```powershell
python -m mbti_tiktok_bot run-slot --export-phone
```

ターミナル常駐の 1 日 3 回デーモンとして回したい場合:

```powershell
python -m mbti_tiktok_bot run-daemon
```

このコマンドは 8:00、12:00、18:00 の未実行スロットだけを順番に実行し、重複防止の state を [state/phone_export_daemon_state.json](state/phone_export_daemon_state.json) に記録します。PowerShell を開いたままにしておけば Task Scheduler は不要です。止める時は Ctrl+C です。

このコマンドは `series_state.json` を 1 本分だけ進め、`PHONE_EXPORT_DIR/<ネタフォルダ>/` にそのネタの続きを追加していきます。各投稿フォルダには完成スライド PNG だけが入ります。

投稿はせず生成結果だけ確認する:

```powershell
python -m mbti_tiktok_bot run-daily --dry-run
```

手動実行だけ同期フォルダへ書き出したい場合:

```powershell
python -m mbti_tiktok_bot run-daily --export-phone
```

企画だけ先に作る:

```powershell
python -m mbti_tiktok_bot plan
```

MBTI タイプやフォーマットを固定したい場合:

```powershell
python -m mbti_tiktok_bot run-daily --mbti ENFP --format が好きな人に見せる態度 --dry-run
```

Windows タスクスケジューラで毎日の生成と同期フォルダ書き出しを回したい場合:

```powershell
./scripts/register-daily-task.ps1 -PythonExe ".\.venv\Scripts\python.exe" -Time "19:00"
```

8:00、12:00、18:00 に 1 本ずつスマホ受け渡しフォルダへ入れたい場合:

```powershell
./scripts/register-phone-export-tasks.ps1 -PythonExe ".\.venv\Scripts\python.exe"
```

タスクスケジューラを使わず、開きっぱなしの PowerShell で同じ時刻実行を回したい場合:

```powershell
./scripts/run-phone-export-loop.ps1 -PythonExe ".\.venv\Scripts\python.exe"
```

この常駐ループは次を行います。

- 8:00、12:00、18:00 を過ぎた未実行スロットだけをその場で実行する
- 実行済みスロットを [state/phone_export_loop_state.json](state/phone_export_loop_state.json) に記録して重複実行を防ぐ
- 実行ログを [logs/phone_export_loop.log](logs/phone_export_loop.log) と [logs/run_daily.log](logs/run_daily.log) に残す
- PC を落とさず PowerShell を開いたままにしておけば、Task Scheduler を使わず回せる

この登録は既定で次を有効にします。

- 画面ロック中でもそのまま実行する設定
- スリープ中なら起こして実行する設定
- 時刻に PC が使えなかった場合、次に使えるようになった時点で実行する設定
- 同じプレフィックス配下で不要になった旧時刻タスクを再登録時に削除する設定

開始日を明日以降にずらしたい場合:

```powershell
./scripts/register-phone-export-tasks.ps1 -PythonExe ".\.venv\Scripts\python.exe" -StartDate "2026-04-25"
```

ログアウト中の実行も狙う場合は、管理者権限の PowerShell から次を使います。

```powershell
./scripts/register-phone-export-tasks.ps1 -PythonExe ".\.venv\Scripts\python.exe" -RunWhenLoggedOut
```

この場合も、OneDrive の同期クライアント自体はログイン中の方が安定します。

## 出力

出力先は `out/<ネタフォルダ>/` です。1つのネタにつき 16 タイプ分が同じフォルダにたまっていきます。

- `series_plan.json`: そのネタに属する投稿一覧
- `post_01_*/package.json`: 投稿案の全データ
- `post_01_*/caption.txt`: そのまま貼りやすい説明文とハッシュタグ
- `post_01_*/caption_template.txt`: MBTI ハッシュタグだけ `#MBTI_TYPE` にした手動差し替え用テンプレート
- `post_01_*/slides/`: スライド画像

同期フォルダ書き出しを使う場合も、`PHONE_EXPORT_DIR/<ネタフォルダ>/` が作られます。各投稿フォルダの中には `slide_01.png` 以降の完成スライドだけが入ります。

## カスタム画像を使う

以下のどちらかに、16タイプ分の提供素材を置きます。素材がないタイプは生成エラーになります。

1. `images/` に 16 タイプ分の画像を置く
2. `assets/mbti_images/` に置く

## 投稿ネタの型

16 タイプを 1 周するごとに、まずは次の基本テーマへ進みます。これを使い切ったあとは、同じ blueprint を使いながらもテーマ名を重複させない形で新テーマを追加します。

- が好きな人に見せる態度
- が脈ありの時にする行動
- のLINEが急に変わる瞬間
- が本気で心を許したサイン
- がしんどい時に出るサイン
- の攻略で効く接し方
- が仲良くなるほど出る素の反応
- の仕事で信頼される関わり方
- の回復が早い休み方
- と会話が噛み合う話し方

## 備考

- 収益化の前提は、フォロワー1万人以上かつ直近30日間の再生数10万回以上です。報酬は動画パフォーマンスに応じて発生するので、今後の企画テーマ、台本、フック、構成、キャプションは 1万人超えを狙える保存率、再生維持率、シェア率を意識したクオリティを基準にします。
- `OPENAI_API_KEY` を入れると、フックや言い回しを少し自然に磨けます。
- 状態管理には `state/series_state.json` を使います。
- 通常の `run-daily` は完了後に `series_state.json` を進めるので、16 タイプの並びを重複させずに次へ進みます。
- 同じ日付で `run-daily` を再実行した場合は既存の出力を再利用するので、日次タスクの二重実行でもネタ順が崩れにくい形にしています。
- スマホへ運ぶところは自前 API より、Syncthing や FolderSync のような既製の同期に任せる方が安定します。
- Android/Appium 連携と TikTok 自動投稿は廃止しました。

## 提供素材ベースのデザインと既存出力の更新

人物表現は、必ず提供済みの16タイプ素材をベースにします。分析家・外交官・番人・探検家の4グループ配色を維持し、同じテーマの16タイプは共通のベースデザイン、レイアウト順、装飾ルールで揃えます。

1枚目は必ずサムネイルになり、`COVER`、MBTI、投稿タイトル、イラストを表示します。「テーマ：○○」の補助テキストは表示しません。二重縁カード、光彩、ジュエル区切り、細線フレーム、背景テクスチャを使った豪華なデザインを全スライドに適用します。2枚目以降はサムネイルの大見出しとフックを再掲せず、提供素材を別トリミング、反転、角度、フレームで加工します。文字は日本語の禁則処理と孤立行補正を通し、読みやすい太さ、コントラスト、余白を維持します。

すでに `out/` にある投稿画像だけを、台本・キャプション・投稿順・シリーズ進行状態を変えずに再描画する場合:

```powershell
python -m mbti_tiktok_bot refresh-visuals
```

1ネタだけを更新する場合:

```powershell
python -m mbti_tiktok_bot refresh-visuals --topic "が脈ありの時にする行動"
```

スマホ同期先も同時に差し替える場合は `--export-phone` を付けます。各投稿の `_render/_shared/visual_identity.json` に、提供素材限定ポリシー、ネタ固有の構図ID、4グループ配色が記録されます。

再描画済みの完成画像を、レンダリングし直さずスマホ同期先へ置き直す場合:

```powershell
python -m mbti_tiktok_bot refresh-visuals --export-only
```

`refresh-visuals` から同期先へ差し替える場合は、キャッシュ済みの旧画像を残さないため、対象テーマの同期先フォルダをすべて削除し、削除完了を確認してから新しい画像を格納します。このクリーン再格納は今後の同種作業でも必須です。
