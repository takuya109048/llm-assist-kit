"""Marp CLI の単体版 (Node.js 不要) を取得して skills/marp-slides/marp.zip を作る

使い方 (標準ライブラリのみ。どの OS でも可):
    python tools/build_marp_zip.py                     # 最新のリリース、Windows 用のみ
    python tools/build_marp_zip.py --version v4.5.1    # リリースを指定
    python tools/build_marp_zip.py --targets windows-x86_64,linux-x86_64
    python tools/build_marp_zip.py --licenses-only     # ライセンス文だけ作り直す

取得元は marp-team/marp-cli の GitHub Releases の単体版
(marp-cli-<版>-win.zip など)。GitHub が公開している SHA-256 と照合してから使う。
zip の中身は `<対象>/marp(.exe)`、LICENSE (Marp CLI)、THIRD_PARTY_LICENSES.txt、
BUILD_INFO.txt。単体版には Node.js 本体と npm パッケージが組み込まれているので、
THIRD_PARTY_LICENSES.txt にそのライセンス文を集める (git が必要):
  - Node.js: 実行ファイルに記録された版の LICENSE
  - npm パッケージ: 同じタグの marp-cli の package-lock.json から、実行時の依存と、
    rollup で lib/ に取り込まれる開発用の依存 (src/ が import するもの) をたどり、
    各パッケージの tarball (integrity と照合) からライセンスファイルを取り出す
--licenses-only は、実行ファイルはそのままにして、BUILD_INFO.txt の版で作り直す。
単体版は 1 つで 50 MB 近くあるので、既定では Windows 用だけを入れる
(GitHub は 100 MB を超えるファイルを受け付けない)。
"""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import io
import json
import re
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

import third_party
from third_party import Component

KIT = Path(__file__).resolve().parent.parent
ZIP_PATH = KIT / "skills" / "marp-slides" / "marp.zip"
REPO = "marp-team/marp-cli"
API = f"https://api.github.com/repos/{REPO}"
# 対象 → (リリースの資産名の末尾, 中の実行ファイル名)
TARGETS = {
    "windows-x86_64": ("win.zip", "marp.exe"),
    "linux-x86_64": ("linux.tar.gz", "marp"),
    "linux-aarch64": ("linux-arm64.tar.gz", "marp"),
    "macos-x86_64": ("mac.tar.gz", "marp"),
}
DEFAULT_TARGETS = ["windows-x86_64"]
# 対象 → npm の (os, cpu)。tarball を選ぶのに使う
NPM_PLATFORMS = {
    "windows-x86_64": ("win32", "x64"),
    "linux-x86_64": ("linux", "x64"),
    "linux-aarch64": ("linux", "arm64"),
    "macos-x86_64": ("darwin", "x64"),
}
# 単体版を作る @yao-pkg/pkg は、起動用のコード (prelude) を実行ファイルに組み込む
PKG_RUNTIME = ["@yao-pkg/pkg"]
CLONE_DIR = KIT / ".build" / "marp-cli"
NODE_LICENSE = "https://raw.githubusercontent.com/nodejs/node/{version}/LICENSE"
USER_AGENT = "llm-assist-kit-build-marp-zip"


def fetch(url: str, accept: str = "application/octet-stream") -> bytes:
    print(f"取得: {url}", flush=True)
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": accept}
    )
    with urllib.request.urlopen(req, timeout=300) as res:
        return res.read()


def release_info(version: str | None) -> dict:
    path = f"/releases/tags/{version}" if version else "/releases/latest"
    return json.loads(fetch(API + path, "application/vnd.github+json"))


def find_asset(release: dict, suffix: str) -> dict:
    name = f"marp-cli-{release['tag_name']}-{suffix}"
    for asset in release["assets"]:
        if asset["name"] == name:
            return asset
    raise SystemExit(f"リリース {release['tag_name']} に {name} がありません")


def verify(data: bytes, asset: dict) -> str:
    """GitHub が公開している digest (sha256:...) と照合し、SHA-256 を返す"""
    actual = hashlib.sha256(data).hexdigest()
    digest = asset.get("digest") or ""
    if not digest.startswith("sha256:"):
        raise SystemExit(f"{asset['name']} の SHA-256 が公開されていません")
    if digest.removeprefix("sha256:") != actual:
        raise SystemExit(f"{asset['name']} の SHA-256 が一致しません")
    return actual


def extract_binary(archive: bytes, asset_name: str, exe: str) -> bytes:
    """リリースの資産 (zip / tar.gz) から実行ファイルを取り出す"""
    if asset_name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            for name in zf.namelist():
                if Path(name).name == exe:
                    return zf.read(name)
    else:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tf:
            for member in tf.getmembers():
                if member.isfile() and Path(member.name).name == exe:
                    f = tf.extractfile(member)
                    if f:
                        return f.read()
    raise SystemExit(f"{asset_name} の中に {exe} がありません")


def node_version(binary: bytes) -> str:
    """単体版に組み込まれた Node.js の版 (v26.8.1 など) を実行ファイルから読む"""
    found = set(re.findall(rb"nodejs\.org/download/release/(v\d+\.\d+\.\d+)", binary))
    if len(found) != 1:
        raise SystemExit(f"組み込まれた Node.js の版が分かりません: {sorted(found)}")
    return found.pop().decode()


def clone_marp_cli(tag: str, directory: Path = CLONE_DIR) -> Path:
    if directory.exists():
        subprocess.run(
            ["git", "fetch", "--depth", "1", "origin", "tag", tag],
            cwd=directory,
            check=True,
        )
        subprocess.run(["git", "checkout", "--detach", tag], cwd=directory, check=True)
    else:
        directory.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                tag,
                f"https://github.com/{REPO}",
                str(directory),
            ],
            check=True,
        )
    return directory


IMPORT = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(\s*|\brequire\s*\(\s*|^\s*import\s+)['"]([^'"]+)['"]""",
    re.M,
)
TYPE_IMPORT = re.compile(r"^\s*(?:import|export)\s+type\b[^;]*;", re.M)


def package_name(specifier: str) -> str | None:
    """import の指定からパッケージ名を返す (相対パスや Node.js の組み込みは None)"""
    if specifier.startswith((".", "/", "node:")) or specifier.startswith("#"):
        return None
    parts = specifier.split("/")
    return "/".join(parts[:2]) if specifier.startswith("@") else parts[0]


def bundled_imports(src: Path) -> set[str]:
    """src/ が import するパッケージ (rollup が lib/ に取り込むもの)"""
    names = set()
    for f in src.rglob("*"):
        if f.suffix not in {".ts", ".tsx", ".js", ".mjs", ".cjs"} or not f.is_file():
            continue
        if ".test." in f.name or f.name.endswith(".d.ts"):
            continue
        text = TYPE_IMPORT.sub("", f.read_text(encoding="utf-8"))
        for spec in IMPORT.findall(text):
            name = package_name(spec)
            if name:
                names.add(name)
    return names


def resolve(packages: dict, parent: str, name: str) -> str | None:
    """package-lock.json の packages で、parent から見た name の場所を返す"""
    base = parent
    while True:
        key = f"{base}/node_modules/{name}" if base else f"node_modules/{name}"
        if key in packages:
            return key
        if not base:
            return None
        i = base.rfind("/node_modules/")
        base = base[:i] if i >= 0 else ""


def runs_on(entry: dict, platforms: list[tuple[str, str]]) -> bool:
    def ok(values: list[str] | None, value: str) -> bool:
        if not values:
            return True
        if f"!{value}" in values:
            return False
        return value in values or all(v.startswith("!") for v in values)

    return any(ok(entry.get("os"), o) and ok(entry.get("cpu"), c) for o, c in platforms)


def npm_closure(lock: dict, roots: list[str], targets: list[str]) -> list[str]:
    """roots から依存をたどり、組み込まれるパッケージの場所の一覧を返す"""
    packages = lock["packages"]
    platforms = [NPM_PLATFORMS[t] for t in targets]
    seen: set[str] = set()
    stack = [k for k in (resolve(packages, "", n) for n in roots) if k]
    while stack:
        key = stack.pop()
        if key in seen:
            continue
        entry = packages[key]
        if not runs_on(entry, platforms):
            continue
        seen.add(key)
        optional_peers = {
            n
            for n, meta in entry.get("peerDependenciesMeta", {}).items()
            if meta.get("optional")
        }
        names = [
            *entry.get("dependencies", {}),
            *entry.get("optionalDependencies", {}),
            *(n for n in entry.get("peerDependencies", {}) if n not in optional_peers),
        ]
        for name in names:
            found = resolve(packages, key, name)
            if found:
                stack.append(found)
    return sorted(seen)


def author_names(manifest: dict) -> list[str]:
    author = manifest.get("author")
    if isinstance(author, dict):
        author = author.get("name")
    return [str(author)] if author else []


def git_package(url: str) -> tuple[list[tuple[str, str]], dict]:
    """git の依存 (git+ssh://git@github.com/<所有者>/<名前>.git#<コミット>) を取得し、
    ライセンスファイルと package.json を返す"""
    m = re.match(
        r"^git\+(?:ssh://git@|https://)github\.com[/:](.+?)(?:\.git)?#(\w+)$", url
    )
    if not m:
        raise SystemExit(f"取得できない依存です: {url}")
    repo, commit = m.groups()
    directory = KIT / ".build" / "npm-git" / repo.replace("/", "-") / commit
    if not (directory / ".git").is_dir():
        directory.mkdir(parents=True, exist_ok=True)
        print(f"取得: https://github.com/{repo} ({commit})", flush=True)
        for cmd in (
            ["git", "init", "-q"],
            [
                "git",
                "fetch",
                "-q",
                "--depth",
                "1",
                f"https://github.com/{repo}",
                commit,
            ],
            ["git", "checkout", "-q", "--detach", "FETCH_HEAD"],
        ):
            subprocess.run(cmd, cwd=directory, check=True)
    manifest_path = directory / "package.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return third_party.license_files(directory), manifest


def manifest_license(manifest: dict) -> str:
    value = manifest.get("license")
    if isinstance(value, dict):
        value = value.get("type")
    if not value and isinstance(manifest.get("licenses"), list):
        value = " OR ".join(
            str(x.get("type")) for x in manifest["licenses"] if isinstance(x, dict)
        )
    return str(value or "")


def npm_component(key: str, entry: dict) -> Component:
    name = entry.get("name") or key.rsplit("node_modules/", 1)[1]
    if entry["resolved"].startswith("git+"):
        files, manifest = git_package(entry["resolved"])
        return Component(
            name,
            entry["version"],
            entry.get("license") or manifest_license(manifest) or "(記載なし)",
            entry["resolved"].removeprefix("git+"),
            [] if files else author_names(manifest),
            files,
        )
    data = fetch(entry["resolved"])
    algo, _, expected = entry["integrity"].partition("-")
    actual = base64.b64encode(hashlib.new(algo, data).digest()).decode()
    if actual != expected:
        raise SystemExit(f"{name} の tarball の integrity が一致しません")
    files = []
    manifest: dict = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for member in sorted(tf.getmembers(), key=lambda m: m.name.lower()):
            parts = member.name.split("/")
            if not member.isfile() or len(parts) != 2:
                continue
            f = tf.extractfile(member)
            if f is None:
                continue
            if third_party.is_license_file(parts[1]):
                files.append((parts[1], third_party.decode(f.read())))
            elif parts[1] == "package.json":
                manifest = json.loads(f.read())
    return Component(
        name,
        entry["version"],
        entry.get("license") or manifest_license(manifest) or "(記載なし)",
        f"https://www.npmjs.com/package/{name}/v/{entry['version']}",
        [] if files else author_names(manifest),
        files,
    )


def third_party_licenses(tag: str, node: str, targets: list[str]) -> str:
    clone = clone_marp_cli(tag)
    lock = json.loads((clone / "package-lock.json").read_text(encoding="utf-8"))
    root = lock["packages"][""]
    runtime = list(root.get("dependencies", {}))
    bundled = sorted(bundled_imports(clone / "src") - set(runtime))
    packages = lock["packages"]
    keys = npm_closure(lock, runtime + bundled, targets)
    # @yao-pkg/pkg は組み込まれる prelude の分だけ (その依存はビルド用の道具)
    keys += [k for k in (resolve(packages, "", n) for n in PKG_RUNTIME) if k]
    # 同じ名前と版が node_modules の別の場所にあれば 1 つにする
    unique: dict[tuple[str, str], str] = {}
    for key in sorted(keys):
        entry = packages[key]
        name = entry.get("name") or key.rsplit("node_modules/", 1)[1]
        unique.setdefault((name, entry["version"]), key)
    components = [npm_component(k, packages[k]) for k in unique.values()]
    components.append(
        Component(
            "Node.js",
            node,
            "MIT ほか (下の LICENSE に、Node.js が組み込む部品の分も含む)",
            f"https://github.com/nodejs/node/tree/{node}",
            files=[
                (
                    "LICENSE",
                    third_party.decode(fetch(NODE_LICENSE.format(version=node))),
                )
            ],
        )
    )
    preface = (
        f"Marp CLI {tag} の単体版 ({', '.join(targets)}) に組み込まれている、"
        "Marp CLI 以外の部品のライセンス文です。\n"
        "Marp CLI 自身のライセンスは同じ zip の LICENSE にあります。\n"
        f"Node.js {node} と、marp-cli の package-lock.json から求めた npm パッケージ "
        "(実行時の依存、rollup で取り込まれる依存、@yao-pkg/pkg) を載せています。"
    )
    return third_party.render(
        "Marp CLI の単体版に組み込まれた他のソフトのライセンス", components, preface
    )


def licenses_only(zip_path: Path) -> int:
    """実行ファイルはそのままにして、THIRD_PARTY_LICENSES.txt だけ作り直す"""
    info = third_party.read_zip_text(zip_path, "BUILD_INFO.txt")
    tag = third_party.build_info_value(info, "version").split()[0]
    with zipfile.ZipFile(zip_path) as zf:
        executables = [n for n in zf.namelist() if n.split("/")[0] in TARGETS]
        targets = sorted({n.split("/")[0] for n in executables})
        node = node_version(zf.read(executables[0]))
    text = third_party_licenses(tag, node, targets)
    if "node:" not in info:
        info = info.replace("built:", f"node: {node} (単体版に組み込まれた版)\nbuilt:")
    info = info.replace(
        "license: MIT (LICENSE を参照)",
        f"license: MIT (LICENSE を参照。組み込まれた部品は {third_party.FILE_NAME})",
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
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--version", help="リリースのタグ (例 v4.5.1。既定: 最新)")
    ap.add_argument(
        "--targets",
        default=",".join(DEFAULT_TARGETS),
        help=f"入れる対象 (カンマ区切り。{', '.join(TARGETS)})",
    )
    ap.add_argument("--output", type=Path, default=ZIP_PATH)
    ap.add_argument(
        "--licenses-only",
        action="store_true",
        help="取得し直さず、今の zip の THIRD_PARTY_LICENSES.txt だけ作り直す",
    )
    args = ap.parse_args()
    if args.licenses_only:
        return licenses_only(args.output)

    targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    unknown = [t for t in targets if t not in TARGETS]
    if unknown:
        raise SystemExit(f"対象が分かりません: {', '.join(unknown)}")

    release = release_info(args.version)
    tag = release["tag_name"]
    binaries: dict[str, tuple[str, bytes]] = {}
    sources = []
    for key in targets:
        suffix, exe = TARGETS[key]
        asset = find_asset(release, suffix)
        archive = fetch(asset["browser_download_url"])
        sha = verify(archive, asset)
        binaries[key] = (exe, extract_binary(archive, asset["name"], exe))
        sources.append(f"  {key}: {asset['name']} (sha256 {sha})")
    license_text = fetch(f"https://raw.githubusercontent.com/{REPO}/{tag}/LICENSE")
    node = node_version(next(iter(binaries.values()))[1])
    licenses = third_party_licenses(tag, node, targets)

    info = "\n".join(
        [
            "Marp CLI の単体版 (Node.js 不要)",
            f"source: https://github.com/{REPO}/releases/tag/{tag}",
            f"version: {tag} ({release.get('published_at', '')})",
            "assets:",
            *sources,
            f"node: {node} (単体版に組み込まれた版)",
            f"built: {datetime.date.today().isoformat()} by tools/build_marp_zip.py",
            "license: MIT (LICENSE を参照。"
            f"組み込まれた部品は {third_party.FILE_NAME})",
            "",
        ]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for key, (exe, data) in binaries.items():
            zi = zipfile.ZipInfo(f"{key}/{exe}", date_time=(2020, 1, 1, 0, 0, 0))
            zi.external_attr = 0o755 << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, data)
        zf.writestr(third_party.text_entry("LICENSE"), license_text)
        zf.writestr(third_party.text_entry(third_party.FILE_NAME), licenses)
        zf.writestr(third_party.text_entry("BUILD_INFO.txt"), info)
    size = args.output.stat().st_size / 1024 / 1024
    print(f"\n{args.output} を作りました ({size:.1f} MB)\n{info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
