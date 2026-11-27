"""marp-slides の見本 (examples/marp-slides-example.pptx) を作り直す

使い方 (標準ライブラリのみ。どの OS でも可):
    python tools/build_examples.py            # 見本の元が変わっていれば作り直す
    python tools/build_examples.py --force    # 変わっていなくても作り直す
    python tools/build_examples.py --check    # 古ければ終了コード 1

PPTX は作るたびに zip の日時が変わるので、中身ではなく元で古さを判断する。
見本の元 (example.md、テーマ、画像、書き出しのスクリプト) の SHA-256 を
examples/marp-slides-example.inputs に記録する。tests/test_example.py が、これと
今の元が一致すること (見本が古くないこと) を確かめる。
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
SKILL = KIT / "skills" / "marp-slides"
EXAMPLE = SKILL / "example.md"
EXAMPLES = KIT / "examples"
PPTX = EXAMPLES / "marp-slides-example.pptx"
INPUTS_FILE = EXAMPLES / "marp-slides-example.inputs"
TEXT_SUFFIXES = {".md", ".css", ".svg", ".py"}


def input_files() -> list[Path]:
    """見本の見た目を決めるファイル"""
    return [
        EXAMPLE,
        SKILL / "theme.css",
        SKILL / "build.py",
        SKILL / "editable_pptx.py",
        *sorted(p for p in (SKILL / "assets").iterdir() if p.is_file()),
    ]


def file_digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix in TEXT_SUFFIXES:
        # Windows の checkout (autocrlf) でも同じになるよう改行をそろえる
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def inputs_text() -> str:
    """見本の元の一覧と SHA-256 (examples/marp-slides-example.inputs の中身)"""
    lines = [
        "# examples/marp-slides-example.pptx を作った元 (tools/build_examples.py が書く)",
    ]
    for path in input_files():
        lines.append(f"{file_digest(path)}  {path.relative_to(KIT).as_posix()}")
    return "\n".join(lines) + "\n"


def is_up_to_date() -> bool:
    if not (PPTX.is_file() and INPUTS_FILE.is_file()):
        return False
    recorded = INPUTS_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
    return recorded == inputs_text()


def build() -> None:
    script = str(SKILL / "build.py")
    subprocess.run(
        [sys.executable, script, str(EXAMPLE), "--pptx", "-o", str(PPTX)], check=True
    )
    INPUTS_FILE.write_text(inputs_text(), encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="古ければ終了コード 1")
    group.add_argument("--force", action="store_true", help="変わっていなくても作る")
    args = ap.parse_args()

    if is_up_to_date() and not args.force:
        print("見本は最新です")
        return 0
    if args.check:
        print(
            "見本が古くなっています: python tools/build_examples.py で作り直してください"
        )
        return 1
    build()
    print(f"作り直しました: {PPTX.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
