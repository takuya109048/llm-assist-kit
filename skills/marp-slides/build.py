"""Marp のスライド (Markdown) を、このスキルのテーマで PDF / HTML / PPTX にする

使い方:
    python build.py slides.md            # slides.pdf を作る
    python build.py slides.md --html     # slides.html を作る
    python build.py slides.md --pptx     # slides.pptx を作る (各スライドは画像)
    python build.py slides.md --pptx-editable  # 文字を編集できる slides.pptx を作る
    python build.py slides.md -o out/deck.pdf

- テーマ (theme.css) はこのスキルのものを使う (Markdown では `theme: kit-slides`)
- スライドと同じフォルダの assets/ に、表紙の背景 (background.svg)・ロゴ (logo.svg)・
  仮の画像 (placeholder.svg) が無ければ既定の画像をコピーする。既にあるファイルは上書きしないので、
  同じ名前の画像を置けば差し替えられる
- Marp CLI は、同じフォルダの marp.zip に入っている単体版 (Node.js 不要) を
  .bin/ に取り出して使う。zip にこの OS 用が無ければ、`marp` コマンド、
  `npx @marp-team/marp-cli` (Node.js が必要) の順に探す
- PDF / PPTX の書き出しには Chrome か Edge (Windows には標準で入っている) が必要
- --pptx-editable は Marp CLI の試験的な機能で、LibreOffice が必要。文字は編集できるが、
  箇条書きや表は行ごとのテキストボックスになり、見た目が少し崩れることがある。
  書き出しはフォントをメイリオ 1 種類にしたテーマ (theme-editable.css) で行い、その後
  PPTX の中のフォント名を「半角英数は Segoe UI、日本語はメイリオ」に、
  別の文字になったもの (康煕部首の "⽉" など) を元の文字に直す
"""

from __future__ import annotations

import argparse
import platform
import re
import shutil
import stat
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
THEME = SKILL_DIR / "theme.css"
DEFAULT_ASSETS = SKILL_DIR / "assets"
ASSET_FILES = ["background.svg", "logo.svg", "placeholder.svg"]
ZIP_PATH = SKILL_DIR / "marp.zip"  # tools/build_marp_zip.py で作る
CACHE_DIR = SKILL_DIR / ".bin"  # zip から取り出した実行ファイルの置き場 (git 管理外)
MARP_PACKAGE = "@marp-team/marp-cli"
FORMATS = ["pdf", "html", "pptx"]
# 文字を編集できる PPTX (Marp CLI の試験的な機能。LibreOffice で PDF を変換して作る)
EDITABLE_PPTX = "pptx-editable"
# 編集できる PPTX を書き出すときのテーマ (フォントをメイリオ 1 種類にしたもの。
# 半角英数と日本語でフォントが変わると、LibreOffice がその切れ目で文字の箱を分けるため)
EDITABLE_THEME = SKILL_DIR / "theme-editable.css"
EDITABLE_THEME_NAME = "kit-slides-editable"
# テーマ (theme.css の --kit-font) のフォント。半角英数と全角 (日本語)
LATIN_FONT = "Segoe UI"
EA_FONT = "Meiryo"
# 編集できる PPTX の中で、テーマのフォントに直すフォント名
# (LibreOffice が PDF から付ける "Meiryo" / "Meiryo-Bold" / "SegoeUI" や、既定の "Noto Serif JP")
SLIDE_FONT_RE = re.compile(
    r'<a:(latin|ea|cs) typeface="(?:Meiryo[^"]*|SegoeUI[^"]*|Noto Serif JP)"'
)
# テーマ・マスター・レイアウトの既定フォント (PowerPoint で文字を打ち足したときに使われる)
DEFAULT_FONT_RE = re.compile(r'<a:(latin|ea|cs) typeface="[^"]*"')
DEFAULT_FONT_PARTS = ("ppt/theme/", "ppt/slideMasters/", "ppt/slideLayouts/")
TEXT_RE = re.compile(r"(<a:t>)([^<]*)(</a:t>)")


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


def format_options(fmt: str) -> list[str]:
    """形式を Marp CLI のオプションにする"""
    if fmt == EDITABLE_PPTX:
        return ["--pptx", "--pptx-editable"]
    return [f"--{fmt}"]


def theme_options(fmt: str) -> list[str]:
    """テーマのオプション (編集できる PPTX は、フォントをメイリオ 1 種類にしたテーマで)"""
    if fmt == EDITABLE_PPTX:
        return [
            "--theme-set",
            str(THEME),
            str(EDITABLE_THEME),
            "--theme",
            EDITABLE_THEME_NAME,
        ]
    return ["--theme-set", str(THEME)]


def build_command(slides: Path, fmt: str, output: Path) -> list[str]:
    return [
        *marp_command(),
        str(slides),
        *theme_options(fmt),
        "--allow-local-files",
        *format_options(fmt),
        "-o",
        str(output),
    ]


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
            help=f"{fmt.upper()} で書き出す" + (" (既定)" if fmt == "pdf" else ""),
        )
    group.add_argument(
        f"--{EDITABLE_PPTX}",
        dest="format",
        action="store_const",
        const=EDITABLE_PPTX,
        help="文字を編集できる PPTX で書き出す (試験的。LibreOffice が必要)",
    )
    parser.add_argument("-o", "--output", type=Path, help="出力ファイル")
    args = parser.parse_args(argv)
    if args.format is None:
        # 形式の指定が無ければ、出力ファイルの拡張子 (無ければ PDF) にする
        suffix = args.output.suffix.lstrip(".").lower() if args.output else ""
        args.format = suffix if suffix in FORMATS else "pdf"
    return args


def _theme_font(m: re.Match[str]) -> str:
    """<a:latin> / <a:cs> は Segoe UI、<a:ea> (日本語などの文字) はメイリオにする"""
    font = EA_FONT if m.group(1) == "ea" else LATIN_FONT
    return f'<a:{m.group(1)} typeface="{font}"'


def fix_font_names(xml: str, part: str) -> str:
    """PPTX の 1 つの XML (part はその中のパス) のフォント名をテーマのフォントにそろえる

    PowerPoint は 1 つの文字の箱の中でも、半角英数は <a:latin>、日本語は <a:ea> の
    フォントで表示するので、メイリオ 1 種類で書き出した文字もこれで Segoe UI と
    メイリオに分かれる。ロゴの文字 (Arial) などはそのままにする。
    """
    if part.startswith(DEFAULT_FONT_PARTS):
        return DEFAULT_FONT_RE.sub(_theme_font, xml)
    return SLIDE_FONT_RE.sub(_theme_font, xml)


def normalize_char(ch: str) -> str:
    """PDF から読み取られて別の文字になったものを元に戻す

    - 康煕部首・CJK 部首補助 (例 "⽉" U+2F49) → 漢字 ("月")
    - 縦書き用の約物 (例 "︓" U+FE13) → 全角の約物 ("：")
    """
    code = ord(ch)
    if 0x2E80 <= code <= 0x2FDF:
        return unicodedata.normalize("NFKC", ch)
    if 0xFE10 <= code <= 0xFE19 or 0xFE30 <= code <= 0xFE4F:
        n = unicodedata.normalize("NFKC", ch)
        if n == "...":
            return "…"
        if len(n) == 1 and "!" <= n <= "~":
            return chr(ord(n) + 0xFEE0)  # 半角の記号を全角にする (":" → "：")
        return n
    return ch


def normalize_text(text: str) -> str:
    return "".join(normalize_char(ch) for ch in text)


def _fix_text(m: re.Match[str]) -> str:
    return m.group(1) + normalize_text(m.group(2)) + m.group(3)


def fix_editable_pptx(path: Path) -> None:
    """編集できる PPTX のフォント名と文字を直す (上書き)"""
    tmp = path.with_name(path.name + ".tmp")
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w") as dst:
        for info in src.infolist():
            data = src.read(info)
            name = info.filename
            if name.endswith(".xml"):
                xml = fix_font_names(data.decode("utf-8"), name)
                if name.startswith("ppt/slides/"):
                    xml = TEXT_RE.sub(_fix_text, xml)
                data = xml.encode("utf-8")
            dst.writestr(info, data)
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    slides: Path = args.slides.resolve()
    if not slides.is_file():
        print(f"スライドのファイルがありません: {args.slides}", file=sys.stderr)
        return 1
    extension = "pptx" if args.format == EDITABLE_PPTX else args.format
    output: Path = (
        args.output.resolve() if args.output else slides.with_suffix(f".{extension}")
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    for path in copy_default_assets(slides):
        print(f"既定の画像をコピーしました: {path}")

    try:
        command = build_command(slides, args.format, output)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1
    result = subprocess.run(command)
    if result.returncode != 0:
        message = f"Marp CLI が失敗しました (終了コード {result.returncode})"
        print(message, file=sys.stderr)
        if args.format == EDITABLE_PPTX:
            print(
                "編集できる PPTX には LibreOffice が必要です "
                "(https://www.libreoffice.org/)。",
                file=sys.stderr,
            )
        return result.returncode
    if args.format == EDITABLE_PPTX:
        fix_editable_pptx(output)
    print(f"作成しました: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
