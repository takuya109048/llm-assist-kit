# 開発者向けメモ

キットを開発・リリースする人向けです。配布用の zip には入れません
(`tools/build_release.py` の `DEV_ONLY`)。

## 開発の準備とチェック

開発ルールは [CLAUDE.md](CLAUDE.md) を参照 (pip + venv、pytest、ruff、pyrefly)。

```powershell
python -m venv .venv
.venv\Scripts\activate          # macOS / Linux: source .venv/bin/activate
pip install -e ".[dev]"
ruff check . ; ruff format --check . ; pyrefly check ; pytest
```

GitHub Actions で Windows / macOS / Linux × Python 3.11 / 3.13 を実行します。
Windows では実際のクリップボードへ書き込み、読み戻して日本語・絵文字が化けないことを確認します。

## 同梱の実行ファイル (zip) の作り直し

- `skills/apply-patch/apply_patch.zip`: `python tools/build_apply_patch.py` (Linux で、Rust と mingw-w64 が必要。
  ビルド元のコミットは zip の `BUILD_INFO.txt` に記録されます)
- `skills/marp-slides/marp.zip`: `python tools/build_marp_zip.py` (`--version v4.5.1` で版を指定、
  `--targets windows-x86_64,linux-x86_64` で対象を追加。取得したファイルは公開されている SHA-256 と照合します)
- どちらも、ライセンス文だけを作り直すときは `--licenses-only` を付けます (下記)

## 同梱しているソフトのライセンス文

- `THIRD_PARTY_LICENSES.txt` は `tools/build_apply_patch.py` と `tools/build_marp_zip.py` が作ります。
  組み込まれた部品を、apply_patch は `cargo tree` (通常の依存。ビルド用・開発用・proc-macro を除く) で、
  Marp CLI は同じ版の `package-lock.json` (実行時の依存と、rollup で取り込まれる依存) でたどり、
  各部品に入っているライセンスファイルを集めます。ライセンスファイルが無い部品は、末尾の付録に
  SPDX のライセンスの原文を載せます
- 実行ファイルを変えずにライセンス文だけ作り直す: `python tools/build_apply_patch.py --licenses-only`
  (`BUILD_INFO.txt` のコミットと Rust の版を使う。Linux で mingw-w64 が必要)、
  `python tools/build_marp_zip.py --licenses-only` (`BUILD_INFO.txt` の版を使う)。どちらも git が必要です

## スライドの見本

- 見本の PPTX (`examples/marp-slides-example.pptx`) は、元 (`example.md`・テーマ・画像・書き出しのスクリプト) を
  変えたら `python tools/build_examples.py` で作り直します。元の SHA-256 を
  `examples/marp-slides-example.inputs` に記録し、見本が古いとテストが失敗します
- 編集できる PPTX の各段落・表・画像の位置と、入りきらない本文を小さくしたときの位置は、
  Chromium で描いた Marp の HTML と一致することをテストで確かめています

## リリース

1. `pyproject.toml` の `version` を上げ、[CHANGELOG.md](CHANGELOG.md) のいちばん上にその版の節
   (`## v<版> (<日付>)`) を書いて main に入れる。この節がリリースの説明になります
2. GitHub の Actions で **Release** を選び、**Run workflow** で版 (例 `v0.1.0`) を入れて実行する。
   main の最新のコミットにタグを付け、`tools/build_release.py` が作った配布用の zip と
   CHANGELOG のその版の節を説明にしてリリースを作ります
   (手元で zip だけ作るときは `python tools/build_release.py v0.1.0`。`dist/` にできます)
3. 既にあるリリースの zip を作り直すときは、**Run workflow** で版を入れ、**rebuild** に印を付けます。
   その版のタグのファイルから zip を作り直して置き換えます (zip に入れないものは今の決まりに従います)

配布用の zip には、開発用のもの (`tests/`・`tools/`・`.github/`・`examples/`・`CLAUDE.md`・
`DEVELOPMENT.md`・`.gitignore`) を入れません。
