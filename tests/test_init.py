"""commands/init.py (PowerShell の関数 init) のテスト"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import ctx
import install

SCRIPT = Path(__file__).resolve().parent.parent / "commands" / "init.py"

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git が無い")


def run_init(cwd: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        env=dict(os.environ, PYTHONIOENCODING="cp1252"),  # 英語版 Windows のパイプ相当
    )
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", errors="replace")


def test_registered_in_install():
    f = next(f for f in install.FUNCTIONS if f.name == "init")
    assert f.script == "commands/init.py"


@needs_git
def test_creates_files_and_git(tmp_path: Path):
    code, out = run_init(tmp_path)
    assert code == 0, out
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith(ctx.DEFAULT_PROMPT)
    assert "# プロジェクトの概要" in agents
    assert (tmp_path / ".ctxignore").is_file()
    assert ".venv/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert (tmp_path / ".git").is_dir()
    assert "git init しました" in out


@needs_git
def test_creates_missing_dir(tmp_path: Path):
    code, out = run_init(tmp_path, "新規/プロジェクト")
    assert code == 0, out
    root = tmp_path / "新規" / "プロジェクト"
    assert (root / "AGENTS.md").is_file()
    assert (root / ".git").is_dir()


@needs_git
def test_keeps_existing_files_and_repo(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("mine\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    sub = tmp_path / "sub"
    sub.mkdir()
    code, out = run_init(tmp_path)
    assert code == 0, out
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "mine\n"
    assert "すでに git のリポジトリ" in out
    # 親がリポジトリなら、その中のフォルダでも git init しない
    code, out = run_init(sub)
    assert code == 0, out
    assert not (sub / ".git").exists()


def test_no_git(tmp_path: Path):
    code, out = run_init(tmp_path, "--no-git")
    assert code == 0, out
    assert (tmp_path / "AGENTS.md").is_file()
    assert not (tmp_path / ".git").exists()


def test_ctx_uses_generated_files(tmp_path: Path):
    run_init(tmp_path, "--no-git")
    (tmp_path / "a.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "secret.csv").write_text("x\n", encoding="utf-8")
    with (tmp_path / ".ctxignore").open("a", encoding="utf-8") as f:
        f.write("*.csv\n")
    r = subprocess.run(
        [sys.executable, str(install.KIT / "ctx.py"), "--stdout", "--no-skills"],
        cwd=tmp_path,
        capture_output=True,
    )
    out = r.stdout.decode("utf-8")
    assert r.returncode == 0
    assert "# プロジェクトの概要" in out
    assert "a.py" in out and "secret.csv" not in out
