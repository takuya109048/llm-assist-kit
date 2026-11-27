"""同梱する実行ファイルに組み込まれた、他の人のソフトのライセンス文をまとめる

tools/build_apply_patch.py と tools/build_marp_zip.py から使う (標準ライブラリのみ)。
zip に入れる THIRD_PARTY_LICENSES.txt は、部品ごとに次の形で並べる:

    ================================================================
    <名前> <版>
    license: <SPDX の表記>
    source: <入手先>
    ---------------- <ファイル名> ----------------
    <部品に入っているライセンスファイルの中身>

部品にライセンスファイルが無いときは、その旨と作者を書き、末尾の付録に
SPDX の原文 (spdx/license-list-data) を載せる。
"""

from __future__ import annotations

import re
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

FILE_NAME = "THIRD_PARTY_LICENSES.txt"
RULE = "=" * 72
# ライセンスファイルとみなす名前 (LICENSE、LICENSE-MIT、LICENCE.md、COPYING、NOTICE など)
LICENSE_NAME = re.compile(r"^(licen[cs]e|copying|copyright|notice|unlicense)", re.I)
SPDX_TEXT = (
    "https://raw.githubusercontent.com/spdx/license-list-data/main/text/{id}.txt"
)
# SPDX の表記のうち、ライセンスの名前でないもの
SPDX_WORDS = {"AND", "OR", "WITH"}
USER_AGENT = "llm-assist-kit-third-party-licenses"
NO_FILE_NOTE = (
    "(この部品にはライセンスファイルが入っていません。"
    "license 欄のライセンスの原文は末尾の付録にあります)"
)


@dataclass
class Component:
    name: str
    version: str
    license: str
    source: str = ""
    authors: list[str] = field(default_factory=list)
    # (ファイル名, 中身)
    files: list[tuple[str, str]] = field(default_factory=list)


def fetch(url: str) -> bytes:
    print(f"取得: {url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as res:
        return res.read()


def decode(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
    return text.strip("\n") + "\n"


def is_license_file(name: str) -> bool:
    return bool(LICENSE_NAME.match(name))


def license_files(directory: Path) -> list[tuple[str, str]]:
    """フォルダの直下にあるライセンスファイルを (名前, 中身) の一覧にする"""
    return [
        (f.name, decode(f.read_bytes()))
        for f in sorted(directory.iterdir(), key=lambda f: f.name.lower())
        if f.is_file() and is_license_file(f.name)
    ]


def spdx_ids(expression: str) -> list[str]:
    """ "MIT OR Apache-2.0" や "MIT/Apache-2.0" からライセンスの名前を取り出す"""
    ids = []
    for word in re.split(r"[\s()/]+", expression):
        if word and word not in SPDX_WORDS and word not in ids:
            ids.append(word.removesuffix("+"))
    return ids


def render(title: str, components: list[Component], preface: str = "") -> str:
    """部品の一覧を THIRD_PARTY_LICENSES.txt の文面にする"""
    components = sorted(components, key=lambda c: (c.name.lower(), c.version))
    lines = [title, "", preface.strip(), "", f"部品の数: {len(components)}", ""]
    missing: list[str] = []
    for c in components:
        lines += [RULE, f"{c.name} {c.version}".strip(), f"license: {c.license}"]
        if c.source:
            lines.append(f"source: {c.source}")
        if c.authors:
            lines.append("authors: " + ", ".join(c.authors))
        if not c.files:
            lines += ["", NO_FILE_NOTE, ""]
            missing += [i for i in spdx_ids(c.license) if i not in missing]
        for name, text in c.files:
            lines += [f"{'-' * 16} {name} {'-' * 16}", text]
    if missing:
        lines += [RULE, "付録: ライセンスの原文 (SPDX License List)", ""]
        for spdx_id in sorted(missing):
            try:
                text = decode(fetch(SPDX_TEXT.format(id=spdx_id)))
            except OSError as e:
                raise SystemExit(f"{spdx_id} の原文を取得できません: {e}") from e
            lines += [f"{'-' * 16} {spdx_id} {'-' * 16}", text]
    return "\n".join(lines).rstrip("\n") + "\n"


def read_zip_text(path: Path, name: str) -> str:
    with zipfile.ZipFile(path) as zf:
        return zf.read(name).decode("utf-8")


def build_info_value(info: str, key: str) -> str:
    """BUILD_INFO.txt の `key: 値` の値を返す"""
    m = re.search(rf"(?m)^{re.escape(key)}: (.+)$", info)
    if not m:
        raise SystemExit(f"BUILD_INFO.txt に {key} がありません")
    return m.group(1).strip()


def replace_in_zip(path: Path, files: dict[str, bytes]) -> None:
    """zip の中の実行ファイルはそのままにして、files のファイルだけを入れ替える"""
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w") as dst:
        for zi in src.infolist():
            if zi.filename not in files:
                dst.writestr(zi, src.read(zi), compresslevel=9)
        for name, data in files.items():
            dst.writestr(text_entry(name), data, compresslevel=9)
    tmp.replace(path)


def text_entry(name: str) -> zipfile.ZipInfo:
    zi = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
    zi.external_attr = 0o644 << 16
    zi.compress_type = zipfile.ZIP_DEFLATED
    return zi
