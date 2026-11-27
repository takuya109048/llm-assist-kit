"""同梱の実行ファイル (apply_patch.zip / marp.zip) のライセンス文と、それを作る tools/ のテスト"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "tools"))

import build_marp_zip  # noqa: E402
import third_party  # noqa: E402
from third_party import Component  # noqa: E402

APPLY_PATCH_ZIP = KIT / "skills" / "apply-patch" / "apply_patch.zip"
MARP_ZIP = KIT / "skills" / "marp-slides" / "marp.zip"


def read(zip_path: Path) -> tuple[set[str], str, str]:
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        info = zf.read("BUILD_INFO.txt").decode("utf-8")
        licenses = zf.read(third_party.FILE_NAME).decode("utf-8")
    return names, info, licenses


# 部品の見出し (ライセンス文の中にも = の行があるので、license 欄が続くものだけ)
HEADING = re.compile(rf"(?m)^{third_party.RULE}\n(?=.+\nlicense: )")


def component_names(licenses: str) -> list[str]:
    return [s.split("\n", 1)[0] for s in HEADING.split(licenses)[1:]]


# ---------------------------------------------------------------------------
# 同梱している zip
# ---------------------------------------------------------------------------


def test_apply_patch_zip_has_third_party_licenses():
    names, info, licenses = read(APPLY_PATCH_ZIP)
    assert {"LICENSE", "NOTICE", third_party.FILE_NAME} <= names
    assert third_party.FILE_NAME in info
    # Apache-2.0 第 4 条 b: ビルドのために変えたところを書く
    assert "modifications: " in info
    found = component_names(licenses)
    for name in ("Rust standard library", "mingw-w64 (CRT, winpthreads)", "similar"):
        assert any(n.startswith(name + " ") for n in found), name
    # codex 自身 (ワークスペースのクレート) は LICENSE / NOTICE で足りるので載せない
    assert not any(n.startswith("codex-") for n in found)
    toolchain = re.search(r"toolchain: rustc (\S+)", info)
    assert toolchain
    assert f"Rust standard library {toolchain.group(1)}" in found


def test_marp_zip_has_third_party_licenses():
    names, info, licenses = read(MARP_ZIP)
    assert {"LICENSE", third_party.FILE_NAME} <= names
    assert third_party.FILE_NAME in info
    node = re.search(r"(?m)^node: (v\S+)", info)
    assert node
    with zipfile.ZipFile(MARP_ZIP) as zf:
        exe = next(n for n in zf.namelist() if n.endswith(("/marp", "/marp.exe")))
        assert build_marp_zip.node_version(zf.read(exe)) == node.group(1)
    found = component_names(licenses)
    assert f"Node.js {node.group(1)}" in found
    for name in ("@marp-team/marp-core", "markdown-it", "puppeteer-core", "yargs"):
        assert any(n.startswith(name + " ") for n in found), name
    # 単体版を作る道具の依存 (esbuild など) は組み込まれないので載せない
    assert not any(n.startswith("esbuild ") for n in found)
    assert len(found) == len(set(found))


@pytest.mark.parametrize("zip_path", [APPLY_PATCH_ZIP, MARP_ZIP])
def test_every_component_has_license_text(zip_path: Path):
    """ライセンスファイルが無い部品は、付録に license 欄のライセンスの原文がある"""
    _, _, licenses = read(zip_path)
    body, _, appendix = licenses.partition("付録: ライセンスの原文")
    sections = HEADING.split(body)[1:]
    assert sections
    for section in sections:
        if third_party.NO_FILE_NOTE not in section:
            assert f"{'-' * 16} " in section
            continue
        expression = re.search(r"(?m)^license: (.+)$", section)
        assert expression
        for spdx_id in third_party.spdx_ids(expression.group(1)):
            assert f"{'-' * 16} {spdx_id} {'-' * 16}" in appendix, spdx_id


# ---------------------------------------------------------------------------
# tools/third_party.py
# ---------------------------------------------------------------------------


def test_is_license_file():
    for name in (
        "LICENSE",
        "LICENSE-MIT",
        "license.md",
        "LICENCE",
        "COPYING",
        "NOTICE",
    ):
        assert third_party.is_license_file(name)
    for name in ("README.md", "package.json", "src"):
        assert not third_party.is_license_file(name)


def test_spdx_ids():
    assert third_party.spdx_ids("MIT OR Apache-2.0") == ["MIT", "Apache-2.0"]
    assert third_party.spdx_ids("MIT/Apache-2.0") == ["MIT", "Apache-2.0"]
    assert third_party.spdx_ids("(Apache-2.0 OR MIT) AND BSD-3-Clause") == [
        "Apache-2.0",
        "MIT",
        "BSD-3-Clause",
    ]
    assert third_party.spdx_ids("Apache-2.0 WITH LLVM-exception") == [
        "Apache-2.0",
        "LLVM-exception",
    ]


def test_render_adds_spdx_text_for_components_without_files(monkeypatch):
    fetched = []

    def fake_fetch(url: str) -> bytes:
        fetched.append(url)
        return b"The MIT text\r\n"

    monkeypatch.setattr(third_party, "fetch", fake_fetch)
    text = third_party.render(
        "題",
        [
            Component("b", "2.0", "MIT", "https://b", ["Bob"]),
            Component("a", "1.0", "ISC", files=[("LICENSE", "ISC text\n")]),
        ],
        "前書き",
    )
    assert text.index("\na 1.0\n") < text.index("\nb 2.0\n")  # 名前の順
    assert "authors: Bob" in text
    assert third_party.NO_FILE_NOTE in text
    assert "---------------- LICENSE ----------------\nISC text\n" in text
    assert "---------------- MIT ----------------\nThe MIT text\n" in text
    assert fetched == [third_party.SPDX_TEXT.format(id="MIT")]


def test_replace_in_zip_keeps_other_entries(tmp_path: Path):
    path = tmp_path / "x.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zi = zipfile.ZipInfo("bin/tool", date_time=(2020, 1, 1, 0, 0, 0))
        zi.external_attr = 0o755 << 16
        zf.writestr(zi, b"binary")
        zf.writestr("BUILD_INFO.txt", "old")
    third_party.replace_in_zip(path, {"BUILD_INFO.txt": b"new", "NEW.txt": b"added"})
    with zipfile.ZipFile(path) as zf:
        assert zf.namelist() == ["bin/tool", "BUILD_INFO.txt", "NEW.txt"]
        assert zf.read("bin/tool") == b"binary"
        assert zf.getinfo("bin/tool").external_attr == 0o755 << 16
        assert zf.read("BUILD_INFO.txt") == b"new"


def test_build_info_value():
    info = "version: v4.5.1 (2026)\nbuilt: today\n"
    assert third_party.build_info_value(info, "version") == "v4.5.1 (2026)"
    with pytest.raises(SystemExit):
        third_party.build_info_value(info, "commit")


# ---------------------------------------------------------------------------
# tools/build_marp_zip.py
# ---------------------------------------------------------------------------


def test_node_version():
    exe = b"...https://nodejs.org/download/release/v26.8.1/...\0" * 3
    assert build_marp_zip.node_version(exe) == "v26.8.1"
    with pytest.raises(SystemExit):
        build_marp_zip.node_version(b"no version")


def test_package_name():
    assert build_marp_zip.package_name("yargs/helpers") == "yargs"
    assert build_marp_zip.package_name("@marp-team/marp-core/browser") == (
        "@marp-team/marp-core"
    )
    for spec in ("./a", "../b", "node:fs", "#imports", "/abs"):
        assert build_marp_zip.package_name(spec) is None


def test_bundled_imports_skips_type_only_and_tests(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.ts").write_text(
        "import chalk from 'chalk'\n"
        "import type { X } from 'only-types';\n"
        "import { y } from './local'\n"
        "const z = await import('pdf-lib')\n"
        "import 'side-effect'\n"
        "import fs from 'node:fs'\n",
        encoding="utf-8",
    )
    (src / "a.test.ts").write_text("import jest from 'jest'\n", encoding="utf-8")
    assert build_marp_zip.bundled_imports(src) == {"chalk", "pdf-lib", "side-effect"}


LOCK = {
    "packages": {
        "": {"dependencies": {"a": "^1"}},
        "node_modules/a": {"version": "1.0.0", "dependencies": {"b": "^1", "c": "^2"}},
        "node_modules/b": {"version": "1.0.0"},
        "node_modules/a/node_modules/c": {
            "version": "2.0.0",
            "dependencies": {"b": "1"},
        },
        "node_modules/c": {"version": "1.0.0"},
        "node_modules/a/node_modules/d": {"version": "1.0.0", "os": ["darwin"]},
        "node_modules/e": {
            "version": "1.0.0",
            "peerDependencies": {"b": "*", "f": "*"},
            "peerDependenciesMeta": {"f": {"optional": True}},
        },
        "node_modules/f": {"version": "1.0.0"},
    }
}


def test_resolve_walks_up_node_modules():
    packages = LOCK["packages"]
    assert build_marp_zip.resolve(packages, "node_modules/a", "c") == (
        "node_modules/a/node_modules/c"
    )
    assert build_marp_zip.resolve(packages, "node_modules/a/node_modules/c", "b") == (
        "node_modules/b"
    )
    assert build_marp_zip.resolve(packages, "", "c") == "node_modules/c"
    assert build_marp_zip.resolve(packages, "", "zzz") is None


def test_npm_closure_follows_deps_for_the_platform():
    lock = {"packages": {**LOCK["packages"]}}
    lock["packages"]["node_modules/a"] = {
        **lock["packages"]["node_modules/a"],
        "optionalDependencies": {"d": "^1"},
    }
    keys = build_marp_zip.npm_closure(lock, ["a"], ["windows-x86_64"])
    assert keys == ["node_modules/a", "node_modules/a/node_modules/c", "node_modules/b"]
    mac = build_marp_zip.npm_closure(lock, ["a"], ["macos-x86_64"])
    assert "node_modules/a/node_modules/d" in mac
    # 省略できる peer の依存はたどらない
    assert build_marp_zip.npm_closure(lock, ["e"], ["windows-x86_64"]) == [
        "node_modules/b",
        "node_modules/e",
    ]


def test_runs_on():
    win = [("win32", "x64")]
    assert build_marp_zip.runs_on({}, win)
    assert build_marp_zip.runs_on({"os": ["win32"], "cpu": ["x64"]}, win)
    assert not build_marp_zip.runs_on({"os": ["linux"]}, win)
    assert not build_marp_zip.runs_on({"os": ["!win32"]}, win)
    assert build_marp_zip.runs_on({"os": ["!darwin"]}, win)
    assert not build_marp_zip.runs_on({"cpu": ["arm64"]}, win)


def test_manifest_license():
    assert build_marp_zip.manifest_license({"license": "MIT"}) == "MIT"
    assert build_marp_zip.manifest_license({"license": {"type": "ISC"}}) == "ISC"
    assert (
        build_marp_zip.manifest_license(
            {"licenses": [{"type": "MIT"}, {"type": "GPL"}]}
        )
        == "MIT OR GPL"
    )
    assert build_marp_zip.manifest_license({}) == ""
