# 取得例

`ctx.py` で擬似プロジェクトを取得した実例です。

| パス | 内容 |
| --- | --- |
| [`sample-project/`](sample-project/) | 取得元の擬似プロジェクト(Python の ToDo CLI + 簡易 Web ビューア) |
| [`sample-context.md`](sample-context.md) | 実際に取得したコンテキスト(クリップボードに入る内容そのもの) |

## 取得コマンド

```powershell
python ctx.py examples/sample-project -o examples/sample-context.md
```

`ctx.py` を `sample-project/` に置いた場合は、そこで `python ctx.py` を実行すると同じ内容がクリップボードに入ります。

## 対象ファイルの確認 (`--list`)

```text
PS> python ctx.py examples/sample-project --list
       9 tok  .gitignore
      80 tok  pyproject.toml
      75 tok  README.md
      19 tok  src/todo/__init__.py
     293 tok  src/todo/cli.py
     156 tok  src/todo/models.py
     300 tok  src/todo/storage.py
     180 tok  tests/test_storage.py
     100 tok  web/app.js
      49 tok  web/index.html

10 ファイル / 推定 1,531 トークン
```

## 擬似プロジェクトの全ファイルと扱い

```text
sample-project/
├── CONTEXT_PROMPT.md            → 冒頭プロンプトとして先頭に入る(本文には含めない)
├── .ctxignore                   → 除外設定(本文には含めない)
├── .env.example                 → 除外: 既定の秘密情報パターン .env.*
├── .gitignore                   ✓
├── assets/logo.png              → 除外: 画像 (*.png)
├── docs/internal/meeting-notes.md → 除外: .ctxignore の docs/internal/
├── pyproject.toml               ✓
├── README.md                    ✓ (``` を含むので ```` で囲まれる)
├── src/todo/__init__.py         ✓
├── src/todo/cli.py              ✓
├── src/todo/models.py           ✓
├── src/todo/storage.py          ✓
├── tests/test_storage.py        ✓
├── web/app.js                   ✓
└── web/index.html               ✓
```

## 例の更新

`tests/test_example.py` が `sample-context.md` と実際の出力の一致を確認しています。
出力形式を意図して変えたときは次で作り直してください。

```bash
CTX_UPDATE_EXAMPLE=1 pytest tests/test_example.py
```
