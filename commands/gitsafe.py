"""git の「dubious ownership」(フォルダの所有者が自分でない) への対処 (commands/ の共通部品)

Box や OneDrive、ネットワークドライブのフォルダは所有者が Everyone などになっていて、
git が「detected dubious ownership」と言って、そのフォルダのリポジトリを使わなくなる。
git config --global --add safe.directory <フォルダ> で、そのフォルダだけを信頼すると直る。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

MARKER = "dubious ownership"

HINT = (
    "git が「dubious ownership」(フォルダの所有者が自分ではない) と言って、"
    "このフォルダのリポジトリを使えません。\n"
    "Box や OneDrive などのフォルダで起きます。このフォルダで `init` を実行すると、"
    "このフォルダを git の safe.directory に登録して直します。"
)


def rev_parse(root: Path) -> tuple[int, str]:
    """git rev-parse --is-inside-work-tree の (終了コード, 標準エラー)"""
    r = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=root, capture_output=True
    )
    return r.returncode, r.stderr.decode("utf-8", errors="replace")


def is_dubious(stderr: str) -> bool:
    return MARKER in stderr


def safe_directory(stderr: str, root: Path) -> str:
    """git のエラーが示す safe.directory の値 (無ければ root を / 区切りにしたもの)"""
    m = re.search(r"safe\.directory\s+'([^'\n]+)'", stderr)
    return m.group(1) if m else root.as_posix()


def add_safe_directory(path: str) -> int:
    return subprocess.run(
        ["git", "config", "--global", "--add", "safe.directory", path]
    ).returncode
