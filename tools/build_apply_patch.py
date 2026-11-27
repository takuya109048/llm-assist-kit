"""codex-rs の apply_patch をビルドして skills/apply-patch/apply_patch.zip を作る

使い方 (Linux。Rust の rustup と git が必要):
    python tools/build_apply_patch.py                       # 最新の openai/codex
    python tools/build_apply_patch.py --rev <コミット>        # コミットを指定
    python tools/build_apply_patch.py --codex-dir <既存の clone>
    python tools/build_apply_patch.py --licenses-only       # ライセンス文だけ作り直す

zip の中身は `<対象>/apply_patch(.exe)`、LICENSE と NOTICE (codex)、
THIRD_PARTY_LICENSES.txt (組み込まれたクレート・Rust 標準ライブラリ・mingw-w64 の
ライセンス文)、BUILD_INFO.txt。--licenses-only は、実行ファイルはそのままにして、
BUILD_INFO.txt のコミットと Rust の版で THIRD_PARTY_LICENSES.txt を作り直す。

ビルドする対象:
    linux-x86_64    x86_64-unknown-linux-gnu
    windows-x86_64  x86_64-pc-windows-gnu (mingw-w64 が必要: apt install gcc-mingw-w64-x86-64)

上流のソースは変更しない。ビルド用にワークスペースの Cargo.toml だけを次のように絞る:
  - members を apply_patch の依存に必要なクレートだけにする
  - [patch.crates-io] の v8 (apply_patch では使わない。取得先の chromium のサーバーが必要になる) を外す
この変更は BUILD_INFO.txt の modifications にも書く (Apache-2.0 の第 4 条 b)。
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import third_party
from third_party import Component

KIT = Path(__file__).resolve().parent.parent
ZIP_PATH = KIT / "skills" / "apply-patch" / "apply_patch.zip"
CODEX_URL = "https://github.com/openai/codex"
PACKAGE = "codex-apply-patch"
TARGETS = {
    "linux-x86_64": ("x86_64-unknown-linux-gnu", "apply_patch"),
    "windows-x86_64": ("x86_64-pc-windows-gnu", "apply_patch.exe"),
}
# windows-gnu の実行ファイルに静的に組み込まれる mingw-w64 の CRT と winpthreads
MINGW_COPYRIGHT = Path("/usr/share/doc/mingw-w64-x86-64-dev/copyright")
MODIFICATIONS = (
    "codex-rs/Cargo.toml の [workspace] members を apply_patch に必要なクレートだけにし、"
    "[patch.crates-io] の v8 を外した (ソースは変更していない)"
)


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> str:
    print("+", " ".join(cmd), flush=True)
    r = subprocess.run(
        cmd, cwd=cwd, check=True, capture_output=True, text=True, env=env
    )
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


def crate_ids(codex_rs: Path, triple: str, env: dict | None) -> set[tuple[str, str]]:
    """対象の実行ファイルに組み込まれる外部のクレート (名前, 版) を返す

    cargo tree で、通常の依存だけ (ビルド用・開発用・proc-macro を除く) をたどる。
    ワークスペース内のクレート (codex 自身) は除く。
    """
    out = run(
        [
            "cargo",
            "tree",
            "-q",
            "-p",
            PACKAGE,
            "-e",
            "normal,no-proc-macro",
            "--target",
            triple,
            "--prefix",
            "none",
            "--format",
            "{p}",
        ],
        cwd=codex_rs,
        env=env,
    )
    ids = set()
    for line in out.splitlines():
        m = re.match(r"^(\S+) v(\S+)(?: \((.*?)\))?(?: \(\*\))?$", line.strip())
        if not m:
            continue
        name, version, source = m.groups()
        if source and source.startswith("/"):
            continue  # ワークスペース内 (パス指定) のクレート
        ids.add((name, version))
    return ids


def crate_components(codex_rs: Path, env: dict | None) -> list[Component]:
    meta = json.loads(
        run(["cargo", "metadata", "--format-version", "1"], cwd=codex_rs, env=env)
    )
    packages = {
        (p["name"], p["version"]): p for p in meta["packages"] if p.get("source")
    }
    ids: set[tuple[str, str]] = set()
    for triple, _ in TARGETS.values():
        ids |= crate_ids(codex_rs, triple, env)
    components = []
    for key in sorted(ids):
        p = packages.get(key)
        if p is None:
            sys.exit(f"cargo metadata にクレートがありません: {key[0]} {key[1]}")
        directory = Path(p["manifest_path"]).parent
        files = third_party.license_files(directory)
        extra = p.get("license_file")
        if extra and (directory / extra).is_file() and extra not in dict(files):
            files.append((extra, third_party.decode((directory / extra).read_bytes())))
        source = p.get("repository") or f"https://crates.io/crates/{p['name']}"
        components.append(
            Component(
                p["name"],
                p["version"],
                p.get("license") or "(記載なし)",
                source,
                [] if files else p.get("authors", []),
                files,
            )
        )
    return components


def html_text(path: Path) -> str:
    text = re.sub(r"<[^>]+>", "", path.read_text(encoding="utf-8"))
    text = html.unescape(text)
    lines = [line.strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def toolchain_components(env: dict | None) -> list[Component]:
    """Rust 標準ライブラリと、windows-gnu で組み込まれる mingw-w64 の部品"""
    rustc = run(["rustc", "--version"], env=env)
    sysroot = Path(run(["rustc", "--print", "sysroot"], env=env))
    doc = sysroot / "share" / "doc" / "rust"
    library = doc / "COPYRIGHT-library.html"
    if not library.is_file():
        sys.exit(f"Rust 標準ライブラリの著作権表示がありません: {library}")
    version = rustc.split()[1]
    components = [
        Component(
            "Rust standard library",
            version,
            "Apache-2.0 OR MIT",
            "https://github.com/rust-lang/rust",
            # 標準ライブラリと、それが使うクレートの著作権表示・ライセンス文
            files=[("COPYRIGHT-library", html_text(library))],
        )
    ]
    if not MINGW_COPYRIGHT.is_file():
        sys.exit(
            f"mingw-w64 の著作権表示がありません: {MINGW_COPYRIGHT}\n"
            "apt install gcc-mingw-w64-x86-64 で入れてください"
        )
    dpkg = subprocess.run(
        ["dpkg-query", "-W", "-f", "${Version}", "mingw-w64-x86-64-dev"],
        capture_output=True,
        text=True,
    )
    components.append(
        Component(
            "mingw-w64 (CRT, winpthreads)",
            dpkg.stdout.strip() if dpkg.returncode == 0 else "",
            "ZPL-2.1, MIT など (下の copyright を参照)",
            "https://www.mingw-w64.org/",
            files=[("copyright", third_party.decode(MINGW_COPYRIGHT.read_bytes()))],
        )
    )
    return components


def third_party_licenses(codex_rs: Path, env: dict | None = None) -> str:
    preface = (
        "apply_patch の実行ファイル (linux-x86_64 / windows-x86_64) に組み込まれている、"
        "codex 以外の部品のライセンス文です。\n"
        "codex 自身のライセンスは同じ zip の LICENSE と NOTICE にあります。\n"
        "windows-x86_64 には mingw-w64 の CRT と winpthreads も静的に組み込まれます "
        "(libgcc は GCC Runtime Library Exception により表示は不要)。"
    )
    components = crate_components(codex_rs, env) + toolchain_components(env)
    return third_party.render(
        "apply_patch に組み込まれた他のソフトのライセンス", components, preface
    )


def licenses_only(codex: Path, zip_path: Path) -> int:
    """実行ファイルはそのままにして、THIRD_PARTY_LICENSES.txt だけ作り直す"""
    info = third_party.read_zip_text(zip_path, "BUILD_INFO.txt")
    commit = third_party.build_info_value(info, "commit").split()[0]
    toolchain = third_party.build_info_value(info, "toolchain").split()[1]
    if not (codex / ".git").is_dir():
        codex.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--filter=blob:none", CODEX_URL, str(codex)])
    run(["git", "fetch", "origin", commit], cwd=codex)
    run(["git", "checkout", "--detach", commit], cwd=codex)
    codex_rs = codex / "codex-rs"
    prune_workspace(codex_rs)
    env = {**os.environ, "RUSTUP_TOOLCHAIN": toolchain}
    text = third_party_licenses(codex_rs, env)
    if "modifications:" not in info:
        info = info.replace("license:", f"modifications: {MODIFICATIONS}\nlicense:")
    info = info.replace(
        "(LICENSE / NOTICE を参照)",
        f"(LICENSE / NOTICE を参照。組み込まれた部品は {third_party.FILE_NAME})",
    )
    third_party.replace_in_zip(
        zip_path,
        {
            third_party.FILE_NAME: text.encode("utf-8"),
            "BUILD_INFO.txt": info.encode("utf-8"),
        },
    )
    print(f"{zip_path} の {third_party.FILE_NAME} を作り直しました")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--codex-dir", type=Path, help="openai/codex の clone (無ければ作る)"
    )
    ap.add_argument("--rev", help="ビルドするコミット (既定: 既定ブランチの最新)")
    ap.add_argument("--output", type=Path, default=ZIP_PATH)
    ap.add_argument(
        "--licenses-only",
        action="store_true",
        help="ビルドせず、今の zip の THIRD_PARTY_LICENSES.txt だけ作り直す",
    )
    args = ap.parse_args()

    codex = args.codex_dir or (KIT / ".build" / "codex")
    if args.licenses_only:
        return licenses_only(codex, args.output)
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
    licenses = third_party_licenses(codex_rs)

    info = "\n".join(
        [
            "apply_patch (codex-rs/apply-patch) のビルド",
            f"source: {CODEX_URL}",
            f"commit: {commit} ({commit_date})",
            f"package: {PACKAGE} (bin apply_patch)",
            f"toolchain: {rustc}",
            "targets: " + ", ".join(f"{k} ({t})" for k, (t, _) in TARGETS.items()),
            f"built: {datetime.date.today().isoformat()} by tools/build_apply_patch.py",
            f"modifications: {MODIFICATIONS}",
            "license: Apache-2.0 (LICENSE / NOTICE を参照。"
            f"組み込まれた部品は {third_party.FILE_NAME})",
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
                zf.writestr(third_party.text_entry(name), (codex / name).read_bytes())
        zf.writestr(third_party.text_entry(third_party.FILE_NAME), licenses)
        zf.writestr(third_party.text_entry("BUILD_INFO.txt"), info)
    size = args.output.stat().st_size / 1024 / 1024
    print(f"\n{args.output} を作りました ({size:.1f} MB)\n{info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
