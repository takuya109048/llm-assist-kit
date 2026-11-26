"""新しいプロジェクトのフォルダを準備する (PowerShell の関数 init から使う)

使い方:
    init                # 今いるフォルダに AGENTS.md・.ctxignore・.gitignore を作り、git init する
    init my-project     # フォルダを指定する (無ければ作る)
    init --no-git       # git init しない

すでにあるファイルは上書きしない (そのまま残す)。すでに git のリポジトリなら git init しない。
"""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import sys
from pathlib import Path

# AGENTS.md の既定の内容。どのプロジェクトでもそのまま効く具体的なルールを入れておき、
# プロジェクト固有のこと (概要・コマンド) だけを書き足す形にする。
# 参考: 広く共有されている Karpathy 由来の CLAUDE.md の 4 原則 (書く前に考える・
# シンプルに・必要な箇所だけ変える・ゴールを確かめる) と、GitHub の 2,500 リポジトリの
# 分析 (正確なコマンドと「常に / 先に確認 / しない」の境界が効く)。
# <!-- --> は ctx でコピーするときに取り除かれる、人向けのメモ
AGENTS_MD = """\
# AGENTS.md

## プロジェクト

<!-- 何をするプロジェクトか、言語とバージョン・主なフレームワークを 1〜3 行で。
例: 社内の請求データを集計する CLI。Python 3.12 / pandas 2 / pytest -->

## コマンド

<!-- そのまま実行できる形で。使わない行は消す -->
- セットアップ:
- テスト:
- テストを 1 つだけ:
- リント / フォーマット:

## 進め方

- 書く前に考える: 前提を明示する。解釈が複数あるときは黙って 1 つに決めず、選択肢を示して質問する。
- シンプルに: 依頼を満たす最小限のコードにする。頼まれていない機能・設定項目・抽象化を足さない。
- 必要な箇所だけ変える: 関係のないリファクタリング・整形・コメントの削除をしない。片付けるのは自分の変更で不要になったものだけ。
- ゴールを確かめる: 何ができたら完了かを先に決め、テストや実行結果で確かめてから完了とする。
- 原因を直す: エラーは症状を隠さず根本原因を直す。原因が分からないときは推測で直さず、調べる手順を示す。

## コード

- 既存のコードの書き方・命名・使っているライブラリに合わせる。
- 省略しない: 「...」「以下同様」や TODO だけの仮実装にせず、そのまま動くコードを示す。
- 確かめていないファイル・関数・API を前提にしない。

## 境界

- 常に: 変更後はテストとリントで確かめる (自分で実行できないときは、実行するコマンドを示す)。
- 先に確認: 依存関係の追加、ファイルの削除や移動、公開 API・データベースのスキーマの変更、大きな設計の変更。
- しない: 秘密情報 (API キー・パスワード・.env の中身) を書く・表示する。テストを消したり弱めたりして通す。頼まれていない push や履歴の書き換え。

## 回答

- 日本語で、結論から簡潔に答える。変更はファイルのパスと変更箇所が分かる形で示す。
- このファイルがプロジェクトのソースと一緒にチャットに貼られたときは、「了解しました」とだけ返して次の依頼を待つ。
"""

CTXIGNORE = """\
# ctx でコピーするときに除外するファイル (.gitignore と同じ書式)
# .gitignore で無視しているファイルや node_modules・.venv などは、ここに書かなくても除外されます。
#
# 例:
# docs/
# *.csv
# tests/fixtures/**
"""

GITIGNORE = """\
# OS / エディタ
.DS_Store
Thumbs.db
desktop.ini
.vscode/
.idea/

# 秘密情報
.env
.env.*

# Python
__pycache__/
*.py[cod]
.venv/
venv/
*.egg-info/
.pytest_cache/
.ruff_cache/

# Node.js
node_modules/

# ビルド結果
build/
dist/
"""

FILES = [
    ("AGENTS.md", AGENTS_MD),
    (".ctxignore", CTXIGNORE),
    (".gitignore", GITIGNORE),
]


def use_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            try:
                stream.reconfigure(encoding="utf-8")
            except ValueError:
                pass


def is_git_repo(root: Path) -> bool:
    r = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=root, capture_output=True
    )
    return r.returncode == 0


def main(argv: list[str]) -> int:
    use_utf8_output()
    ap = argparse.ArgumentParser(
        prog="init",
        description="新しいプロジェクトのフォルダに AGENTS.md・.ctxignore・.gitignore を作り、"
        "git init します。すでにあるファイルは上書きしません。",
    )
    ap.add_argument(
        "dir",
        nargs="?",
        default=".",
        help="プロジェクトのフォルダ (既定: 今いるフォルダ)",
    )
    ap.add_argument("--no-git", action="store_true", help="git init しない")
    args = ap.parse_args(argv)

    root = Path(args.dir).resolve()
    if root.exists() and not root.is_dir():
        print(f"エラー: フォルダではありません: {root}")
        return 1
    root.mkdir(parents=True, exist_ok=True)
    print(f"プロジェクトのフォルダ: {root}")

    for name, content in FILES:
        path = root / name
        if path.exists():
            print(f"  {name:<11} すでにあるので、そのままにしました")
            continue
        # 改行は LF のまま書く (git の設定に任せる)。日本語は UTF-8 (BOM なし)
        path.write_bytes(content.encode("utf-8"))
        print(f"  {name:<11} 作りました")

    if not args.no_git:
        if not shutil.which("git"):
            print("エラー: git が見つかりません (--no-git で git init を省けます)")
            return 1
        if is_git_repo(root):
            print(
                f"  {'.git':<11} すでに git のリポジトリなので、git init しませんでした"
            )
        else:
            r = subprocess.run(["git", "init", "-q"], cwd=root)
            if r.returncode != 0:
                return r.returncode
            print(f"  {'.git':<11} git init しました")

    print("\nAGENTS.md にプロジェクトの概要や規約を書いてから、ctx で使ってください。")
    if not args.no_git:
        print("最初のコミットは `addcommit 最初のコミット` でできます。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
