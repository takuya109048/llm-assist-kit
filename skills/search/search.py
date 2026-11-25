"""プロジェクト内を検索して `パス:行番号: 内容` で表示する (search スキル用)

使い方: python search.py PATTERN [フォルダ ...] [-F] [-i] [-g GLOB] [-C N] [--max N]
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "dist",
    "build",
}


def list_files(base: Path) -> list[Path]:
    """git 管理下なら .gitignore を尊重して列挙、そうでなければ走査する"""
    if shutil.which("git"):
        r = subprocess.run(
            ["git", "-C", str(base), "ls-files", "-z", "--cached", "--others"]
            + ["--exclude-standard"],
            capture_output=True,
        )
        if r.returncode == 0:
            names = r.stdout.decode("utf-8", errors="replace").split("\0")
            return sorted(
                (base / n for n in names if n and (base / n).is_file()),
                key=lambda p: p.as_posix().lower(),
            )
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        files += [Path(dirpath) / f for f in filenames]
    return sorted(files, key=lambda p: p.as_posix().lower())


def read_lines(path: Path) -> list[str] | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None  # バイナリ
    for enc in ("utf-8-sig", "cp932"):
        try:
            return data.decode(enc).splitlines()
        except UnicodeDecodeError:
            continue
    return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="search.py")
    ap.add_argument("pattern")
    ap.add_argument("paths", nargs="*", default=["."])
    ap.add_argument("-F", "--fixed", action="store_true", help="正規表現ではなく文字列")
    ap.add_argument("-i", "--ignore-case", action="store_true")
    ap.add_argument("-g", "--glob", action="append", default=[], help="対象ファイル")
    ap.add_argument("-C", "--context", type=int, default=0, help="前後の行数")
    ap.add_argument("--max", type=int, default=200, help="最大件数")
    args = ap.parse_args(argv)

    source = re.escape(args.pattern) if args.fixed else args.pattern
    try:
        regex = re.compile(source, re.IGNORECASE if args.ignore_case else 0)
    except re.error as e:
        print(f"正規表現が不正です: {e}")
        return 2

    cwd = Path.cwd()
    hits = 0
    hit_files = 0
    truncated = False
    for base in args.paths:
        for path in list_files(Path(base)):
            try:
                rel = path.resolve().relative_to(cwd.resolve()).as_posix()
            except ValueError:
                rel = path.as_posix()
            if args.glob and not any(
                fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(path.name, g)
                for g in args.glob
            ):
                continue
            lines = read_lines(path)
            if lines is None:
                continue
            matched = [i for i, line in enumerate(lines) if regex.search(line)]
            if not matched:
                continue
            hit_files += 1
            shown: set[int] = set()
            for i in matched:
                if hits >= args.max:
                    truncated = True
                    break
                hits += 1
                lo, hi = max(0, i - args.context), min(len(lines), i + args.context + 1)
                if args.context and shown and lo > max(shown) + 1:
                    print("--")
                for j in range(lo, hi):
                    if j in shown:
                        continue
                    shown.add(j)
                    sep = ":" if j == i or j in matched else "-"
                    print(f"{rel}{sep}{j + 1}{sep} {lines[j].rstrip()[:300]}")
            if truncated:
                break
        if truncated:
            break

    if hits == 0:
        print(f"見つかりませんでした: {args.pattern}")
        return 1
    note = f" (最大 {args.max} 件で打ち切り)" if truncated else ""
    print(f"\n{hits} 件 / {hit_files} ファイル{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
