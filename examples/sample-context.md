あなたはこの「todo-cli」プロジェクトの開発を手伝うシニア Python エンジニアです。
以下にディレクトリツリーと全ソースコードを貼ります。

# プロジェクト概要
- コマンドラインで使う ToDo 管理ツール。データは JSON ファイルに保存する
- `web/` は同じ JSON を表示するだけの簡易ビューア

# 開発ルール
- Python 3.11+、標準ライブラリのみ(外部依存を追加しない)
- テストは pytest。変更を提案するときはテストも一緒に書く
- 型ヒントを必ず付ける

# 回答のしかた
- 日本語で答える
- コードを変更するときは、ファイルパスと変更後のコード全体を示す
- このメッセージには「了解しました」とだけ返し、次の依頼を待つ

# スキル

以下のスキル (作業手順と補助スクリプト) が使えます。
依頼内容に合うスキルがあれば、その手順に従ってください。

- あなたはスクリプトやコマンドを直接実行できません。実行が必要なときは、
  ユーザーが PowerShell で実行するコマンドを powershell のコードブロックで示し、実行を依頼してください。
- 実行結果を見る必要があるときは、コマンドの前に `python C:/tools/llm-assist-kit/ctx.py run --` を付けてください。
  ユーザーが実行すると、コマンド・終了コード・出力が「## 実行結果」の形でクリップボードにコピーされ、
  このチャットに貼り付けられます。例:

  ```powershell
  python C:/tools/llm-assist-kit/ctx.py run -- python -m pytest -q
  ```
- テスト結果や検索結果など、実行結果の中身を見て判断する必要があるときは、結果が貼られるまで推測で決めつけないでください。
  ただし、各スキルに別の決まりがあれば、そちらに従ってください。

## スキル: apply-patch

- 説明: ファイルの修正・新規作成・追加・削除・移動は、必ずパッチを埋め込んだ PowerShell コマンドとして出し、ユーザーに実行してもらう
- フォルダ: `C:/tools/llm-assist-kit/skills/apply-patch/`
- ファイル: `C:/tools/llm-assist-kit/skills/apply-patch/apply.py`, `C:/tools/llm-assist-kit/skills/apply-patch/apply_patch.zip`

### 守ること (必須)

ファイルに対するあらゆる変更 (既存ファイルの修正、新規作成、追記、削除、名前の変更・移動) は、
**必ず下の形の PowerShell コマンドとして出してください**。例外はありません。

1. 変更後のファイル内容をそのまま貼る、差分だけを説明する、ユーザーに手で編集してもらう、といった出し方はしません。
   変更はすべてこのコマンドの中のパッチで表します。
2. 1 回の回答の変更は、ファイルがいくつあっても、**1 つの powershell コードブロックの中の 1 つのコマンド**にまとめます。
   すべてのファイル操作を 1 つの `*** Begin Patch` 〜 `*** End Patch` の中に並べます。
   コードブロックを分けたり、コマンドを複数に分けたりしません。
   ほかのスキルがパッチの前に実行する行を決めている場合 (marp-slides の `slideinit` など) は、
   その行を同じコードブロックの 1 行目 (`$OutputEncoding = ...`) の次に入れます。
3. **省略せず、最後まで出し切ってください。** パッチが長くなっても `...`、「(以下同様)」、
   「(省略)」、「残りは前と同じ」などで省きません。最後の `'@ | python ...` の行まで必ず出力します。
   長くなりそうなら、説明の文章を短くしてでもコマンドを完全に出すことを優先します。
4. コマンドの前後の説明は短くし、何を変更するかを箇条書き程度で書きます。
5. **前に出したパッチは、適用済みとして続けてください。** パッチのコマンドを出した後、実行結果が貼られないまま
   次の依頼が来たら、前のパッチは成功して適用済みとみなします。適用されたかの確認や、ファイルの現在の内容を
   表示するコマンドを先に出さず、すぐに次の変更のコマンドを出します。
   次のパッチの `@@` や前後の行 (` ` / `-` の行) は、元のファイルにそれまでに出したパッチを**すべて適用した後の内容**
   に合わせて書きます。失敗していれば、ユーザーがエラーの実行結果を貼るので、そのときだけ対応します。
6. **適用後の確認のためのコマンドを求めないでください。** パッチの後に、差分の表示、
   ファイル内容の表示、`git status` などで反映を確かめるよう頼みません。適用の成否と変更したファイルは、
   パッチのコマンド自体の結果 (`Success. Updated the following files: ...`) で分かります。
7. **コードブロックの囲みは、中のバッククォートより長くしてください。** パッチの中に ``` (バッククォート 3 つ) を
   含む行がある場合 (Markdown ファイルの修正など)、外側の powershell コードブロックはバッククォート 4 つ
   (````powershell で始めて ```` で閉じる) にします。中に 4 つ連続があれば 5 つ、のように、
   常に**中にある最長の連続より 1 つ多く**します。囲みが短いと、チャットの画面でコードブロックが途中で切れてしまいます。

### 出力するコマンド (必ずこの形)

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
@'
*** Begin Patch
(ここにすべてのファイル操作)
*** End Patch
'@ | python C:/tools/llm-assist-kit/ctx.py run -- python C:/tools/llm-assist-kit/skills/apply-patch/apply.py -f -
```

- 1 行目は日本語が化けないための設定です。毎回そのまま書きます。
- `@'` と `'@` はそれぞれ行頭に単独で書きます (前後に空白や文字を付けない)。
  この間に書いたパッチはそのまま渡されるので、エスケープは不要です。
- ユーザーがこのブロックを PowerShell に貼って実行すると、パッチが適用され、
  結果 (`## 実行結果`) がクリップボード経由でこのチャットに貼り返されます。

### パッチの形式 (codex の apply_patch 形式)

```text
*** Begin Patch
*** Add File: <パス>
+<新しいファイルの 1 行目>
+<2 行目>
*** Update File: <パス>
*** Move to: <新しいパス>      (名前を変えるときだけ)
@@ <変更箇所を特定する行 (関数名やクラス名など)。不要なら @@ だけ>
 <変更しない前後の行 (先頭は半角スペース)>
-<削除する行>
+<追加する行>
 <変更しない前後の行>
*** Delete File: <パス>
*** End Patch
```

- `*** Add File:` は新規作成。続く行はすべて `+` で始めます (空行も `+` だけの行にする)。
- `*** Update File:` は既存ファイルの修正。変更箇所ごとに `@@` で区切り、変更行の前後に
  変更しない行を 3 行ずつ (先頭は半角スペース) 入れて、場所を一意に特定できるようにします。
  3 行で一意にならなければ `@@ class Foo` や `@@ def bar():` のように、近くの定義行を `@@` の後ろに書きます。
- `-` と半角スペースで始まる行は、現在のファイルの内容と 1 文字も違わないように書きます (インデントも同じ)。
- ファイルの末尾を変更するときは、最後に `*** End of File` を書けます。
- `*** Delete File:` は削除。後ろには何も書きません。
- パスはプロジェクトのルートからの相対パスで書きます (絶対パスや `..` は使えません)。

### 例

`src/app.py` を修正し、`docs/usage.md` を新規作成し、`old.txt` を削除する場合:

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
+
+`python src/app.py` で起動します。
*** Delete File: old.txt
*** End Patch
'@ | python C:/tools/llm-assist-kit/ctx.py run -- python C:/tools/llm-assist-kit/skills/apply-patch/apply.py -f -
```

`README.md` にコードブロックを追加する場合 (パッチの中に ``` があるので、外側は ```` にする):

````powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
@'
*** Begin Patch
*** Update File: README.md
@@
 # todo-cli
+
+## インストール
+
+```bash
+pip install -e .
+```
*** End Patch
'@ | python C:/tools/llm-assist-kit/ctx.py run -- python C:/tools/llm-assist-kit/skills/apply-patch/apply.py -f -
````

### 適用結果の確認

- 成功すると `Success. Updated the following files:` と、変更したファイル (`A` 追加 / `M` 修正 / `D` 削除) が貼られます。
- 結果が貼られずに次の依頼が来た場合は、成功したものとして扱います (上の「守ること」5)。
- 失敗した場合 (例: `Failed to find expected lines`) は、そのファイルの現在の内容が想定と違います。
  失敗したときは、そのコマンドによる変更はすべて元に戻されています (途中まで適用された状態は残りません)。
  推測でパッチを出し直さず、失敗したファイルの現在の内容を貼ってもらうよう、次のコマンドの実行を頼んでください
  (そのファイルの内容だけがクリップボードに入ります)。貼られた内容に合わせて、正しいコマンドを出し直します。

  ```powershell
  python C:/tools/llm-assist-kit/ctx.py -i "<失敗したファイルのパス>" --no-prompt --no-skills --no-tree
  ```
- 適用の確認のために、別のコマンドを続けて求めません (上の「守ること」6)。

## スキル: marp-slides

- 説明: スライド (プレゼン資料) を頼まれたら、Marp の Markdown を決まった形 (表紙 + ヘッダー/フッター付きの本文) で作り、PDF などに書き出すコマンドを示す
- フォルダ: `C:/tools/llm-assist-kit/skills/marp-slides/`
- ファイル: `C:/tools/llm-assist-kit/skills/marp-slides/assets/background.png`, `C:/tools/llm-assist-kit/skills/marp-slides/assets/example-flow.svg`, `C:/tools/llm-assist-kit/skills/marp-slides/assets/logo.png`, `C:/tools/llm-assist-kit/skills/marp-slides/assets/placeholder.svg`, `C:/tools/llm-assist-kit/skills/marp-slides/build.py`, `C:/tools/llm-assist-kit/skills/marp-slides/editable_pptx.py`, `C:/tools/llm-assist-kit/skills/marp-slides/example.md`, `C:/tools/llm-assist-kit/skills/marp-slides/marp.zip`, `C:/tools/llm-assist-kit/skills/marp-slides/theme.css`

### いつ使うか

スライド・プレゼン資料・発表資料の作成や修正を頼まれたとき。
スライドは [Marp](https://marp.app/) の Markdown ファイル (例 `slides/発表名.md`) として作ります。
ファイルの作成・修正は、ほかのファイルと同じ方法 (apply-patch スキルがあればそのパッチ) で行います。

### 新しく作るとき (最初の 1 回は slideinit もいっしょに)

スライドの Markdown を新しく作るパッチを出すときは、**同じ 1 つのコードブロックの中で、パッチより前に
`slideinit` を実行**するようにします。`slideinit` は、スライドのフォルダ (既定 `slides/`) に既定の画像
(表紙の背景 `assets/background.png`・ロゴ `assets/logo.png`)・テーマ (`assets/kit-slides.css`)・
VS Code のプレビュー用の設定 (`.vscode/settings.json`) をそろえる関数です (何度実行しても同じで、既にある画像は上書きしません)。

- apply-patch スキルのコマンドの 1 行目 (`$OutputEncoding = ...`) の次の行に `slideinit` を 1 行入れ、
  その後にいつものパッチ (`@'` 〜 `'@ | python ...`) を続けます。コードブロックは 1 つです。
- スライドを `slides/` 以外のフォルダに置くときは、`slideinit <フォルダ>` と書きます。
- 2 回目以降 (作ったスライドの修正、同じフォルダへのスライドの追加) は `slideinit` を付けず、パッチだけを出します。

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
slideinit
@'
*** Begin Patch
*** Add File: slides/発表名.md
+---
+marp: true
+theme: kit-slides
+paginate: true
+footer: "![logo](assets/logo.png)"
+---
+
+<!-- _class: cover -->
+
+![bg](assets/background.png)
+
+# 発表のタイトル
+
+〇〇部 △△課
+2026年11月25日
+
+---
+
+## スライドのタイトル
+
+- 要点 1
+- 要点 2
*** End Patch
'@ | python C:/tools/llm-assist-kit/ctx.py run -- python C:/tools/llm-assist-kit/skills/apply-patch/apply.py -f -
```

### スライドの形 (必ずこの形)

- **1 枚目は表紙**。背景画像の上、中央の横線の上側にタイトル、下側に部署名と日付 (すべて左寄せ)。
- **2 枚目以降**は、ヘッダー (スライドのタイトルのみ) とフッター (左端に「ページ数 / 総ページ数」、
  右端にロゴ画像) を、線で本文と区切ります。
- 見た目 (色・位置・線・ページ番号) はテーマ `kit-slides` が付けます。Markdown に `<style>` や
  位置を決める HTML を書かないでください (使ってよい HTML は、文字の色分けの `<span>` だけです)。

### 書き方

```markdown
---
marp: true
theme: kit-slides
paginate: true
footer: "![logo](assets/logo.png)"
---

<!-- _class: cover -->

![bg](assets/background.png)

# 発表のタイトル

〇〇部 △△課
2026年11月25日

---

## スライドのタイトル

- 要点 1
- 要点 2

---

## 次のスライドのタイトル

### 小見出し

本文
```

決まり:

1. 先頭のフロントマター (`marp` 〜 `footer`) はこのまま書きます。`footer` はロゴの画像で、全ページ右下に出ます。
2. 表紙は `<!-- _class: cover -->`、`![bg](assets/background.png)`、`# タイトル`、
   その下に部署名と日付を **改行で 2 行に並べた 1 つの段落** で書きます (間に空行を入れない)。
   表紙には `#` 以外の見出しや箇条書きを書きません。
3. 2 枚目以降は、各スライドの最初に **`## タイトル` を 1 つだけ** 書きます (これがヘッダーになります)。
   スライドの中の見出しは `###` 以下を使います (`#` や 2 つ目の `##` は使わない)。
4. スライドの区切りは `---` だけの行 (前後に空行) です。
5. 1 枚に詰め込みすぎないでください。目安は箇条書き 6 行、表 6 行程度まで。あふれる内容は複数のスライドに分けます。
6. 日付をユーザーが指定しなければ、今日の日付を `YYYY年M月D日` で書きます。部署名が分からなければ
   `〇〇部` のような仮の値を入れ、差し替えるよう一言添えます。
7. 背景やロゴにユーザー自身の画像を使う場合は、`assets/background.png` / `assets/logo.png` を
   その画像のパス (スライドの Markdown からの相対パス) に書き換えます。

### 文字の色分け (HTML の span)

- 文字の色を変えるときは、Markdown の中に `<span class="色">言葉</span>` と書きます。色は次の 5 つです。

  | 書き方 | 色 | 使い分けの例 |
  | --- | --- | --- |
  | `<span class="red">言葉</span>` | 赤 | いちばん伝えたいこと・注意・問題点 |
  | `<span class="blue">言葉</span>` | 青 | 新しい方式・提案・ポイント |
  | `<span class="green">言葉</span>` | 緑 | 良くなる点・効果・完了 |
  | `<span class="orange">言葉</span>` | オレンジ | 検討中・注意して見てほしい点 |
  | `<span class="gray">言葉</span>` | グレー | 補足・目立たせたくないもの |

- 太字にもするときは `**<span class="red">言葉</span>**` と書きます。`**言葉**` は黒の太字、`*言葉*` は斜体です。
- 色分けは 1 枚に 1〜3 か所までにし、同じ意味には同じ色を使います (多いと目立たなくなります)。
  見出し (`##` `###`) の中には使いません。
- `<span style="color: #d32f2f">` のように色を直接書くこともできますが、資料の色をそろえるため、上の 5 つを使います。
- 色分けの `<span>` 以外の HTML (`<div>`・`<style>`・`<font>` など) は使いません。

### 本文のレイアウト (2 枚目以降)

内容に合わせて、`## タイトル` の前に `<!-- _class: ... -->` を 1 行書くと、次のレイアウトにできます。
付けなければ 1 カラムです。

| クラス | レイアウト | 使う場面 |
| --- | --- | --- |
| `cols` | テキストの 2 カラム | 2 つのものの比較 (現行と新方式、メリットとデメリットなど) |
| `image-right` | 左にテキスト、右に画像 | 画面のイメージ、図、写真の説明 |
| `image-left` | 左に画像、右にテキスト | 同上 (`image-right` が続くときに左右を変える) |
| `table` | 1 カラムで、真ん中に大きな表 | スケジュール、一覧、比較表など、表が主役のスライド |
| `image` | 1 カラムで、真ん中に大きな画像 | 構成図、画面のスクリーンショットなど、画像が主役のスライド |
| `center` | 1 カラムで、ど真ん中に大きめのテキスト | まとめ、結論、伝えたい 1 つのメッセージ、お願いごと |

```markdown
---

<!-- _class: cols -->

## 現行と新方式の比較

### 現行

- 要点 1
- 要点 2

### 新方式

- 要点 1
- 要点 2

---

<!-- _class: image-right -->

## 画面のイメージ

- 説明 1
- 説明 2

![](assets/placeholder.svg)

---

<!-- _class: table -->

## 導入スケジュール

| 時期 | 内容 | 担当 |
| --- | --- | --- |
| 2027年1月 | 要件定義 | 業務改善課 |
| 2027年4月 | 試験運用 | 開発課 |

---

<!-- _class: image -->

## システム構成

![](assets/placeholder.svg)

構成図の説明 (1 行)

---

<!-- _class: center -->

## まとめ

### 伝えたいことを 1 行で

補足を 1 行で
```

- `cols` は **`###` 小見出しをちょうど 2 つ** 書きます。1 つ目の `###` から左のカラム、2 つ目の `###` から右のカラムになります。
  各カラムの中身は箇条書きか短い段落にし、左右の分量をそろえます。
- `image-right` / `image-left` は、テキストを先に書き、最後に **画像だけの行** `![](画像のパス)` を 1 つ書きます
  (画像は本文の高さに合わせて縮小されます)。テキストは本文の半分の幅しか無いので、1 行を短くし、5 行程度までにします。
- `table` は表を **1 つだけ** 書きます。表は本文の幅いっぱいに広がり、上下の真ん中に置かれます。
  表の前に `###` 小見出しを 1 つ書いてもかまいません。表は 8 行程度までにし、多ければスライドを分けます。
- `image` は **画像だけの行** `![](画像のパス)` を 1 つ書きます。画像は残りの高さいっぱいに拡大・縮小されます。
  画像の前に `###` 小見出し、後ろに 1 行の説明 (キャプション) を書いてもかまいません。
- `center` は文字が大きく中央ぞろえになります。`###` 小見出し 1 つ (いちばん伝えたいこと) と 1〜2 行の段落、
  または 3 行程度までの短い箇条書きにします。長い文章や表は書きません。
- 図 (流れ・構成・関係) で表せる画像は、下の「図を SVG で作る」で作って貼ります。
- 写真や画面のスクリーンショットなど、あなたが作れない画像がまだ無いときは、`assets/placeholder.svg` (仮の画像) を書き、
  差し替えるよう一言添えます (仮の画像のファイルは、書き出し (`slidepdf` / `slidepptx`) のときにコピーされます)。
- 画像を左右に置くために `![bg right](...)` や HTML は使いません (ヘッダーとフッターの線が崩れます)。

### 図を SVG で作る (フロー図・構成図など)

次のどちらかのときは、図を SVG ファイルとして作り、スライドに貼ります (作ってよいかを確認せず、そのまま作ります)。

- **ユーザーが図を求めたとき** (「フロー図を入れて」「構成図にして」など)。
- **図のほうが伝わるとあなたが判断したとき**。手順・業務の流れ、システムの構成やつながり、
  関係者の役割分担、スケジュールの流れ、比較の軸など、箇条書きだけでは関係が見えにくい内容です。
  箇条書きで十分なものまで図にはしません (目安は資料全体で 1〜3 枚)。

図を作ったときは、回答の説明に「〇〇のスライドに図を入れた」と一言添えます。

- 図は `slides/assets/<図の名前>.svg` (スライドの Markdown と同じフォルダの `assets/`) に、
  スライドと同じパッチの `*** Add File:` で作ります。スライドには `![](assets/<図の名前>.svg)` と書きます。
- 置き場所は `image` (真ん中に大きく)・`image-right` / `image-left` (テキストの横) のレイアウトにします。
- 大きさは置き場所に合わせ、`<svg>` に `width`・`height`・`viewBox` を同じ値で書きます (この大きさのまま表示されます)。
  - `image`: `width="1100" height="440" viewBox="0 0 1100 440"` (前後に `###` と説明を書くとき)
  - `image-right` / `image-left`: `width="560" height="480" viewBox="0 0 560 480"`
- 見た目はスライドに合わせます。
  - 文字: `font-family="Segoe UI, Meiryo, sans-serif"`、大きさは 20〜28 (小さすぎると読めません)、色は `#222222`
    (補足は `#666666`、強調は `#d32f2f`)
  - 箱: `<rect rx="10" fill="#f3f5f8" stroke="#b3b3b3" stroke-width="2"/>`。主役の箱だけ
    `fill="#e8eef6" stroke="#1f4e8c" stroke-width="3"` にします
  - 線と矢印: `stroke="#666666" stroke-width="3"`。矢印の先は `<polygon>` の三角形で描きます
    (PowerPoint で崩れないように `marker` は使いません)。戻りや補助の線は `stroke-dasharray="10 8"`
- SVG は自動で折り返さないので、文字は短くし、箱の幅を「文字数 × 文字の大きさ + 40」以上にします。
  2 行にするときは `<text>` を 2 つ書きます。文字を箱の真ん中に置くときは `text-anchor="middle"` を使い、
  縦の位置は `y` で決めます (`dominant-baseline` は使いません)。
- 使うのは `rect`・`line`・`polyline`・`polygon`・`circle`・`path`・`text` だけにします。
  `<style>`・`class`・`<foreignObject>`・`filter`・外部の画像やフォントは使いません。
- 見本: `C:/tools/llm-assist-kit/skills/marp-slides/assets/example-flow.svg` (見本のスライド `example.md` の「システム構成」で使っています)。
- PowerPoint (`slidepptx`) では、図は SVG の画像として入ります。PowerPoint で図を右クリックして
  「図形に変換」すると、箱や文字を個別に編集できると伝えてください。

### 書き出し

スライドのファイルを作ったら (または修正したら)、書き出すコマンドを示します
(`<スライドのパス>` は実際のパスに置き換える)。PDF は `slidepdf`、PowerPoint は `slidepptx` です。

```powershell
slidepdf "<スライドのパス>"
```

```powershell
slidepptx "<スライドのパス>"
```

- パスを省くと `slides/` の `*.md` をすべて書き出します。フォルダを指定するとその中の `*.md` を書き出します。
- 出力はスライドと同じ場所に、同じ名前で拡張子を `.pdf` / `.pptx` にしたファイルです。
- `slidepptx` の PowerPoint は、文字・箇条書き・番号・表が PowerPoint のテキストや表として編集でき、
  位置はテーマと同じになります (Python だけで作るので、Marp CLI・ブラウザ・ほかのソフトは不要)。
  この書き方 (上の決まり) から外れた Markdown や HTML は再現されません。文字の折り返し位置が PDF と
  1 文字ほど違うことがあると伝えてください。画像は SVG のまま入るので、PowerPoint 2016 以降で開くよう伝えてください。
- 書き出しのときも `slideinit` と同じ準備 (足りない画像・テーマ・VS Code の設定) をします。
  既にある画像は上書きされないので、同じ名前の画像を置けば差し替えられます。
- VS Code のプレビューで `theme: kit-slides` が「not recognized」と警告されるときは、`slideinit` を実行し、
  VS Code のウィンドウの再読み込みを案内してください。
- `slidepdf` などの関数が見つからないと言われたら、キットのフォルダで `python install.py` を実行して
  PowerShell を開き直すよう案内してください。関数を使わない場合は
  `python C:/tools/llm-assist-kit/ctx.py run -- python C:/tools/llm-assist-kit/skills/marp-slides/build.py "<スライドのパス>"` (PowerPoint は末尾に `--pptx`) でも書き出せます。
- Marp CLI は同梱の `marp.zip` の単体版を使うので、Node.js は不要です (Windows)。
  PDF の書き出しには Edge か Chrome を使います。
  「Marp CLI が見つかりません」と表示されたら (zip にその OS 用が無い場合)、Node.js のインストールを案内してください。

# プロジェクト: sample-project

## ディレクトリツリー

```text
sample-project/
├── config/
│   └── stage/
│       └── prod.local.toml
├── docs/
│   ├── draft10.md
│   └── TODO.md
├── src/
│   └── todo/
│       ├── __init__.py
│       ├── cli.py
│       ├── models.py
│       ├── scratch_a.py
│       └── storage.py
├── tests/
│   ├── fixtures/
│   │   └── tmp
│   └── test_storage.py
├── web/
│   ├── app.js
│   └── index.html
├── .gitignore
├── keep.bak
├── pyproject.toml
└── README.md
```

## ソースコード (16 ファイル)

### .gitignore

```gitignore
__pycache__/
.venv/
*.log
todo.json
```

### config/stage/prod.local.toml

```toml
# 5. * は / をまたがないので config/stage/ 以下は出力に入る
```

### docs/draft10.md

```markdown
# 9. ? は 1 文字だけなので draft10.md は出力に入る
```

### docs/TODO.md

```markdown
# 4. ルート固定ではないので docs/TODO.md は出力に入る
```

### keep.bak

```
2. !keep.bak で含め直されたファイル(出力に入る)
```

### pyproject.toml

```toml
[project]
name = "todo-cli"
version = "0.1.0"
description = "JSON ファイルに保存するシンプルな ToDo 管理ツール"
requires-python = ">=3.11"
dependencies = []

[project.scripts]
todo = "todo.cli:main"

[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"
```

### README.md

````markdown
# todo-cli

JSON ファイルに保存するシンプルな ToDo 管理ツールです。

## 使い方

```bash
todo add "牛乳を買う"
todo list
todo done 1
```

保存先は環境変数 `TODO_FILE` で変更できます(既定: `./todo.json`)。
````

### src/todo/__init__.py

```python
"""シンプルな ToDo 管理ツール"""

__version__ = "0.1.0"
```

### src/todo/cli.py

```python
from __future__ import annotations

import argparse
import os
from pathlib import Path

from todo.storage import TaskStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="todo")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add", help="タスクを追加")
    add.add_argument("title")
    sub.add_parser("list", help="タスク一覧")
    done = sub.add_parser("done", help="タスクを完了にする")
    done.add_argument("id", type=int)
    args = parser.parse_args(argv)

    store = TaskStore(Path(os.environ.get("TODO_FILE", "todo.json")))
    if args.command == "add":
        task = store.add(args.title)
        print(f"追加しました: #{task.id} {task.title}")
    elif args.command == "list":
        for task in store.load():
            mark = "x" if task.done else " "
            print(f"[{mark}] #{task.id} {task.title}")
    elif args.command == "done":
        task = store.complete(args.id)
        print(f"完了しました: #{task.id} {task.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### src/todo/models.py

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class Task:
    id: int
    title: str
    done: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Task:
        return cls(
            id=int(str(data["id"])),
            title=str(data["title"]),
            done=bool(data.get("done", False)),
            created_at=str(data.get("created_at", "")),
        )
```

### src/todo/scratch_a.py

```python
"""10. [0-9] に a は含まれないので出力に入る"""
```

### src/todo/storage.py

```python
from __future__ import annotations

import json
from pathlib import Path

from todo.models import Task


class TaskStore:
    """タスクを JSON ファイルに保存・読み込みする"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[Task]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [Task.from_dict(d) for d in data]

    def save(self, tasks: list[Task]) -> None:
        text = json.dumps([t.to_dict() for t in tasks], ensure_ascii=False, indent=2)
        self.path.write_text(text, encoding="utf-8")

    def add(self, title: str) -> Task:
        tasks = self.load()
        task = Task(id=max((t.id for t in tasks), default=0) + 1, title=title)
        tasks.append(task)
        self.save(tasks)
        return task

    def complete(self, task_id: int) -> Task:
        tasks = self.load()
        for task in tasks:
            if task.id == task_id:
                task.done = True
                self.save(tasks)
                return task
        raise KeyError(f"タスク {task_id} は存在しません")
```

### tests/fixtures/tmp

```
3. tmp という名前の「ファイル」。tmp/ はディレクトリ専用なので出力に入る
```

### tests/test_storage.py

```python
from pathlib import Path

import pytest
from todo.storage import TaskStore


def test_add_and_load(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "todo.json")
    store.add("牛乳を買う")
    store.add("本を返す")
    assert [t.title for t in store.load()] == ["牛乳を買う", "本を返す"]
    assert [t.id for t in store.load()] == [1, 2]


def test_complete(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "todo.json")
    task = store.add("牛乳を買う")
    store.complete(task.id)
    assert store.load()[0].done


def test_complete_missing(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        TaskStore(tmp_path / "todo.json").complete(99)
```

### web/app.js

```javascript
// todo.json を読み込んで一覧表示する
async function render() {
  const res = await fetch("../todo.json");
  const tasks = await res.json();
  const list = document.getElementById("tasks");
  for (const task of tasks) {
    const li = document.createElement("li");
    li.textContent = `${task.done ? "✅" : "⬜"} ${task.title}`;
    list.appendChild(li);
  }
}

render();
```

### web/index.html

```html
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>todo viewer</title>
</head>
<body>
  <h1>ToDo</h1>
  <ul id="tasks"></ul>
  <script src="app.js"></script>
</body>
</html>
```
