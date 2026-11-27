"""tools/build_release.py (リリース用の zip と説明文) のテスト"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "tools"))

import build_release  # noqa: E402


def test_changelog_has_notes_for_the_current_version():
    tag = build_release.tag_for(build_release.project_version())
    notes = build_release.release_notes(tag)
    assert f"{build_release.NAME}-{tag}.zip" in notes
    assert not re.search(r"(?m)^## ", notes)  # 次の版の節を含まない


def test_tag_for_checks_pyproject_version():
    version = build_release.project_version()
    assert build_release.tag_for(version) == f"v{version}"
    assert build_release.tag_for(f"v{version}") == f"v{version}"
    with pytest.raises(SystemExit):
        build_release.tag_for("v999.0.0")
    with pytest.raises(SystemExit):
        build_release.tag_for("latest")


def test_release_notes_takes_only_that_section(tmp_path: Path):
    (tmp_path / "CHANGELOG.md").write_text(
        "# 変更履歴\n\n## v0.2.0 (2027-01-01)\n\n新しい\n\n"
        "## v0.1.0 (2026-11-27)\n\n最初\n",
        encoding="utf-8",
    )
    assert build_release.release_notes("v0.2.0", tmp_path) == "新しい\n"
    assert build_release.release_notes("v0.1.0", tmp_path) == "最初\n"
    with pytest.raises(SystemExit):
        build_release.release_notes("v0.0.1", tmp_path)


def test_release_files_drop_dev_only_files():
    files = ["ctx.py", "tests/test_ctx.py", "tools/x.py", ".github/workflows/ci.yml"]
    assert build_release.release_files(files) == ["ctx.py"]


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_build_zip_from_tracked_files(tmp_path: Path):
    root = tmp_path / "kit"
    (root / "skills" / "s").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "ctx.py").write_text("print(1)\n", encoding="utf-8")
    (root / "skills" / "s" / "bin.zip").write_bytes(b"PK fake")
    (root / "tests" / "test_x.py").write_text("", encoding="utf-8")
    (root / "untracked.txt").write_text("", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", "ctx.py", "skills", "tests")
    output = tmp_path / "out.zip"
    files = build_release.build_zip("v0.1.0", output, root)
    assert files == ["ctx.py", "skills/s/bin.zip"]
    with zipfile.ZipFile(output) as zf:
        assert zf.namelist() == [
            "llm-assist-kit-v0.1.0/ctx.py",
            "llm-assist-kit-v0.1.0/skills/s/bin.zip",
        ]
        inner = zf.getinfo("llm-assist-kit-v0.1.0/skills/s/bin.zip")
        assert inner.compress_type == zipfile.ZIP_STORED
        assert zf.read("llm-assist-kit-v0.1.0/ctx.py") == b"print(1)\n"


def test_release_contains_licenses():
    files = build_release.release_files(build_release.tracked_files())
    for name in (
        "LICENSE",
        "README.md",
        "CHANGELOG.md",
        "skills/apply-patch/apply_patch.zip",
        "skills/marp-slides/marp.zip",
    ):
        assert name in files
