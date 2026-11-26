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

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))

from ctx import DEFAULT_PROMPT  # noqa: E402  (キットの ctx.py の内蔵プロンプト)

AGENTS_MD = (
    DEFAULT_PROMPT
    + """
# プロジェクトの概要
- (このプロジェクトの目的を書く)
- (使っている言語・フレームワーク・主なライブラリを書く)

# 規約
- (コーディング規約、テストの実行方法、回答の形式などを書く)
"""
)

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
