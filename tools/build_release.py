"""リリース用の zip と説明文を作る (標準ライブラリのみ。git が必要)

使い方:
    python tools/build_release.py v0.1.0                 # dist/ に作る
    python tools/build_release.py v0.1.0 --output-dir out
    python tools/build_release.py v0.1.0 --root <その版を checkout したフォルダ>

作るもの:
    dist/llm-assist-kit-<版>.zip   git が管理しているファイルから、開発用のもの
                                   (tests/、tools/、.github/、examples/ など) を除いたもの。
                                   展開すると llm-assist-kit-<版>/ ができる
    dist/release-notes.md          CHANGELOG.md の、その版の節

版は pyproject.toml の version と一致していなければならない (v は付けても付けなくてもよい)。
--root を付けると、そのフォルダ (例えば過去の版のタグを checkout したもの) の
ファイル・pyproject.toml・CHANGELOG.md から作る。除くもの (DEV_ONLY) はこのスクリプトのものを使う。
GitHub のリリースは .github/workflows/release.yml が、これを使って作る
(作り直すときは、既にあるリリースの zip を置き換える)。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import tomllib
import zipfile
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
NAME = "llm-assist-kit"
# 配布する zip に入れない、開発用のもの (examples/ はリポジトリで見るための例)
DEV_ONLY = (
    "tests/",
    "tools/",
    ".github/",
    "examples/",
    "CLAUDE.md",
    "DEVELOPMENT.md",
    ".gitignore",
)


def project_version(root: Path = KIT) -> str:
    with open(root / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def tag_for(version: str, root: Path = KIT) -> str:
    """v0.1.0 / 0.1.0 を受け取り、pyproject.toml と一致すれば v0.1.0 を返す"""
    plain = version.removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", plain):
        raise SystemExit(f"版は v1.2.3 の形で指定してください: {version}")
    expected = project_version(root)
    if plain != expected:
        raise SystemExit(
            f"版 {plain} が pyproject.toml の version ({expected}) と一致しません"
        )
    return f"v{plain}"


def release_notes(tag: str, root: Path = KIT) -> str:
    """CHANGELOG.md から `## <tag>` で始まる節の本文を取り出す"""
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(
        rf"(?ms)^## {re.escape(tag)}(?:[ \t][^\n]*)?\n(.*?)(?=^## |\Z)",
        text,
    )
    if not m or not m.group(1).strip():
        raise SystemExit(f"CHANGELOG.md に {tag} の節がありません")
    return m.group(1).strip() + "\n"


def tracked_files(root: Path = KIT) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
    ).stdout.decode("utf-8")
    return sorted(p for p in out.split("\0") if p)


def release_files(files: list[str]) -> list[str]:
    return [f for f in files if not f.startswith(DEV_ONLY)]


def build_zip(tag: str, output: Path, root: Path = KIT) -> list[str]:
    """配布用の zip を作り、入れたファイルの一覧を返す"""
    files = release_files(tracked_files(root))
    prefix = f"{NAME}-{tag}"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in files:
            path = root / name
            zi = zipfile.ZipInfo(f"{prefix}/{name}", date_time=(2020, 1, 1, 0, 0, 0))
            zi.external_attr = (0o755 if path.stat().st_mode & 0o111 else 0o644) << 16
            # 中身が zip のもの (apply_patch.zip など) は圧縮し直さない
            zi.compress_type = (
                zipfile.ZIP_STORED if name.endswith(".zip") else zipfile.ZIP_DEFLATED
            )
            zf.writestr(zi, path.read_bytes())
    return files


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("version", help="リリースする版 (例 v0.1.0)")
    ap.add_argument("--output-dir", type=Path, default=KIT / "dist")
    ap.add_argument(
        "--root",
        type=Path,
        default=KIT,
        help="zip に入れるキットのフォルダ (既定: このキット)",
    )
    args = ap.parse_args()

    root = args.root.resolve()
    tag = tag_for(args.version, root)
    notes = release_notes(tag, root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "release-notes.md").write_text(notes, encoding="utf-8")
    output = args.output_dir / f"{NAME}-{tag}.zip"
    files = build_zip(tag, output, root)
    size = output.stat().st_size / 1024 / 1024
    print(f"{output} を作りました ({len(files)} ファイル、{size:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
