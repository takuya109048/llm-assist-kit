"""git reset --hard HEAD と git clean -fd をまとめて行う (PowerShell の関数 reset から使う)

使い方:
    reset       # 消える内容を表示し、確認してから実行
    reset -y    # 確認せずに実行

コミットしていない変更と、git で管理していないファイル・フォルダを消して、
最後のコミットの状態に戻す。.gitignore で無視しているファイル (.venv など) は残る。
"""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import sys

import gitsafe  # commands/gitsafe.py (このスクリプトと同じフォルダ)


def use_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            try:
                stream.reconfigure(encoding="utf-8")
            except ValueError:
                pass


# 日本語のファイル名を "\346\226..." ではなくそのまま表示する
GIT = ["git", "-c", "core.quotepath=false"]


def git(*args: str) -> tuple[int, str]:
    r = subprocess.run([*GIT, *args], capture_output=True)
    out = (r.stdout + r.stderr).decode("utf-8", errors="replace")
    return r.returncode, out.replace("\r\n", "\n").rstrip("\n")


def confirm(question: str) -> bool:
    try:
        answer = input(question)
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


def main(argv: list[str]) -> int:
    use_utf8_output()
    ap = argparse.ArgumentParser(
        prog="reset",
        description="git reset --hard HEAD と git clean -fd をまとめて行います。",
    )
    ap.add_argument("-y", "--yes", action="store_true", help="確認せずに実行する")
    args = ap.parse_args(argv)

    if not shutil.which("git"):
        print("エラー: git が見つかりません")
        return 1
    code, out = git("rev-parse", "--is-inside-work-tree")
    if code != 0:
        print(gitsafe.HINT if gitsafe.is_dubious(out) else out)
        return code

    _, changed = git("status", "--short", "--untracked-files=no")
    _, removed = git("clean", "-nd")
    if not changed and not removed:
        print("元に戻す変更はありません")
        return 0

    if changed:
        print("元に戻すファイル (git reset --hard HEAD):")
        print("\n".join(f"  {line}" for line in changed.split("\n")))
    if removed:
        print("削除するファイル・フォルダ (git clean -fd):")
        print("\n".join(f"  {line}" for line in removed.split("\n")))
    if not args.yes and not confirm(
        "これらの変更をすべて破棄します。元に戻せません。よろしいですか? [y/N]: "
    ):
        print("中止しました")
        return 1

    code = subprocess.run([*GIT, "reset", "--hard", "HEAD"]).returncode
    if code != 0:
        return code
    return subprocess.run([*GIT, "clean", "-fd"]).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
