# 取得例

`ctx.py` で擬似プロジェクトを取得した実例です。

| パス | 内容 |
| --- | --- |
| [`sample-project/`](sample-project/) | 取得元の擬似プロジェクト(Python の ToDo CLI + 簡易 Web ビューア) |
| [`sample-context.md`](sample-context.md) | 実際に取得したコンテキスト(クリップボードに入る内容そのもの) |
| [`sample-run-result.md`](sample-run-result.md) | キットの search スキルのスクリプトを `ctx.py run` で実行した結果(LLM に貼り返す内容そのもの) |

スキルはキットの [`skills/`](../skills/) にあるもの (プロジェクトの外) を使っています。
キットの場所はマシンごとに違うので、例では `C:/tools/llm-assist-kit` に置いたものとして表しています。

## 取得コマンド

```powershell
cd examples/sample-project
python C:\tools\llm-assist-kit\ctx.py          # (関数を登録していれば ctx だけ)
```

## 対象ファイルの確認 (`--list`)

```text
PS> ctx --list
       9 tok  .gitignore
      23 tok  config/stage/prod.local.toml
      19 tok  docs/draft10.md
      22 tok  docs/TODO.md
      20 tok  keep.bak
      80 tok  pyproject.toml
      75 tok  README.md
      19 tok  src/todo/__init__.py
     293 tok  src/todo/cli.py
     156 tok  src/todo/models.py
      19 tok  src/todo/scratch_a.py
     300 tok  src/todo/storage.py
      33 tok  tests/fixtures/tmp
     180 tok  tests/test_storage.py
     100 tok  web/app.js
      49 tok  web/index.html
       skill  git-diff  (C:/tools/llm-assist-kit/skills/git-diff/SKILL.md)
       skill  run-tests  (C:/tools/llm-assist-kit/skills/run-tests/SKILL.md)
       skill  search  (C:/tools/llm-assist-kit/skills/search/SKILL.md)

16 ファイル / スキル 3 / 推定 2,979 トークン
```

## `.ctxignore` の全パターン

[`sample-project/.ctxignore`](sample-project/.ctxignore) では、使えるパターンをすべて 1 回ずつ使っています。
各パターンに「除外されるファイル」と「似ているが出力に入るファイル」を用意しています。

| # | パターン | 意味 | 除外される | 出力に入る |
| --- | --- | --- | --- | --- |
| 1 | `*.bak` | ベース名へのグロブ(どの階層にもマッチ) | `src/todo/cli.py.bak` | |
| 2 | `!keep.bak` | 否定: 除外したものを含め直す | | `keep.bak` |
| 3 | `tmp/` | 末尾 `/` はディレクトリだけ(どの階層でも) | `web/tmp/cache.js` | `tests/fixtures/tmp`(ファイル) |
| 4 | `/TODO.md` | 先頭 `/` はルート直下だけ | `TODO.md` | `docs/TODO.md` |
| 5 | `config/*.local.toml` | 途中に `/` があるとルートからのパス。`*` は `/` をまたがない | `config/dev.local.toml` | `config/stage/prod.local.toml` |
| 6 | `docs/internal/` | パス指定のディレクトリ | `docs/internal/meeting-notes.md` | |
| 7 | `!docs/internal/public.md` | 除外したディレクトリの中は `!` でも含め直せない(git と同じ) | `docs/internal/public.md` | |
| 8 | `web/**/generated.js` | `**` は 0 個以上のディレクトリ | `web/generated.js`<br>`web/lib/generated.js` | |
| 9 | `docs/draft?.md` | `?` は任意の 1 文字 | `docs/draft1.md` | `docs/draft10.md` |
| 10 | `scratch[0-9].py` | `[...]` は文字クラス(`[!...]` で否定) | `src/todo/scratch1.py` | `src/todo/scratch_a.py` |
| 11 | `\#memo.txt` | `\` で先頭の `#` や `!` を文字として扱う | `#memo.txt` | |
| | `# ...` / 空行 | コメントと空行は無視 | | |

`.ctxignore` 以外の理由で本文に入らないファイル:

| ファイル | 理由 |
| --- | --- |
| `CONTEXT_PROMPT.md` | 冒頭プロンプトとして先頭に入る |
| `.ctxignore` | 設定ファイル |
| `.env.example` | 既定の秘密情報パターン `.env.*` |
| `assets/logo.png` | 既定の画像パターン `*.png` |

`.ctxignore` が効くのは取得するフォルダ直下のものだけです(サブフォルダの `.ctxignore` は読みません)。

## スキルとスクリプト実行の流れ

[`sample-context.md`](sample-context.md) の「# スキル」欄に、キットの 3 つのスキル
(`run-tests` / `git-diff` / `search`) の `SKILL.md` が入っています。
`${SKILL_DIR}` と `${CTX}` は実際のパス (`C:/tools/llm-assist-kit/...`) に置き換わっているので、
LLM はそのまま実行できるコマンドを示せます。スキルのスクリプトはプロジェクトの外にあるので、
ツリーやソースコード欄には入りません。

チャットでのやり取りは次のようになります。

1. ユーザー: `ctx` でコピーしたコンテキストを貼り、「TaskStore はどこで使われている?」と質問
2. LLM: search スキルに従い、実行するコマンドを示す

   ```powershell
   python C:/tools/llm-assist-kit/ctx.py run -- python C:/tools/llm-assist-kit/skills/search/search.py TaskStore
   ```
3. ユーザー: プロジェクトのフォルダの PowerShell で実行 → 結果がクリップボードに入るので、チャットに貼る
   (貼る内容の実例: [`sample-run-result.md`](sample-run-result.md))
4. LLM: 貼られた結果をもとに回答する

## 例の更新

`tests/test_example.py` が `sample-context.md` / `sample-run-result.md` と実際の出力の一致、上の表のとおりに含まれる/除外されること、
`.ctxignore` の全パターンにテストケースがあることを確認しています。
出力形式を意図して変えたときは次で作り直してください。

```bash
CTX_UPDATE_EXAMPLE=1 pytest tests/test_example.py
```
