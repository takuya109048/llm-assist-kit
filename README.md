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

```
C:\tools\llm-assist-kit\      ← キット (例)
├── ctx.py
└── skills\                    ← スキル (どのプロジェクトでも使う)
    ├── apply-patch\SKILL.md, apply.py, apply_patch.zip
    ├── run-tests\SKILL.md
    ├── git-diff\SKILL.md, diff.py
    └── search\SKILL.md, search.py

my-project\                    ← 対象プロジェクト
├── CONTEXT_PROMPT.md          ← (任意) 冒頭プロンプト
├── .ctxignore                 ← (任意) 追加の除外パターン
└── src\ ...
```

毎回パスを打たなくて済むように、PowerShell のプロファイル (`notepad $PROFILE`) に関数を登録しておくと便利です。

```powershell
function ctx { python C:\tools\llm-assist-kit\ctx.py @args }
```

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
ctx -s search -s git-diff  # 入れるスキルを指定 (複数可。既定: すべて)
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

ルート直下の `CONTEXT_PROMPT.md` → `.ctxprompt.md` → `.ctxprompt` の順に探し、無ければ内蔵の日本語プロンプトを使います。
プロジェクトの概要・コーディング規約・回答形式などを書いておくと、CLAUDE.md と同じ感覚で使えます。

### スキル

キットの `skills/<名前>/SKILL.md` を読み込み、冒頭プロンプトの後に「# スキル」欄として入れます。
スキルはプロジェクトに置かず、キットで管理してどのプロジェクトでも使います。
Claude Code のスキルと同じ形式です。

| スキル | 内容 |
| --- | --- |
| [`run-tests`](skills/run-tests/SKILL.md) | コードの変更を提案したら、テストの実行を依頼して結果を確認する |
| [`git-diff`](skills/git-diff/SKILL.md) | 変更を反映した後、git の差分 ([`diff.py`](skills/git-diff/diff.py)) を見せてもらい提案どおりか確認する |
| [`search`](skills/search/SKILL.md) | プロジェクト内を検索 ([`search.py`](skills/search/search.py)) して該当箇所を見せてもらう |
| [`apply-patch`](skills/apply-patch/SKILL.md) | LLM が出したパッチで、ファイルの修正・新規作成・削除・移動をまとめて行う (下記) |

スキルを追加するには `skills/<名前>/` に `SKILL.md` (とスクリプト) を置きます。

````markdown
---
name: search
description: プロジェクト内を文字列や正規表現で検索して、該当箇所を見せてもらう
---
確認したい箇所があれば、検索の実行をユーザーに依頼してください。

```powershell
python ${CTX} run -- python ${SKILL_DIR}/search.py "検索する文字列"
```
````

- `name` / `description` は省略可 (`name` の既定はフォルダ名)
- 本文の `${SKILL_DIR}` はスキルフォルダの実際のパス (例 `C:/tools/llm-assist-kit/skills/search`)、
  `${CTX}` は ctx.py の実際のパスに置き換わるので、LLM はそのまま実行できるコマンドを示せます
- スキル欄の先頭には「あなたはコマンドを実行できない。実行はユーザーに `python <ctx.py> run -- ...` で依頼し、
  貼られた結果を待つこと」という説明が自動で付きます
- スキルの場所は `--skills-dir DIR` (複数可) か環境変数 `CTX_SKILLS_DIR` (`;` 区切り) で変更できます
- スキルのスクリプトも ctx.py と同じく標準ライブラリだけで書きます

### ファイルの変更をパッチで適用する (apply-patch スキル)

LLM にファイル全体を書き直させる代わりに、[codex](https://github.com/openai/codex) の
`apply_patch` 形式のパッチを出させ、まとめて適用します。

1. LLM が `*** Begin Patch` 〜 `*** End Patch` のパッチを出す (書き方は [SKILL.md](skills/apply-patch/SKILL.md) で LLM に伝わる)
2. LLM の回答をコピーして、プロジェクトのフォルダで実行する

   ```powershell
   ctx run -- python C:\tools\llm-assist-kit\skills\apply-patch\apply.py
   ```
3. 結果 (`Success. Updated the following files: ...` かエラー) がクリップボードに入るので、チャットに貼り返す

- クリップボードの中からパッチの部分だけを取り出すので、LLM の回答をまるごとコピーして構いません
  (`-f patch.txt` でファイルからも読めます。`--dry-run` で変更されるファイルの一覧だけ表示)
- 適用前に、追加・更新・削除するファイルの一覧を表示します
- プロジェクトの外を指すパス (絶対パスや `..`) を含むパッチは適用しません
- 途中で失敗したときは、そのとき適用した変更をすべて元に戻します (中途半端な状態を残しません)
- 適用は [`apply_patch.zip`](skills/apply-patch/apply_patch.zip) に入っている codex-rs の `apply_patch`
  (Windows x64 / Linux x64 用にビルドしたもの。Apache-2.0) で行います。
  初回に `skills/apply-patch/.bin/` に取り出して使います
- zip の作り直し: `python tools/build_apply_patch.py` (Linux で、Rust と mingw-w64 が必要。
  ビルド元のコミットは zip の `BUILD_INFO.txt` に記録されます)

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
