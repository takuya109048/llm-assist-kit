"""codex-rs の apply_patch をビルドして skills/apply-patch/apply_patch.zip を作る

使い方 (Linux。Rust の rustup と git が必要):
    python tools/build_apply_patch.py                       # 最新の openai/codex
    python tools/build_apply_patch.py --rev <コミット>        # コミットを指定
    python tools/build_apply_patch.py --codex-dir <既存の clone>

ビルドする対象:
    linux-x86_64    x86_64-unknown-linux-gnu
    windows-x86_64  x86_64-pc-windows-gnu (mingw-w64 が必要: apt install gcc-mingw-w64-x86-64)

上流のソースは変更しない。ビルド用にワークスペースの Cargo.toml だけを次のように絞る:
  - members を apply_patch の依存に必要なクレートだけにする
  - [patch.crates-io] の v8 (apply_patch では使わない。取得先の chromium のサーバーが必要になる) を外す
"""

from __future__ import annotations

import argparse
import datetime
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
ZIP_PATH = KIT / "skills" / "apply-patch" / "apply_patch.zip"
CODEX_URL = "https://github.com/openai/codex"
PACKAGE = "codex-apply-patch"
TARGETS = {
    "linux-x86_64": ("x86_64-unknown-linux-gnu", "apply_patch"),
    "windows-x86_64": ("x86_64-pc-windows-gnu", "apply_patch.exe"),
}


def run(cmd: list[str], cwd: Path | None = None) -> str:
    print("+", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
    return r.stdout.strip()


def dependency_closure(lock_path: Path, root: str) -> set[str]:
    """Cargo.lock から root が依存するパッケージ名をすべて集める"""
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    by_name: dict[str, list[dict]] = {}
    for p in lock["package"]:
        by_name.setdefault(p["name"], []).append(p)
    seen: set[str] = set()
    stack = [root]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        for p in by_name.get(name, []):
            stack += [d.split(" ")[0] for d in p.get("dependencies", [])]
    return {n for n in seen if any("source" not in p for p in by_name.get(n, []))}


def prune_workspace(codex_rs: Path) -> None:
    """ワークスペースの Cargo.toml を apply_patch のビルドに必要な分だけにする"""
    manifest = codex_rs / "Cargo.toml"
    original = codex_rs / "Cargo.toml.orig"
    if not original.exists():
        shutil.copy(manifest, original)
    text = original.read_text(encoding="utf-8")
    ws = tomllib.loads(text)
    workspace_crates = dependency_closure(codex_rs / "Cargo.lock", PACKAGE)
    paths = []
    for name in sorted(workspace_crates):
        dep = ws["workspace"]["dependencies"].get(name)
        if isinstance(dep, dict) and "path" in dep:
            paths.append(dep["path"])
        elif (codex_rs / name / "Cargo.toml").is_file():
            paths.append(name)
        else:
            sys.exit(f"ワークスペース内のクレートの場所が分かりません: {name}")
    members = "members = [\n" + "".join(f'    "{p}",\n' for p in paths) + "]"
    text = re.sub(r"members\s*=\s*\[.*?\]", members, text, count=1, flags=re.S)
    text = re.sub(r'(?m)^v8 = \{ git = "[^"]*rusty_v8[^\n]*\n', "", text)
    manifest.write_text(text, encoding="utf-8")
    print(f"ワークスペースを {len(paths)} クレートに絞りました")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--codex-dir", type=Path, help="openai/codex の clone (無ければ作る)"
    )
    ap.add_argument("--rev", help="ビルドするコミット (既定: 既定ブランチの最新)")
    ap.add_argument("--output", type=Path, default=ZIP_PATH)
    args = ap.parse_args()

    codex = args.codex_dir or (KIT / ".build" / "codex")
    if not (codex / ".git").is_dir():
        codex.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--filter=blob:none", CODEX_URL, str(codex)])
    if args.rev:
        run(["git", "fetch", "origin", args.rev], cwd=codex)
        run(["git", "checkout", "--detach", args.rev], cwd=codex)
    commit = run(["git", "rev-parse", "HEAD"], cwd=codex)
    commit_date = run(["git", "show", "-s", "--format=%cI", "HEAD"], cwd=codex)

    codex_rs = codex / "codex-rs"
    prune_workspace(codex_rs)
    rustc = run(["rustc", "--version"], cwd=codex_rs)
    binaries: dict[str, Path] = {}
    for key, (triple, exe) in TARGETS.items():
        run(["rustup", "target", "add", triple], cwd=codex_rs)
        run(
            [
                "cargo",
                "build",
                "--release",
                "-p",
                PACKAGE,
                "--bin",
                "apply_patch",
                "--target",
                triple,
                "--config",
                "profile.release.strip=true",
            ],
            cwd=codex_rs,
        )
        binaries[key] = codex_rs / "target" / triple / "release" / exe

    info = "\n".join(
        [
            "apply_patch (codex-rs/apply-patch) のビルド",
            f"source: {CODEX_URL}",
            f"commit: {commit} ({commit_date})",
            f"package: {PACKAGE} (bin apply_patch)",
            f"toolchain: {rustc}",
            "targets: " + ", ".join(f"{k} ({t})" for k, (t, _) in TARGETS.items()),
            f"built: {datetime.date.today().isoformat()} by tools/build_apply_patch.py",
            "license: Apache-2.0 (LICENSE / NOTICE を参照)",
            "",
        ]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for key, path in binaries.items():
            zi = zipfile.ZipInfo(f"{key}/{path.name}", date_time=(2020, 1, 1, 0, 0, 0))
            zi.external_attr = 0o755 << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, path.read_bytes())
        for name in ("LICENSE", "NOTICE"):
            if (codex / name).is_file():
                zf.write(codex / name, name)
        zf.writestr("BUILD_INFO.txt", info)
    size = args.output.stat().st_size / 1024 / 1024
    print(f"\n{args.output} を作りました ({size:.1f} MB)\n{info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
