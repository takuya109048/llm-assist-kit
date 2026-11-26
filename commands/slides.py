"""スライド (marp-slides スキル) の準備と書き出し (PowerShell の関数 slideinit / slidepdf / slidepptx から使う)

使い方:
    slideinit                 # slides/ に一式 (既定の画像・テーマ・VS Code の設定) をそろえる
    slideinit 資料            # フォルダを指定する
    slidepdf                  # slides/ の *.md をすべて PDF にする
    slidepdf slides/発表.md   # ファイル (またはフォルダ) を指定する
    slidepptx                 # 文字を編集できる PowerPoint (PPTX) にする

中身はキットの skills/marp-slides/build.py。slideinit は何度実行しても同じで、
既にある画像は上書きしない (同じ名前の画像を置けば差し替えられる)。
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType

KIT = Path(__file__).resolve().parent.parent
BUILD = KIT / "skills" / "marp-slides" / "build.py"
DEFAULT_FOLDER = "slides"
COMMANDS = {
    "init": "slideinit",
    "pdf": "slidepdf",
    "pptx": "slidepptx",
}


def load_build() -> ModuleType:
    spec = importlib.util.spec_from_file_location("marp_slides_build", BUILD)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def use_utf8_output() -> None:
    """日本語のパスやメッセージが化けたりエラーにならないように、出力を UTF-8 にする"""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            try:
                stream.reconfigure(encoding="utf-8")
            except ValueError:
                pass


def slide_files(targets: list[str]) -> list[Path]:
    """書き出す Markdown (指定が無ければ slides/ の *.md、フォルダならその中の *.md)"""
    if not targets:
        folder = Path(DEFAULT_FOLDER)
        return sorted(folder.glob("*.md")) if folder.is_dir() else []
    files: list[Path] = []
    for target in targets:
        path = Path(target)
        if path.is_dir():
            files.extend(sorted(path.glob("*.md")))
        else:
            files.append(path)
    return files


def init(folder: str, build: ModuleType) -> int:
    path = Path(folder).resolve()
    for message in build.prepare_folder(path, Path.cwd().resolve()):
        print(message)
    print(f"スライドのフォルダを準備しました: {path}")
    return 0


def export(fmt: str, targets: list[str], build: ModuleType) -> int:
    files = slide_files(targets)
    if not files:
        where = ", ".join(targets or [DEFAULT_FOLDER])
        print(f"スライドの Markdown が見つかりません: {where}", file=sys.stderr)
        return 1
    failed = 0
    for path in files:
        if build.main([str(path), f"--{fmt}"]) != 0:
            failed += 1
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    use_utf8_output()
    if not argv or argv[0] not in COMMANDS:
        print(f"使い方: slides.py {{{'|'.join(COMMANDS)}}} ...", file=sys.stderr)
        return 2
    command, rest = argv[0], argv[1:]
    ap = argparse.ArgumentParser(prog=COMMANDS[command])
    if command == "init":
        ap.description = (
            "スライドのフォルダに一式 (既定の画像・テーマ・VS Code の設定) をそろえる"
        )
        ap.add_argument(
            "folder", nargs="?", default=DEFAULT_FOLDER, help="フォルダ (既定: slides)"
        )
        args = ap.parse_args(rest)
        return init(args.folder, load_build())
    kind = "PDF" if command == "pdf" else "文字を編集できる PowerPoint (PPTX)"
    ap.description = f"スライドを {kind} にする"
    ap.add_argument(
        "targets",
        nargs="*",
        help="Markdown のファイルかフォルダ (既定: slides/ の *.md すべて)",
    )
    args = ap.parse_args(rest)
    return export(command, args.targets, load_build())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
