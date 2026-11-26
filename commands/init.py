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

import gitsafe  # commands/gitsafe.py (このスクリプトと同じフォルダ)

# AGENTS.md の既定の内容。llm-assist-kit での開発の流れ (ctx で貼る → パッチを出す →
# ctx run で結果を貼る → addcommit / reset) と、どのプロジェクトでも効く具体的なルールを入れ、
# プロジェクト固有のこと (概要・コマンド) だけを書き足す形にする。
# ルールの参考: Karpathy 由来の CLAUDE.md の 4 原則 (書く前に考える・シンプルに・
# 必要な箇所だけ変える・ゴールを確かめる) と、GitHub の agents.md の分析
# (正確なコマンドと「常に / 先に確認 / しない」の境界が効く)。
# <!-- --> は ctx でコピーするときに取り除かれる、人向けのメモ
AGENTS_MD = """\
# AGENTS.md

<!-- llm-assist-kit の ctx でチャットの LLM に貼る指示。「プロジェクト」と「コマンド」を書き足して使う。
同じ指摘を 2 回したら、そのルールを足す。このコメントは ctx でコピーするときに取り除かれる。 -->

## プロジェクト

<!-- 何をするプロジェクトか、言語とバージョン・主なフレームワークを 1〜3 行で。
例: 社内の請求データを集計する CLI。Python 3.12 / pandas 2 / pytest -->

## コマンド

<!-- そのまま実行できる形で。使わない行は消す -->
- テスト:
- テストを 1 つだけ:
- リント / フォーマット:

## 開発の流れ (llm-assist-kit)

あなたはチャットの LLM で、ファイルを読み書きできず、コマンドも実行できない。手を動かすのはユーザーで、次の流れで進める。

1. ユーザーが `ctx` で、この指示・スキル・ディレクトリツリー・全ソースを貼る。貼られた内容が今のファイルの状態。
2. あなたは変更をパッチのコマンドで出す (apply-patch スキルの形)。ユーザーが PowerShell で実行する。
3. 確かめが要るときは、テストなどのコマンドを `run --` 付きで示す (「# スキル」欄の形)。結果は「## 実行結果」として貼られる。
4. うまくいったらユーザーが `addcommit <メッセージ>` でコミットし、やり直すときは `reset` で最後のコミットに戻す。

- 1 回の回答は 1 つの目的に絞り、パッチと確かめのコマンドを出したら止まる。大きな依頼は手順に分け、最初の手順だけを出す。
- 実行結果で決まることは、結果が貼られるまで決めつけない。
- 貼られていないファイルが必要なときは、中身を推測せず、`ctx -i "<パス>" --no-prompt --no-skills --no-tree` で貼ってもらう。
- 会話が長くなってファイルの今の内容があいまいになったら、`ctx` で貼り直してもらう。
- 変更がひと区切りついたら、コミットのコマンドを `addcommit <変更の要約>` の形で 1 行示す。

## 進め方

- 書く前に考える: 前提を明示する。解釈が複数あるときは黙って 1 つに決めず、選択肢を示して質問する。
- シンプルに: 依頼を満たす最小限のコードにする。頼まれていない機能・設定項目・抽象化を足さない。
- 必要な箇所だけ変える: 関係のないリファクタリング・整形・コメントの削除をしない。既存の書き方・命名・ライブラリに合わせる。
- ゴールを確かめる: 何ができたら完了かを先に決め、テストや実行結果で確かめる。
- 原因を直す: エラーは症状を隠さず根本原因を直す。原因が分からないときは、調べるためのコマンドを示す。

## 境界

- 先に確認: 依存関係の追加、ファイルの削除や移動、公開 API・データベースのスキーマの変更、大きな設計の変更。
- しない: 秘密情報 (API キー・パスワード・.env の中身) をコードやコマンドに書く。テストを消したり弱めたりして通す。
  `git push`・履歴の書き換え・`reset` など、元に戻せないコマンドを頼まれずに出す。

## 回答

- 日本語で、結論から簡潔に答える。
- このファイルがプロジェクトのソースと一緒に貼られたときは、「了解しました」とだけ返して次の依頼を待つ。
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
        code, err = gitsafe.rev_parse(root)
        if code == 0:
            print(
                f"  {'.git':<11} すでに git のリポジトリなので、git init しませんでした"
            )
        elif not gitsafe.is_dubious(err):
            r = subprocess.run(["git", "init", "-q"], cwd=root)
            if r.returncode != 0:
                return r.returncode
            print(f"  {'.git':<11} git init しました")
            code, err = gitsafe.rev_parse(root)
        if code != 0 and gitsafe.is_dubious(err):
            # Box などのフォルダは所有者が自分でないため、git が使ってくれない
            path = gitsafe.safe_directory(err, root)
            if gitsafe.add_safe_directory(path) != 0:
                print(err.rstrip())
                return 1
            print(
                f"  {'.git':<11} フォルダの所有者が自分でないため、git の safe.directory に"
                f"登録しました\n              ({path})"
            )

    print("\nAGENTS.md にプロジェクトの概要や規約を書いてから、ctx で使ってください。")
    if not args.no_git:
        print("最初のコミットは `addcommit 最初のコミット` でできます。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
