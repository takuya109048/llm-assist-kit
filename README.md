# llm-assist-kit

## ctx.py — プロジェクトを丸ごと LLM チャットに貼るためのツール

エージェントではない普通のチャット型 LLM (ChatGPT / Claude.ai / Gemini など) に、

1. **冒頭プロンプト** (CLAUDE.md のような指示文)
2. **ディレクトリツリー**
3. **各ファイルの生ソースコード**

を **1 つのテキスト** にまとめてクリップボードへコピーします。あとはチャット欄に `Ctrl+V` するだけです。

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

### 出力形式

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

### テスト

```powershell
python -m unittest discover -s tests -v
```

GitHub Actions で Windows / macOS / Linux × Python 3.11 / 3.13 を実行します。
Windows では実際のクリップボードへ書き込み、読み戻して日本語・絵文字が化けないことを確認します。
