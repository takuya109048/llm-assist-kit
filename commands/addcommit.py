"""git add -A と git commit をまとめて行う (PowerShell の関数 addcommit から使う)

使い方:
    addcommit メッセージ            # git add -A のあと git commit -m "メッセージ"
    addcommit 修正 その2             # 空白で区切った語は 1 つのメッセージにつなげる
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys


def use_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            try:
                stream.reconfigure(encoding="utf-8")
            except ValueError:
                pass


def main(argv: list[str]) -> int:
    use_utf8_output()
    message = " ".join(argv).strip()
    if not message or message in ("-h", "--help"):
        print("使い方: addcommit <コミットメッセージ>")
        print("  git add -A のあと、そのメッセージで git commit します。")
        return 0 if message else 2
    if not shutil.which("git"):
        print("エラー: git が見つかりません")
        return 1
    code = subprocess.run(["git", "add", "-A"]).returncode
    if code != 0:
        return code
    return subprocess.run(["git", "commit", "-m", message]).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
