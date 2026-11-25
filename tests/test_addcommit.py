"""commands/addcommit.py (PowerShell の関数 addcommit) のテスト"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import install

SCRIPT = Path(__file__).resolve().parent.parent / "commands" / "addcommit.py"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git が無い")


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)
    return r.stdout.decode("utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "t")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "commit.gpgsign", "false")
    return root


def addcommit(repo: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=repo,
        capture_output=True,
        env=dict(os.environ, PYTHONIOENCODING="cp1252"),  # 英語版 Windows のパイプ相当
    )
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", errors="replace")


def last_message(repo: Path) -> str:
    return git(repo, "log", "-1", "--format=%s").strip()


def test_adds_all_changes_and_commits(repo: Path):
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    code, _ = addcommit(repo, "最初のコミット")
    assert code == 0
    assert last_message(repo) == "最初のコミット"

    # 追加・変更・削除がすべて入る
    (repo / "a.txt").unlink()
    (repo / "b.txt").write_text("b\n", encoding="utf-8")
    (repo / "sub").mkdir()
    (repo / "sub" / "c.txt").write_text("c\n", encoding="utf-8")
    code, _ = addcommit(repo, "変更")
    assert code == 0
    changed = git(repo, "show", "--name-status", "--format=", "HEAD").split()
    assert changed == ["D", "a.txt", "A", "b.txt", "A", "sub/c.txt"]
    assert git(repo, "status", "--porcelain") == ""


def test_words_are_joined_into_one_message(repo: Path):
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    assert addcommit(repo, "fix:", "日本語の", "メッセージ")[0] == 0
    assert last_message(repo) == "fix: 日本語の メッセージ"


def test_no_message_shows_usage(repo: Path):
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    code, out = addcommit(repo)
    assert code == 2
    assert "使い方: addcommit <コミットメッセージ>" in out
    # 何もしない (ステージもしない)
    assert git(repo, "status", "--porcelain").startswith("??")


def test_nothing_to_commit_returns_git_exit_code(repo: Path):
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    addcommit(repo, "first")
    code, out = addcommit(repo, "second")
    assert code != 0
    assert "nothing to commit" in out


def test_outside_git_repository(tmp_path: Path):
    r = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=tmp_path, capture_output=True
    )
    if r.returncode == 0:
        pytest.skip("tmp_path が git リポジトリの中にある")
    code, out = addcommit(tmp_path, "msg")
    assert code != 0
    assert "not a git repository" in out


def test_registered_in_install():
    names = {f.name: f for f in install.FUNCTIONS}
    assert names["addcommit"].script == "commands/addcommit.py"


@pytest.mark.parametrize(
    "shell", [ps for ps in install.POWERSHELLS if shutil.which(ps)] or ["(none)"]
)
def test_addcommit_function_in_powershell(shell: str, repo: Path, tmp_path: Path):
    """install.py で登録した関数 addcommit を、実際の PowerShell で使う"""
    if shell == "(none)":
        pytest.skip("PowerShell が無い")
    profile = tmp_path / "profile.ps1"
    assert install.main(["--profile", str(profile), "--python", sys.executable]) == 0
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    command = (
        f". {install.ps_quote(str(profile))}; "
        f"Set-Location {install.ps_quote(str(repo))}; "
        "addcommit 日本語の メッセージ"
    )
    script = tmp_path / "run.ps1"
    script.write_text(command, encoding="utf-8-sig")
    r = subprocess.run(
        [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
    )
    out = r.stdout.decode("utf-8", errors="replace")
    assert r.returncode == 0, out + r.stderr.decode("utf-8", errors="replace")
    assert last_message(repo) == "日本語の メッセージ"
    assert git(repo, "status", "--porcelain") == ""
