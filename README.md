# llm-assist-kit

## ctx.py — プロジェクトを丸ごと LLM チャットに貼るためのツール

エージェントではない普通のチャット型 LLM (ChatGPT / Claude.ai / Gemini など) に、

1. **冒頭プロンプト** (CLAUDE.md のような指示文)
2. **スキル** (作業手順と補助スクリプトの説明。Claude Code の `SKILL.md` と同じ形式)
3. **ディレクトリツリー**
4. **各ファイルの生ソースコード**

を **1 つのテキスト** にまとめてクリップボードへコピーします。あとはチャット欄に `Ctrl+V` するだけです。

LLM はコマンドを実行できないので、スクリプトは自分で PowerShell から実行します。
結果を LLM に見せたいときは `python ctx.py run -- <コマンド>` で実行すると、
結果が LLM 向けの形でクリップボードに入るので、そのままチャットに貼り付けます。

- 標準ライブラリのみ (Python 3.11+)、`pip install` 不要
- Windows では Win32 API で直接クリップボードへ書き込むので日本語も文字化けしません
  (macOS: `pbcopy`、Linux: `wl-copy` / `xclip` / `xsel`、WSL: `clip.exe`)

### セットアップ

`ctx.py` を対象プロジェクトのルートフォルダにコピーするだけです。

```
my-project/
├── ctx.py              ← ここに置く
├── CONTEXT_PROMPT.md   ← (任意) 冒頭プロンプト
├── .ctxignore          ← (任意) 追加の除外パターン
├── .ctx/skills/        ← (任意) スキル
│   └── <名前>/SKILL.md
└── src/ ...
```

### 使い方 (PowerShell)

```powershell
python ctx.py                    # クリップボードへコピー
python ctx.py --list             # 対象ファイルと推定トークン数を確認 (コピーしない)
python ctx.py -i "src/**"        # src 以下だけ
python ctx.py -i "*.py" -i "*.md" # 拡張子で絞り込み
python ctx.py -x "tests/**"      # 除外を追加
python ctx.py -n                 # 行番号付き
python ctx.py -p review.md       # 別の冒頭プロンプトを使う
python ctx.py --no-prompt        # 冒頭プロンプトなし
python ctx.py -s run-tests       # 入れるスキルを指定 (複数可。既定: すべて)
python ctx.py --no-skills        # スキルを入れない
python ctx.py -o context.md      # ファイルへ出力
python ctx.py --stdout           # 標準出力へ
```

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

`.ctx/skills/<名前>/SKILL.md` (と `.claude/skills/<名前>/SKILL.md`) を読み込み、冒頭プロンプトの後に
「# スキル」欄として入れます。Claude Code のスキルと同じ形式なので、既存のものをそのまま使えます。

````markdown
---
name: todo-stats
description: todo.json の中身を集計する
---
ToDo データについて質問されたら、推測せずに集計スクリプトの実行をユーザーに依頼してください。

```powershell
python ctx.py run -- python ${SKILL_DIR}/stats.py todo.json
```
````

- `name` / `description` は省略可 (`name` の既定はフォルダ名)
- 本文の `${SKILL_DIR}` はスキルフォルダのパス (`.ctx/skills/todo-stats`) に置き換わります
- スキル欄の先頭には「あなたはコマンドを実行できない。実行はユーザーに `python ctx.py run -- ...` で依頼し、
  貼られた結果を待つこと」という説明が自動で付きます
- `SKILL.md` はスキル欄に入るので本文からは外します。同じフォルダのスクリプトは通常のファイルとして本文に入ります
- 探すフォルダは `--skills-dir DIR` で変更できます

### 実行結果のコピー (`run`)

```powershell
python ctx.py run -- python -m pytest -q                # 引数をそのまま実行
python ctx.py run "Get-ChildItem src | Select Name"      # 1 つの文字列なら PowerShell で実行
python ctx.py run --tail 50 -- python -m pytest -q      # 最後の 50 行だけ (既定 200、0 で全部)
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
