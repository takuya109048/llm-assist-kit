"""git の「dubious ownership」(Box などのフォルダ) への対処のテスト

init は safe.directory に登録して直し、addcommit・reset・ctx は分かりやすい案内を出す。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import gitsafe
import pytest

import install

COMMANDS = install.KIT / "commands"

ERROR = """\
fatal: detected dubious ownership in repository at 'C:/Box/my_project/生産計画／容器'
'C:/Box/my_project/生産計画／容器' is owned by:
\t/Everyone (S-1-1-0)
but the current user is:
\tPC/user (S-1-5-21-1)
To add an exception for this directory, call:

\tgit config --global --add safe.directory 'C:/Box/my_project/生産計画／容器'
"""


def test_detects_and_parses_git_error():
    assert gitsafe.is_dubious(ERROR)
    assert not gitsafe.is_dubious("fatal: not a git repository")
    assert (
        gitsafe.safe_directory(ERROR, Path("/x")) == "C:/Box/my_project/生産計画／容器"
    )
    assert gitsafe.safe_directory("fatal: dubious ownership", Path("/a/b")) == "/a/b"


# 所有者が自分でないフォルダを作るには root で chown する (Linux の CI では root でない)
needs_root = pytest.mark.skipif(
    shutil.which("git") is None or not hasattr(os, "geteuid") or os.geteuid() != 0,  # pyrefly: ignore[missing-attribute]
    reason="所有者の違うフォルダを作るには git と root 権限が要る",
)


@pytest.fixture
def foreign(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """所有者が別のユーザーのフォルダ (日本語・全角スラッシュ入り) と、git の設定を隔離した環境"""
    root = tmp_path / "生産計画／容器管理"
    root.mkdir()
    env = dict(
        os.environ,
        GIT_CONFIG_GLOBAL=str(tmp_path / "gitconfig"),
        GIT_CONFIG_NOSYSTEM="1",
        PYTHONIOENCODING="cp932",  # 日本語版 Windows のパイプ相当
    )
    env.pop("SUDO_UID", None)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=env)
    for p in [root, *root.rglob("*")]:
        os.chown(p, 65534, 65534)  # pyrefly: ignore[missing-attribute]
    r = subprocess.run(["git", "status"], cwd=root, capture_output=True, env=env)
    assert gitsafe.is_dubious(r.stderr.decode("utf-8", errors="replace"))
    return root, env


def run(cmd: list[str], cwd: Path, env: dict[str, str]) -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, env=env)
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", errors="replace")


@needs_root
def test_init_registers_safe_directory(foreign: tuple[Path, dict[str, str]]):
    root, env = foreign
    code, out = run([sys.executable, str(COMMANDS / "init.py")], root, env)
    assert code == 0, out
    assert "safe.directory に登録しました" in out
    code, out = run(["git", "status"], root, env)
    assert code == 0, out
    # 2 回目は登録済みなので何もしない
    code, out = run([sys.executable, str(COMMANDS / "init.py")], root, env)
    assert code == 0, out
    assert "すでに git のリポジトリ" in out
    assert "safe.directory" not in out


@needs_root
@pytest.mark.parametrize("script", ["addcommit.py", "reset.py"])
def test_commands_show_hint(foreign: tuple[Path, dict[str, str]], script: str):
    root, env = foreign
    args = ["msg"] if script == "addcommit.py" else ["-y"]
    code, out = run([sys.executable, str(COMMANDS / script), *args], root, env)
    assert code != 0
    assert "`init` を実行すると" in out
    assert "Traceback" not in out


@needs_root
def test_ctx_does_not_crash(foreign: tuple[Path, dict[str, str]]):
    root, env = foreign
    (root / "a.py").write_text("print(1)\n", encoding="utf-8")
    code, out = run(
        [sys.executable, str(install.KIT / "ctx.py"), "--stdout", "--no-skills"],
        root,
        env,
    )
    assert code == 0, out
    assert "Traceback" not in out and "UnicodeDecodeError" not in out
    assert "dubious ownership" in out
    assert "a.py" in out
