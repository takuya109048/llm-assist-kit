"""git の変更内容 (status / stat / 差分) をまとめて表示する (git-diff スキル用)

使い方: python diff.py [パス ...]
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys


def git(*args: str) -> tuple[int, str]:
    r = subprocess.run(["git", *args], capture_output=True)
    out = (r.stdout + r.stderr).decode("utf-8", errors="replace")
    return r.returncode, out.replace("\r\n", "\n").rstrip("\n")


def section(title: str, body: str) -> None:
    print(f"===== {title} =====")
    print(body if body.strip() else "(なし)")
    print()


def use_utf8_output() -> None:
    """出力を UTF-8 にする (英語版 Windows でパイプに出すと cp1252 になり、日本語で落ちるため)"""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            try:
                stream.reconfigure(encoding="utf-8")
            except ValueError:
                pass


def main(argv: list[str]) -> int:
    use_utf8_output()
    if not shutil.which("git"):
        print("git が見つかりません")
        return 1
    code, out = git("rev-parse", "--is-inside-work-tree")
    if code != 0:
        print("git リポジトリではありません")
        return 1
    paths = ["--", *argv] if argv else []
    section("git status --short", git("status", "--short", *paths)[1])
    section("git diff --stat (未ステージ)", git("diff", "--stat", *paths)[1])
    section(
        "git diff --stat (ステージ済み)", git("diff", "--cached", "--stat", *paths)[1]
    )
    section("git diff (未ステージ)", git("diff", *paths)[1])
    section("git diff (ステージ済み)", git("diff", "--cached", *paths)[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
