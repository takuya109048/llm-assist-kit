"""Marp のスライド (Markdown) を、このスキルのテーマで PDF / HTML / PPTX にする

使い方:
    python build.py slides.md            # slides.pdf を作る
    python build.py slides.md --html     # slides.html を作る
    python build.py slides.md --pptx     # 文字を編集できる slides.pptx を作る
    python build.py slides.md -o out/deck.pdf

- テーマ (theme.css) はこのスキルのものを使う (Markdown では `theme: kit-slides`)
- スライドと同じフォルダの assets/ に、表紙の背景 (background.svg)・ロゴ (logo.svg)・
  仮の画像 (placeholder.svg) が無ければ既定の画像をコピーする。既にあるファイルは上書きしないので、
  同じ名前の画像を置けば差し替えられる
- Marp CLI は、同じフォルダの marp.zip に入っている単体版 (Node.js 不要) を
  .bin/ に取り出して使う。zip にこの OS 用が無ければ、`marp` コマンド、
  `npx @marp-team/marp-cli` (Node.js が必要) の順に探す
- PDF の書き出しには Chrome か Edge (Windows には標準で入っている) が必要
- --pptx は Marp CLI を使わず、editable_pptx.py (標準ライブラリだけ) で
  Markdown から直接 PPTX を作る。文字・箇条書き・表を PowerPoint で編集でき、
  位置と大きさはテーマ (theme.css) の寸法に合わせる。Chrome / Edge / LibreOffice は不要
  (各スライドを画像にした PPTX は作らない。--pptx-editable は --pptx と同じ)
- VS Code (Marp for VS Code) のプレビューでも kit-slides テーマを使えるように、テーマを
  スライドの assets/kit-slides.css にコピーし、ワークスペースの .vscode/settings.json の
  markdown.marp.themes に登録する (拡張機能はワークスペースの中のテーマしか使えないため)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path
from types import ModuleType

SKILL_DIR = Path(__file__).resolve().parent
THEME = SKILL_DIR / "theme.css"
DEFAULT_ASSETS = SKILL_DIR / "assets"
ASSET_FILES = ["background.svg", "logo.svg", "placeholder.svg"]
ZIP_PATH = SKILL_DIR / "marp.zip"  # tools/build_marp_zip.py で作る
CACHE_DIR = SKILL_DIR / ".bin"  # zip から取り出した実行ファイルの置き場 (git 管理外)
MARP_PACKAGE = "@marp-team/marp-cli"
FORMATS = ["pdf", "html", "pptx"]
KIT_DIR = SKILL_DIR.parent.parent
# Marp for VS Code のプレビュー用に、スライドの assets/ に置くテーマのコピー
VSCODE_THEME = "kit-slides.css"
VSCODE_THEMES_KEY = "markdown.marp.themes"
# PPTX は editable_pptx.py で Markdown から直接作る (文字を編集できる。Marp CLI は使わない)
EDITABLE_MODULE = SKILL_DIR / "editable_pptx.py"


def copy_default_assets(slides: Path) -> list[Path]:
    """スライドのフォルダの assets/ に、無い既定画像だけをコピーする"""
    dest_dir = slides.parent / "assets"
    copied = []
    for name in ASSET_FILES:
        dest = dest_dir / name
        if dest.exists():
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DEFAULT_ASSETS / name, dest)
        copied.append(dest)
    return copied


def copy_theme(slides: Path) -> Path | None:
    """テーマ (theme.css) をスライドの assets/kit-slides.css にコピーする

    VS Code のプレビューで kit-slides テーマを使うため。キットのテーマが変わったら
    上書きする (内容が同じならそのまま)。コピーしたらそのパスを返す。
    """
    dest = slides.parent / "assets" / VSCODE_THEME
    data = THEME.read_bytes()
    if dest.is_file() and dest.read_bytes() == data:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


def workspace_root(slides: Path, cwd: Path) -> Path:
    """VS Code のワークスペースのフォルダ (の見当)

    スライドの上のフォルダで .vscode があるところ、無ければ今のフォルダ (VS Code の
    ターミナルはワークスペースのフォルダで開く) にスライドがあればそこ、
    どちらでもなければスライドのフォルダ。
    """
    folder = slides.parent
    for candidate in [folder, *folder.parents]:
        if (candidate / ".vscode").is_dir():
            return candidate
    if slides.is_relative_to(cwd) and cwd != Path.home():
        return cwd
    return folder


def register_vscode_theme(slides: Path, cwd: Path) -> str | None:
    """ワークスペースの .vscode/settings.json に、テーマのコピーを登録する

    Marp for VS Code は、ワークスペースの中のテーマしか使えない
    (markdown.marp.themes にワークスペースからの相対パスを書く)。
    登録したら、または登録できなかったら、その説明を返す (何もしなければ None)。
    """
    root = workspace_root(slides, cwd)
    entry = (
        "./" + (slides.parent / "assets" / VSCODE_THEME).relative_to(root).as_posix()
    )
    settings = root / ".vscode" / "settings.json"
    data: dict = {}
    if settings.is_file():
        text = settings.read_text(encoding="utf-8-sig")
        try:
            loaded = json.loads(text) if text.strip() else {}
        except json.JSONDecodeError:
            loaded = None
        if not isinstance(loaded, dict):
            return (
                f"{settings} を読めなかったので (コメントなどがある)、VS Code の設定は"
                f'変えていません。プレビューで kit-slides を使うには "{VSCODE_THEMES_KEY}"'
                f' に "{entry}" を追加してください'
            )
        data = loaded
    themes = data.get(VSCODE_THEMES_KEY, [])
    if not isinstance(themes, list):
        themes = [themes]
    normalized = {str(t).removeprefix("./") for t in themes}
    if entry.removeprefix("./") in normalized:
        return None
    data[VSCODE_THEMES_KEY] = [*themes, entry]
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return (
        f"VS Code のプレビューで kit-slides テーマを使えるように登録しました: {settings}"
        " (警告が消えないときは、VS Code のウィンドウを再読み込みしてください)"
    )


def setup_vscode_preview(slides: Path, cwd: Path) -> list[str]:
    """VS Code (Marp for VS Code) のプレビューでテーマが使えるようにする

    キットの中のスライド (見本など) では何もしない。
    """
    if slides.is_relative_to(KIT_DIR):
        return []
    messages = []
    copied = copy_theme(slides)
    if copied:
        messages.append(f"テーマをコピーしました (VS Code のプレビュー用): {copied}")
    registered = register_vscode_theme(slides, cwd)
    if registered:
        messages.append(registered)
    return messages


def platform_key() -> str:
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "x64": "x86_64", "arm64": "aarch64"}.get(
        machine, machine
    )
    if sys.platform == "win32":
        return "windows-x86_64"  # ARM 版 Windows も x64 エミュレーションで動く
    if sys.platform == "darwin":
        return f"macos-{arch}"
    return f"linux-{arch}"


def zip_binary() -> Path | None:
    """marp.zip から今の OS 用の marp を取り出して、そのパスを返す (無ければ None)

    取り出したものは .bin/<CRC>-<サイズ>/ に置き、2 回目からはそれを使う
    (zip を作り直すと別のフォルダになる)。
    """
    if not ZIP_PATH.is_file():
        return None
    exe = "marp.exe" if sys.platform == "win32" else "marp"
    with zipfile.ZipFile(ZIP_PATH) as zf:
        try:
            info = zf.getinfo(f"{platform_key()}/{exe}")
        except KeyError:
            return None
        target = CACHE_DIR / f"{info.CRC:08x}-{info.file_size}" / exe
        if not target.is_file():
            print(f"marp.zip から Marp CLI を取り出しています: {target}", flush=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(exe + ".tmp")
            tmp.write_bytes(zf.read(info))
            tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            tmp.replace(target)
    return target


def marp_command() -> list[str]:
    """Marp CLI を起動するコマンド (marp.zip の単体版、marp、npx の順)"""
    binary = zip_binary()
    if binary:
        return [str(binary)]
    marp = shutil.which("marp")
    if marp:
        return [marp]
    npx = shutil.which("npx")
    if npx:
        return [npx, "--yes", MARP_PACKAGE]
    raise FileNotFoundError(
        f"Marp CLI が見つかりません。marp.zip にこの OS ({platform_key()}) 用が"
        "入っていないので、Node.js をインストールするか "
        f"(npx が使えれば自動で取得します)、`npm install -g {MARP_PACKAGE}` "
        "を実行してください。"
    )


def load_editable_pptx() -> ModuleType:
    """editable_pptx.py を読み込む (build.py をどこから実行しても使えるように、パスで読む)"""
    spec = importlib.util.spec_from_file_location("editable_pptx", EDITABLE_MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass が自分のモジュールを探せるように
    spec.loader.exec_module(module)
    return module


def build_command(slides: Path, fmt: str, output: Path) -> list[str]:
    return [
        *marp_command(),
        str(slides),
        "--theme-set",
        str(THEME),
        "--allow-local-files",
        f"--{fmt}",
        "-o",
        str(output),
    ]


FORMAT_HELP = {
    "pdf": "PDF で書き出す (既定)",
    "html": "HTML で書き出す",
    "pptx": "文字を編集できる PowerPoint (PPTX) で書き出す (Marp CLI もブラウザも不要)",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Marp のスライドを kit-slides テーマで書き出す"
    )
    parser.add_argument("slides", type=Path, help="スライドの Markdown ファイル")
    group = parser.add_mutually_exclusive_group()
    for fmt in FORMATS:
        group.add_argument(
            f"--{fmt}",
            dest="format",
            action="store_const",
            const=fmt,
            help=FORMAT_HELP[fmt],
        )
    # 以前の名前 (--pptx と同じ)
    group.add_argument(
        "--pptx-editable",
        dest="format",
        action="store_const",
        const="pptx",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("-o", "--output", type=Path, help="出力ファイル")
    args = parser.parse_args(argv)
    if args.format is None:
        # 形式の指定が無ければ、出力ファイルの拡張子 (無ければ PDF) にする
        suffix = args.output.suffix.lstrip(".").lower() if args.output else ""
        args.format = suffix if suffix in FORMATS else "pdf"
    return args


def build_pptx(slides: Path, output: Path) -> int:
    """文字を編集できる PPTX を作る (Marp CLI は使わない)"""
    for message in load_editable_pptx().convert(slides, output):
        print(f"警告: {message}", file=sys.stderr)
    print(f"作成しました: {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    slides: Path = args.slides.resolve()
    if not slides.is_file():
        print(f"スライドのファイルがありません: {args.slides}", file=sys.stderr)
        return 1
    output: Path = (
        args.output.resolve() if args.output else slides.with_suffix(f".{args.format}")
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    for path in copy_default_assets(slides):
        print(f"既定の画像をコピーしました: {path}")
    for message in setup_vscode_preview(slides, Path.cwd().resolve()):
        print(message)

    if args.format == "pptx":
        return build_pptx(slides, output)

    try:
        command = build_command(slides, args.format, output)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1
    result = subprocess.run(command)
    if result.returncode != 0:
        message = f"Marp CLI が失敗しました (終了コード {result.returncode})"
        print(message, file=sys.stderr)
        return result.returncode
    print(f"作成しました: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
