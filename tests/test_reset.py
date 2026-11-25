"""commands/reset.py (PowerShell の関数 reset) のテスト"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import install

SCRIPT = Path(__file__).resolve().parent.parent / "commands" / "reset.py"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git が無い")


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)
    return r.stdout.decode("utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """コミット済みの a.txt・b.txt と、無視する ignored.log があるリポジトリ"""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "t")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "commit.gpgsign", "false")
    # Windows の git は既定で改行を CRLF にして取り出すので、内容の比較のために止める
    git(root, "config", "core.autocrlf", "false")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    (root / "b.txt").write_text("b\n", encoding="utf-8")
    (root / ".gitignore").write_text("ignored.log\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    return root


def make_changes(repo: Path) -> None:
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    (repo / "b.txt").unlink()
    (repo / "新規.txt").write_text("new\n", encoding="utf-8")
    (repo / "newdir").mkdir()
    (repo / "newdir" / "x.txt").write_text("x\n", encoding="utf-8")
    (repo / "ignored.log").write_text("keep\n", encoding="utf-8")
    git(repo, "add", "a.txt")  # ステージ済みの変更も戻ること


def run_reset(repo: Path, *args: str, answer: str | None = None) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=repo,
        capture_output=True,
        input=None if answer is None else answer.encode(),
        env=dict(os.environ, PYTHONIOENCODING="cp1252"),  # 英語版 Windows のパイプ相当
    )
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", errors="replace")


def assert_clean(repo: Path) -> None:
    assert (repo / "a.txt").read_text(encoding="utf-8") == "a\n"
    assert (repo / "b.txt").read_text(encoding="utf-8") == "b\n"
    assert not (repo / "新規.txt").exists()
    assert not (repo / "newdir").exists()
    # .gitignore で無視しているファイルは残る
    assert (repo / "ignored.log").read_text(encoding="utf-8") == "keep\n"
    assert git(repo, "status", "--porcelain") == ""


def test_confirm_yes_resets_and_cleans(repo: Path):
    make_changes(repo)
    code, out = run_reset(repo, answer="y\n")
    assert code == 0, out
    assert "元に戻すファイル (git reset --hard HEAD):" in out
    assert "M  a.txt" in out and " D b.txt" in out
    assert "削除するファイル・フォルダ (git clean -fd):" in out
    assert "Would remove 新規.txt" in out  # 日本語のファイル名がそのまま表示される
    assert "Would remove newdir/" in out
    assert "ignored.log" not in out
    assert_clean(repo)


@pytest.mark.parametrize("answer", ["n\n", "\n", ""])
def test_cancel_changes_nothing(repo: Path, answer: str):
    make_changes(repo)
    before = git(repo, "status", "--porcelain")
    code, out = run_reset(repo, answer=answer)
    assert code == 1
    assert "中止しました" in out
    assert git(repo, "status", "--porcelain") == before
    assert (repo / "新規.txt").exists()


def test_yes_option_skips_confirmation(repo: Path):
    make_changes(repo)
    code, out = run_reset(repo, "-y")
    assert code == 0, out
    assert "よろしいですか" not in out
    assert_clean(repo)


def test_nothing_to_reset(repo: Path):
    (repo / "ignored.log").write_text("keep\n", encoding="utf-8")
    code, out = run_reset(repo)
    assert code == 0
    assert "元に戻す変更はありません" in out


def test_outside_git_repository(tmp_path: Path):
    r = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=tmp_path, capture_output=True
    )
    if r.returncode == 0:
        pytest.skip("tmp_path が git リポジトリの中にある")
    (tmp_path / "keep.txt").write_text("x", encoding="utf-8")
    code, out = run_reset(tmp_path, "-y")
    assert code != 0
    assert "not a git repository" in out
    assert (tmp_path / "keep.txt").exists()


def test_registered_in_install():
    names = {f.name: f for f in install.FUNCTIONS}
    assert names["reset"].script == "commands/reset.py"


@pytest.mark.parametrize(
    "shell", [ps for ps in install.POWERSHELLS if shutil.which(ps)] or ["(none)"]
)
def test_reset_function_in_powershell(shell: str, repo: Path, tmp_path: Path):
    """install.py で登録した関数 reset を、実際の PowerShell で使う"""
    if shell == "(none)":
        pytest.skip("PowerShell が無い")
    profile = tmp_path / "profile.ps1"
    assert install.main(["--profile", str(profile), "--python", sys.executable]) == 0
    make_changes(repo)
    command = (
        f". {install.ps_quote(str(profile))}; "
        f"Set-Location {install.ps_quote(str(repo))}; "
        "reset -y"
    )
    r = subprocess.run(
        [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
    )
    out = r.stdout.decode("utf-8", errors="replace")
    assert r.returncode == 0, out + r.stderr.decode("utf-8", errors="replace")
    assert_clean(repo)
