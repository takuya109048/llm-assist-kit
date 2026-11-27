# 変更履歴

リリースのたびに、いちばん上に `## v<版> (<日付>)` の節を足します。
リリースのページの説明には、その版の節がそのまま使われます (`tools/build_release.py`)。

## v0.1.0 (2026-11-27)

最初のリリースです。

### 使い方

1. 下の **Assets** から `llm-assist-kit-v0.1.0.zip` をダウンロードし、`C:\tools\` などに展開します。
2. 展開したフォルダで `python install.py` を実行し、PowerShell の関数 (`ctx` など) を登録します。
3. 詳しくは同梱の `README.md` を見てください。Python 3.11 以上が必要です。追加のインストールはいりません。

### 入っているもの

- **ctx.py**
  - 冒頭プロンプト・スキル・ディレクトリツリー・ソースコードを 1 つのテキストにまとめ、クリップボードへコピーします。
  - `ctx run -- <コマンド>` を使うと、コマンドの実行結果を LLM に渡しやすい形でコピーします。
- **PowerShell の関数**: `ctx`、`addcommit`、`reset`、`init`、`slideinit`、`slidepdf`、`slidepptx`
- **apply-patch スキル**
  - LLM が出したパッチで、ファイルの修正・新規作成・削除・移動をまとめて行います。
  - 途中で失敗したら、それまでの変更をすべて元に戻します。
  - 適用には codex-rs の `apply_patch` を使います。Windows x64 と Linux x64 用を同梱しています。
- **marp-slides スキル**: Marp でスライドを作り、PDF・HTML・PPTX に書き出します。
  - PPTX は文字を編集できる形で出します。SVG の図は、PowerPoint の図形・矢印・テキストに変えます。
  - 本文は上下の真ん中に置きます。2 カラムのときは、左右の上端をそろえます。
  - 見出しの中でも、語を色分けできます。
  - Marp CLI の単体版 (Windows x64 用) を同梱しているので、Node.js は必要ありません。

### ライセンス

- このキットは MIT ライセンスです (`LICENSE`)。
- 同梱している実行ファイルは、それぞれのライセンスに従います。
  - `apply_patch.zip`: Apache-2.0
  - `marp.zip`: MIT
- それぞれの zip に、組み込まれている部品のライセンス文 (`THIRD_PARTY_LICENSES.txt`) を入れています。
