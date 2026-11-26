"""Marp CLI の単体版 (Node.js 不要) を取得して skills/marp-slides/marp.zip を作る

使い方 (標準ライブラリのみ。どの OS でも可):
    python tools/build_marp_zip.py                     # 最新のリリース、Windows 用のみ
    python tools/build_marp_zip.py --version v4.5.1    # リリースを指定
    python tools/build_marp_zip.py --targets windows-x86_64,linux-x86_64

取得元は marp-team/marp-cli の GitHub Releases の単体版
(marp-cli-<版>-win.zip など)。GitHub が公開している SHA-256 と照合してから使う。
zip の中身は `<対象>/marp(.exe)`、LICENSE、BUILD_INFO.txt。
単体版は 1 つで 50 MB 近くあるので、既定では Windows 用だけを入れる
(GitHub は 100 MB を超えるファイルを受け付けない)。
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import io
import json
import tarfile
import urllib.request
import zipfile
from pathlib import Path

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


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--version", help="リリースのタグ (例 v4.5.1。既定: 最新)")
    ap.add_argument(
        "--targets",
        default=",".join(DEFAULT_TARGETS),
        help=f"入れる対象 (カンマ区切り。{', '.join(TARGETS)})",
    )
    ap.add_argument("--output", type=Path, default=ZIP_PATH)
    args = ap.parse_args()

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

    info = "\n".join(
        [
            "Marp CLI の単体版 (Node.js 不要)",
            f"source: https://github.com/{REPO}/releases/tag/{tag}",
            f"version: {tag} ({release.get('published_at', '')})",
            "assets:",
            *sources,
            f"built: {datetime.date.today().isoformat()} by tools/build_marp_zip.py",
            "license: MIT (LICENSE を参照)",
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
        zf.writestr("LICENSE", license_text)
        zf.writestr("BUILD_INFO.txt", info)
    size = args.output.stat().st_size / 1024 / 1024
    print(f"\n{args.output} を作りました ({size:.1f} MB)\n{info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
