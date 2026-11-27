# llm-assist-kit

## ctx.py — プロジェクトを丸ごと LLM チャットに貼るためのツール

エージェントではない普通のチャット型 LLM (ChatGPT / Claude.ai / Gemini など) に、

1. **冒頭プロンプト** (CLAUDE.md のような指示文)
2. **スキル** (このキットの `skills/` にある作業手順と補助スクリプトの説明。Claude Code の `SKILL.md` と同じ形式)
3. **ディレクトリツリー**
4. **各ファイルの生ソースコード**

を **1 つのテキスト** にまとめてクリップボードへコピーします。あとはチャット欄に `Ctrl+V` するだけです。

LLM はコマンドを実行できないので、スクリプトは自分で PowerShell から実行します。
結果を LLM に見せたいときは `python <キット>\ctx.py run -- <コマンド>` で実行すると、
結果が LLM 向けの形でクリップボードに入るので、そのままチャットに貼り付けます。

- 標準ライブラリのみ (Python 3.11+)、`pip install` 不要
- Windows では Win32 API で直接クリップボードへ書き込むので日本語も文字化けしません
  (macOS: `pbcopy`、Linux: `wl-copy` / `xclip` / `xsel`、WSL: `clip.exe`)

### セットアップ

このキット (リポジトリ) を 1 か所に置きます。プロジェクトには何も置きません。
[Releases](https://github.com/takuya109048/llm-assist-kit/releases) の `llm-assist-kit-<版>.zip` を
展開するか、`git clone` します (zip には開発用の `tests/`・`tools/` は入っていません)。

```
C:\tools\llm-assist-kit\      ← キット (例)
├── ctx.py
└── skills\                    ← スキル (どのプロジェクトでも使う)
    ├── apply-patch\SKILL.md, apply.py, apply_patch.zip
    └── marp-slides\SKILL.md, build.py, editable_pptx.py, theme.css, marp.zip, assets\

my-project\                    ← 対象プロジェクト
├── AGENTS.md                  ← (任意) 冒頭プロンプト
├── .ctxignore                 ← (任意) 追加の除外パターン
└── src\ ...
```

初期設定として、キットのフォルダで次を 1 回実行します。PowerShell のプロファイルに `ctx` などの関数が登録され、
どのフォルダからでも `ctx` で使えるようになります。

```powershell
cd C:\tools\llm-assist-kit
python install.py
```

- Windows PowerShell 5.1 と PowerShell 7 の両方のプロファイル (`$PROFILE.CurrentUserAllHosts`) に登録します
- プロファイルの `# >>> llm-assist-kit >>>` 〜 `# <<< llm-assist-kit <<<` の範囲だけを書き換えるので、
  何度実行しても同じです。キットのフォルダを移したら、もう一度実行してください
- 実行ポリシーが `Restricted` だとプロファイルが読み込まれません。そのときは注意と、直すコマンドを表示します
  (`python install.py --set-execution-policy` で、現在のユーザーだけ `RemoteSigned` にもできます)
- 同じフォルダの別のプロファイル (`Microsoft.PowerShell_profile.ps1` や `Microsoft.VSCode_profile.ps1`) に
  同じ名前の関数やエイリアスが残っていると、そちらが後から読み込まれて優先されます。見つけたら場所を表示するので、
  古い定義を消してから PowerShell を開き直してください
- `python install.py --uninstall` で外せます。`--print` で書き込む内容だけ表示します
- 関数を追加するときは、`install.py` の `FUNCTIONS` に 1 行足して `python install.py` を実行し直します
  (関数の中身のスクリプトは `commands/` に置きます)

登録される関数:

| 関数 | 内容 |
| --- | --- |
| `ctx` | プロジェクトのコンテキストをクリップボードへ。`ctx run -- <コマンド>` で実行結果をコピー |
| `addcommit` | `git add -A` と `git commit -m` をまとめて行う。`addcommit メッセージ` (空白で区切った語はつなげて 1 つのメッセージにする) |
| `reset` | `git reset --hard HEAD` と `git clean -fd` をまとめて行い、最後のコミットの状態に戻す。消える内容を表示して確認してから実行 (`reset -y` で確認なし)。`.gitignore` で無視しているファイルは残る |
| `init` | 新しいプロジェクトのフォルダで実行すると、`AGENTS.md` (冒頭プロンプトのひな形)・`.ctxignore`・`.gitignore` を作り、`git init` する。すでにあるファイルは上書きしない。`init <フォルダ>` でフォルダを指定 (無ければ作る)、`init --no-git` で git init を省く。Box・OneDrive などで git が「dubious ownership」と言うフォルダは、git の `safe.directory` に登録して使えるようにする |
| `slideinit` | スライドのフォルダ (既定 `slides/`、`slideinit <フォルダ>` で指定) に、既定の画像 (表紙の背景 `assets/background.png`・ロゴ `assets/logo.png`)・テーマ (`assets/kit-slides.css`)・VS Code のプレビュー用の設定 (`.vscode/settings.json`) をそろえる。何度実行しても同じで、既にある画像は上書きしない。marp-slides スキルは、スライドを新しく作るパッチの前にこれを入れる |
| `slidepdf` | スライドを PDF にする。`slidepdf slides/発表.md` (省くと `slides/` の `*.md` をすべて) |
| `slidepptx` | スライドを文字を編集できる PowerPoint (PPTX) にする。使い方は `slidepdf` と同じ |

### 使い方 (PowerShell、プロジェクトのフォルダで)

```powershell
ctx                    # クリップボードへコピー (今いるフォルダが対象)
ctx --list             # 対象ファイルと推定トークン数を確認 (コピーしない)
ctx -i "src/**"        # src 以下だけ
ctx -i "*.py" -i "*.md" # 拡張子で絞り込み
ctx -x "tests/**"      # 除外を追加
ctx -n                 # 行番号付き
ctx -p review.md       # 別の冒頭プロンプトを使う
ctx --no-prompt        # 冒頭プロンプトなし
ctx -s apply-patch    # 入れるスキルを指定 (複数可。既定: すべて)
ctx --no-skills        # スキルを入れない
ctx -o context.md      # ファイルへ出力
ctx --stdout           # 標準出力へ
ctx C:\work\other     # 別のフォルダを対象にする
```

(関数を登録しない場合は `ctx` を `python C:\tools\llm-assist-kit\ctx.py` に読み替えてください。
`ctx.py` をプロジェクトにコピーして `python ctx.py` と実行しても同じように動きます。
その場合のスキルの場所は環境変数 `CTX_SKILLS_DIR` で指定します。)

実行するとこのように表示されます。

```
[ctx] クリップボードにコピーしました (Win32 API): 42 ファイル / 183,201 文字 / 推定 51,330 トークン
```

### 対象ファイルの決め方

| 仕組み | 内容 |
| --- | --- |
| `.gitignore` | git 管理下なら `git ls-files` で尊重 (未追跡ファイルも含む)。git が無ければ簡易パーサで解釈 |
| 既定の除外 | `node_modules` `.venv` `dist` `build` `__pycache__` などのディレクトリ、ロックファイル、`.env` / `*.pem` などの秘密情報、画像・アーカイブ等のバイナリ |
| `.ctxignore` | プロジェクト独自の除外 (`.gitignore` と同じ書式) |
| `-i` / `-x` | 実行時の絞り込み / 除外 |
| `--max-size` | 既定 200KB 超のファイルはスキップ |
| バイナリ判定 | NUL バイトを含む / UTF-8・CP932 として読めないファイルはスキップ |

`ctx.py` 自身と冒頭プロンプトファイル、`.ctxignore` は本文に含まれません。

### 冒頭プロンプト

ルート直下の `AGENTS.md` → `.ctxprompt.md` → `.ctxprompt` の順に探し、無ければ内蔵の日本語プロンプトを使います。
プロジェクトの概要・コーディング規約・回答形式などを書いておくと、CLAUDE.md と同じ感覚で使えます。
新しいプロジェクトでは `init` を実行すると、そのまま使える `AGENTS.md` が作られます。
このキットでの開発の流れ (`ctx` で貼る → LLM がパッチのコマンドを出す → `ctx run --` で結果を貼る →
`addcommit` / `reset`) と、進め方 (書く前に考える・シンプルに・必要な箇所だけ変える・ゴールを確かめる・原因を直す)、
境界 (先に確認 / しない) の決まりが入っているので、プロジェクトの概要とコマンドだけ書き足してください。
同じ指摘を 2 回したら、そのルールを足していくのがコツです。

冒頭プロンプトの `<!-- ... -->` (HTML コメント) は、コピーするときに取り除かれます (コードブロックの中は残ります)。
人向けのメモを書いておけます。

### スキル

キットの `skills/<名前>/SKILL.md` を読み込み、冒頭プロンプトの後に「# スキル」欄として入れます。
スキルはプロジェクトに置かず、キットで管理してどのプロジェクトでも使います。
Claude Code のスキルと同じ形式です。

| スキル | 内容 |
| --- | --- |
| [`apply-patch`](skills/apply-patch/SKILL.md) | LLM が出したパッチで、ファイルの修正・新規作成・削除・移動をまとめて行う (下記) |
| [`marp-slides`](skills/marp-slides/SKILL.md) | Marp でスライドを作り、PDF / HTML / PPTX に書き出す (表紙 + ヘッダー/フッター付きの決まった形。下記) |
| [`marp-slides`](skills/marp-slides/SKILL.md) | Marp でスライドを作り、PDF / HTML / PPTX に書き出す (表紙 + ヘッダー/フッター付きの決まった形。下記) |

スキルを追加するには `skills/<名前>/` に `SKILL.md` (とスクリプト) を置きます。

````markdown
---
name: my-skill
description: (このスキルを使う場面を 1 行で)
---
(LLM への指示。スクリプトを使う場合は、実行するコマンドをユーザーに依頼させる)

```powershell
python ${CTX} run -- python ${SKILL_DIR}/my_script.py
```
````

- `name` / `description` は省略可 (`name` の既定はフォルダ名)
- 本文の `${SKILL_DIR}` はスキルフォルダの実際のパス (例 `C:/tools/llm-assist-kit/skills/apply-patch`)、
  `${SKILLS_DIR}` はスキルを並べたフォルダ (例 `C:/tools/llm-assist-kit/skills`。ほかのスキルのスクリプトを
  `${SKILLS_DIR}/apply-patch/apply.py` のように指すときに使う)、
  `${CTX}` は ctx.py の実際のパスに置き換わるので、LLM はそのまま実行できるコマンドを示せます
- スキル欄の先頭には「あなたはコマンドを実行できない。実行はユーザーに `python <ctx.py> run -- ...` で依頼し、
  貼られた結果を待つこと」という説明が自動で付きます
- スキルの場所は `--skills-dir DIR` (複数可) か環境変数 `CTX_SKILLS_DIR` (`;` 区切り) で変更できます
- スキルのスクリプトも ctx.py と同じく標準ライブラリだけで書きます

### ファイルの変更をパッチで適用する (apply-patch スキル)

LLM にファイル全体を書き直させる代わりに、[codex](https://github.com/openai/codex) の
`apply_patch` 形式のパッチを出させ、まとめて適用します。

[SKILL.md](skills/apply-patch/SKILL.md) で LLM に「ファイルへのあらゆる変更 (修正・新規作成・追記・削除・移動) は、
パッチを埋め込んだ PowerShell コマンドとして、1 つのコードブロックに 1 つのコマンドで、省略せず最後まで出す」
ように指示しています。LLM は毎回次の形のブロックを出します。

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
@'
*** Begin Patch
*** Update File: src/app.py
@@ def greet(name):
-    print("Hi " + name)
+    print(f"こんにちは、{name} さん")
*** Add File: docs/usage.md
+# 使い方
*** Delete File: old.txt
*** End Patch
'@ | python C:/tools/llm-assist-kit/ctx.py run -- python C:/tools/llm-assist-kit/skills/apply-patch/apply.py -f -
```

1. そのブロックをコピーして、プロジェクトのフォルダの PowerShell に貼って実行する
2. パッチが適用され、結果 (`Success. Updated the following files: ...` かエラー) がクリップボードに入る
3. チャットに貼り返す

- 1 行目は、Windows PowerShell 5.1 でパッチ中の日本語が化けないための設定です
  (外部コマンドへのパイプが既定で ASCII になるため)
- `apply.py` は単体でも使えます: 引数なしでクリップボード (LLM の回答をまるごとコピーしたもの) から
  パッチ部分だけを取り出して適用、`-f patch.txt` でファイルから、`--dry-run` で変更されるファイルの一覧だけ表示
- 適用前に、追加・更新・削除するファイルの一覧を表示します
- プロジェクトの外を指すパス (絶対パスや `..`) を含むパッチは適用しません
- 途中で失敗したときは、そのとき適用した変更をすべて元に戻します (中途半端な状態を残しません)
- 適用は [`apply_patch.zip`](skills/apply-patch/apply_patch.zip) に入っている codex-rs の `apply_patch`
  (Windows x64 / Linux x64 用にビルドしたもの。Apache-2.0) で行います。
  初回に `skills/apply-patch/.bin/` に取り出して使います
- zip の作り直し: `python tools/build_apply_patch.py` (Linux で、Rust と mingw-w64 が必要。
  ビルド元のコミットは zip の `BUILD_INFO.txt` に記録されます)。
  ライセンス文だけを作り直すときは `--licenses-only` を付けます ([同梱しているソフトのライセンス](#同梱しているソフトのライセンス))

### スライドを作る (marp-slides スキル)

「〇〇の発表資料を作って」と頼むと、LLM が [Marp](https://marp.app/) の Markdown を決まった形で作り、
書き出しのコマンドを示します。

- 1 枚目は表紙: 背景画像の上、中央の横線の上にタイトル、下に部署名と日付 (左寄せ)
- 2 枚目以降: ヘッダー (スライドのタイトル) とフッター (左にページ数 / 総ページ数、右にロゴ) を線で本文と区切る
- 本文のレイアウトは 1 カラムのほか、`<!-- _class: ... -->` で `cols` (テキストの 2 カラム)、
  `image-right` (右に画像)、`image-left` (左に画像)、`table` (真ん中に大きな表)、
  `image` (真ん中に大きな画像)、`center` (ど真ん中に大きめのテキスト) を選べます
- 文字の色分け: Markdown の中に `<span class="red">言葉</span>` と書く (`red`・`blue`・`green`・`orange`・`gray`)。
  Marp CLI には `--html` を付けて書き出し、VS Code のプレビューも `markdown.marp.enableHtml` を有効にする (`slideinit` が設定する)
- フロー図・構成図などは、ユーザーが求めたとき、または図のほうが伝わると LLM が判断したときに、
  LLM が SVG ファイル (`slides/assets/<名前>.svg`) をスライドと同じパッチで作り、
  画像のレイアウト (`image` / `image-right` / `image-left`) に貼ります。大きさ・色・使える要素の決まりは
  [SKILL.md](skills/marp-slides/SKILL.md) に、見本は [`example-flow.svg`](skills/marp-slides/assets/example-flow.svg) にあります。
  PowerPoint では SVG の画像として入り、「図形に変換」で箱や文字を個別に編集できます
- 見た目はテーマ [`theme.css`](skills/marp-slides/theme.css) (`theme: kit-slides`) で決めます。
  フォントは半角英数が Segoe UI、全角 (日本語) がメイリオです
- 全パターンを使った見本: [`example.md`](skills/marp-slides/example.md) (11 枚) と、
  それを書き出した、文字を編集できる PowerPoint [`examples/marp-slides-example.pptx`](examples/marp-slides-example.pptx)

```powershell
slideinit                     # slides/ に既定の画像・テーマ・VS Code の設定をそろえる (最初の 1 回)
slidepdf slides/発表.md        # PDF
slidepptx slides/発表.md       # 文字を編集できる PowerPoint
```

- スライドを新しく作るとき、LLM はパッチのコマンドと同じコードブロックに `slideinit` を入れて出します
  (1 回貼れば、フォルダの準備とスライドの作成がまとめて済みます)
- 関数を使わない場合は `python C:/tools/llm-assist-kit/skills/marp-slides/build.py slides/発表.md` (PowerPoint は `--pptx` を付ける)

- `--pptx` は Marp CLI を使わず、[`editable_pptx.py`](skills/marp-slides/editable_pptx.py)
  (標準ライブラリだけ) が Markdown から直接 PPTX を作ります。Chrome / Edge / LibreOffice も不要です。
  - 文字は PowerPoint の段落、箇条書きと番号付きリストは PowerPoint の箇条書き、表は PowerPoint の表、
    画像・線・ロゴは個別の図形になり、そのまま編集できます。ページ番号はスライド番号のフィールドです
  - 位置と大きさは `theme.css` (と Marp の default テーマ) の寸法をそのまま写します (1px = 1/96 インチ)。
    行の高さは固定値、箱の内側の余白は 0 にして、ブラウザと同じ位置に行が並ぶようにしています。
    見本の各段落・表・画像の位置は、Chromium で描いた Marp の HTML と一致することをテストで確かめています
  - 文字の折り返しと表の列幅だけは文字の幅を見積もって決めるので、PDF と 1 文字ほど違うことがあります
  - 対象は SKILL.md の書き方 (表紙、本文のレイアウト、見出し・段落・箇条書き・表・画像・太字・斜体など) です。
    `<style>` や HTML で決めた見た目は再現しません
  - 画像は SVG のまま埋め込むので、PowerPoint 2016 以降で開いてください
  - 各スライドを画像にした (文字を編集できない) PPTX は作りません。以前の `--pptx-editable` は `--pptx` と同じです
  - 見本の PPTX の作り直しは下を参照

- Marp CLI は [`marp.zip`](skills/marp-slides/marp.zip) に入っている公式の単体版 (Windows x64 用。MIT) を
  初回に `skills/marp-slides/.bin/` に取り出して使うので、Node.js は不要です。
  PDF の書き出しには Edge か Chrome を使います
- zip にその OS 用が無ければ、`marp` コマンド、`npx @marp-team/marp-cli` (Node.js が必要) の順に使います
- zip の作り直し: `python tools/build_marp_zip.py` (`--version v4.5.1` で版を指定、
  `--targets windows-x86_64,linux-x86_64` で対象を追加。取得したファイルは公開されている SHA-256 と照合します)。
  ライセンス文だけを作り直すときは `--licenses-only` を付けます
- スライドと同じフォルダの `assets/` に `background.png` (表紙の背景)・`logo.png` (ロゴ) が無ければ、
  既定の画像をコピーします。`placeholder.svg` (画像のレイアウト用の仮の画像) は、スライドが使っているときだけ
  書き出しのときにコピーします。既にあれば上書きしないので、同じ名前のファイルを置けば差し替えられます
- VS Code (Marp for VS Code) のプレビューでも `kit-slides` テーマを使えるように、`build.py` を実行すると
  テーマをスライドの `assets/kit-slides.css` にコピーし、ワークスペースの `.vscode/settings.json` の
  `markdown.marp.themes` に登録します (拡張機能はワークスペースの中のテーマしか使えないため)。
  ワークスペースは、スライドの上のフォルダで `.vscode` があるところ、無ければ今のフォルダです。
  `settings.json` にコメントがあって読めないときは書き換えず、追加する値を表示します
- 見本の PPTX は、元 (`example.md`・テーマ・画像・書き出しのスクリプト) を変えたら
  `python tools/build_examples.py` で作り直します。元の SHA-256 を `examples/marp-slides-example.inputs` に記録し、
  見本が古いとテストが失敗します

### 実行結果のコピー (`run`)

```powershell
ctx run -- python -m pytest -q                # 引数をそのまま実行
ctx run "Get-ChildItem src | Select Name"      # 1 つの文字列なら PowerShell で実行
ctx run --tail 50 -- python -m pytest -q      # 最後の 50 行だけ (既定 200、0 で全部)
```

実行中の出力はそのまま画面に流れ、終わると次の形でクリップボードに入ります(`-o FILE` / `--stdout` も可)。
終了コードは実行したコマンドのものをそのまま返します。

````markdown
## 実行結果

```powershell
PS> python -m pytest -q
```

- 終了コード: 1 (失敗)

```text
(標準出力と標準エラーを合わせた出力。色の制御文字は除去)
```
````

### 出力形式

実際の取得例は [examples/](examples/) にあります(擬似プロジェクトと、取得したコンテキストそのもの)。

````markdown
(冒頭プロンプト)

# プロジェクト: my-project

## ディレクトリツリー

```text
my-project/
├── src/
│   └── main.py
└── README.md
```

## ソースコード (2 ファイル)

### README.md

```markdown
...
```

### src/main.py

```python
...
```
````

Markdown 内に ``` を含むファイルは、より長いフェンス (````) で囲むので崩れません。

### ライセンス

このキットは [MIT ライセンス](LICENSE) です。同梱している実行ファイルは、下のとおりそれぞれのライセンスに従います。

### 同梱しているソフトのライセンス

次の 2 つの zip には、他の人が作ったソフトの実行ファイルが入っています。
zip を配るときは、中のライセンス文も一緒に配ってください (zip ごと配れば満たせます)。

| zip | 中身 | ライセンス | zip に入れているライセンス文 |
| --- | --- | --- | --- |
| [`apply_patch.zip`](skills/apply-patch/apply_patch.zip) | [openai/codex](https://github.com/openai/codex) の `apply_patch` をビルドしたもの | Apache-2.0 | `LICENSE`・`NOTICE` (codex)、`THIRD_PARTY_LICENSES.txt` (組み込まれた Rust のクレート、Rust 標準ライブラリ、Windows 版の mingw-w64 の CRT と winpthreads) |
| [`marp.zip`](skills/marp-slides/marp.zip) | [Marp CLI](https://github.com/marp-team/marp-cli) の公式の単体版 | MIT | `LICENSE` (Marp CLI)、`THIRD_PARTY_LICENSES.txt` (組み込まれた Node.js と npm パッケージ) |

- どちらの zip にも、入手先・版・SHA-256 などを書いた `BUILD_INFO.txt` があります。
  apply_patch はビルドのために codex の `Cargo.toml` を絞っているので、そのことも `modifications:` に書いています
  (Apache-2.0 の第 4 条 b。ソースは変更していません)
- `THIRD_PARTY_LICENSES.txt` は `tools/build_apply_patch.py` と `tools/build_marp_zip.py` が作ります。
  組み込まれた部品を、apply_patch は `cargo tree` (通常の依存。ビルド用・開発用・proc-macro を除く) で、
  Marp CLI は同じ版の `package-lock.json` (実行時の依存と、rollup で取り込まれる依存) でたどり、
  各部品に入っているライセンスファイルを集めます。ライセンスファイルが無い部品は、末尾の付録に
  SPDX のライセンスの原文を載せます
- 実行ファイルを変えずにライセンス文だけ作り直す: `python tools/build_apply_patch.py --licenses-only`
  (`BUILD_INFO.txt` のコミットと Rust の版を使う。Linux で mingw-w64 が必要)、
  `python tools/build_marp_zip.py --licenses-only` (`BUILD_INFO.txt` の版を使う)。どちらも git が必要です

### リリース

1. `pyproject.toml` の `version` を上げ、[CHANGELOG.md](CHANGELOG.md) のいちばん上にその版の節 (`## v<版> (<日付>)`) を書いて main に入れる
2. GitHub の Actions で **Release** を選び、**Run workflow** で版 (例 `v0.1.0`) を入れて実行する。
   main の最新のコミットにタグを付け、`tools/build_release.py` が作った配布用の zip と
   CHANGELOG のその版の節を説明にしてリリースを作ります
   (手元で zip だけ作るときは `python tools/build_release.py v0.1.0`。`dist/` にできます)

### 開発

開発ルールは [CLAUDE.md](CLAUDE.md) を参照(pip + venv、pytest、ruff、pyrefly)。

```powershell
python -m venv .venv
.venv\Scripts\activate          # macOS / Linux: source .venv/bin/activate
pip install -e ".[dev]"
ruff check . ; ruff format --check . ; pyrefly check ; pytest
```

GitHub Actions で Windows / macOS / Linux × Python 3.11 / 3.13 を実行します。
Windows では実際のクリップボードへ書き込み、読み戻して日本語・絵文字が化けないことを確認します。
