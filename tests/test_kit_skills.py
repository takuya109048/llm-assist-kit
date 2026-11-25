"""キットに同梱しているスキル (skills/) のテスト"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import ctx

KIT_SKILLS = Path(__file__).resolve().parent.parent / "skills"
SKILL_DIRS = sorted(p for p in KIT_SKILLS.iterdir() if (p / "SKILL.md").is_file())
HAS_GIT = shutil.which("git") is not None


def run_script(script: str, *args: str, cwd: Path) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, str(KIT_SKILLS / script), *args],
        capture_output=True,
        cwd=cwd,
        env=dict(ctx.os.environ, PYTHONIOENCODING="utf-8"),
    )
    return r.returncode, (r.stdout + r.stderr).decode("utf-8").replace("\r\n", "\n")


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# SKILL.md の形式
# ---------------------------------------------------------------------------


def test_kit_has_skills():
    assert [p.name for p in SKILL_DIRS] == [
        "apply-patch",
        "git-diff",
        "run-tests",
        "search",
    ]


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_md_is_valid(skill_dir: Path):
    meta, body = ctx.parse_frontmatter(ctx.read_text(skill_dir / "SKILL.md"))
    assert meta.get("name") == skill_dir.name
    assert meta.get("description")
    assert body.strip()
    # 実行例は ctx.py run 経由で、参照しているスクリプトは実在する
    assert "python ${CTX} run --" in body
    for ref in re.findall(r"\$\{SKILL_DIR\}/([\w./-]+)", body):
        assert (skill_dir / ref).is_file(), ref


# ---------------------------------------------------------------------------
# search.py
# ---------------------------------------------------------------------------


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text(
        "import os\n\ndef Foo():\n    return foo_bar()\n", encoding="utf-8"
    )
    (root / "src" / "b.txt").write_text("foo(1)\nbar\n", encoding="utf-8")
    (root / "sjis.txt").write_bytes("日本語の foo\n".encode("cp932"))
    (root / "bin.dat").write_bytes(b"foo\0\1")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "x.js").write_text("foo", encoding="utf-8")
    return root


def test_search_regex(tree: Path):
    code, out = run_script("search/search.py", "foo", cwd=tree)
    assert code == 0
    assert out.splitlines()[:3] == [
        "sjis.txt:1: 日本語の foo",
        "src/a.py:4:     return foo_bar()",
        "src/b.txt:1: foo(1)",
    ]
    assert "bin.dat" not in out
    assert "node_modules" not in out
    assert out.rstrip().endswith("3 件 / 3 ファイル")


def test_search_options(tree: Path):
    # -F: ( を文字として扱う。-i: Foo( にもマッチ
    _, out = run_script("search/search.py", "-F", "-i", "FOO(", cwd=tree)
    assert out.splitlines()[:2] == ["src/a.py:3: def Foo():", "src/b.txt:1: foo(1)"]
    _, out = run_script("search/search.py", "-i", "foo", "-g", "*.py", cwd=tree)
    assert out.splitlines()[:2] == [
        "src/a.py:3: def Foo():",
        "src/a.py:4:     return foo_bar()",
    ]
    _, out = run_script("search/search.py", "Foo", "-C", "1", "src", cwd=tree)
    assert out.splitlines()[:3] == [
        "src/a.py-2- ",
        "src/a.py:3: def Foo():",
        "src/a.py-4-     return foo_bar()",
    ]


def test_search_max(tree: Path):
    _, out = run_script("search/search.py", "o", "--max", "2", cwd=tree)
    assert "2 件" in out
    assert "最大 2 件で打ち切り" in out


def test_search_no_match_and_bad_regex(tree: Path):
    assert run_script("search/search.py", "zzz", cwd=tree) == (
        1,
        "見つかりませんでした: zzz\n",
    )
    code, out = run_script("search/search.py", "(", cwd=tree)
    assert code == 2
    assert "正規表現が不正です" in out


@pytest.mark.skipif(not HAS_GIT, reason="git が無い")
def test_search_respects_gitignore(tree: Path):
    git(tree, "init", "-q")
    (tree / ".gitignore").write_text("src/b.txt\n", encoding="utf-8")
    _, out = run_script("search/search.py", "foo", cwd=tree)
    assert "src/b.txt" not in out
    assert "src/a.py:4:" in out


# ---------------------------------------------------------------------------
# diff.py
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_GIT, reason="git が無い")
def test_diff(tmp_path: Path):
    git(tmp_path, "init", "-q")
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "init")
    (tmp_path / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("y\n", encoding="utf-8")
    git(tmp_path, "add", "b.txt")
    (tmp_path / "new.txt").write_text("new\n", encoding="utf-8")

    code, out = run_script("git-diff/diff.py", cwd=tmp_path)
    assert code == 0
    sections = out.split("===== ")
    assert [s.split(" =====")[0] for s in sections[1:]] == [
        "git status --short",
        "git diff --stat (未ステージ)",
        "git diff --stat (ステージ済み)",
        "git diff (未ステージ)",
        "git diff (ステージ済み)",
    ]
    assert " M a.txt" in sections[1] and "M  b.txt" in sections[1]
    assert "?? new.txt" in sections[1]
    assert "+two" in sections[4]
    assert "-x\n+y" in sections[5]

    # パス指定で絞り込み
    _, out = run_script("git-diff/diff.py", "a.txt", cwd=tmp_path)
    assert "b.txt" not in out
    assert "+two" in out


def test_diff_outside_git(tmp_path: Path):
    if HAS_GIT:
        # tmp_path が別の git リポジトリの中にある環境では判定できない
        r = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=tmp_path,
            capture_output=True,
        )
        if r.returncode == 0:
            pytest.skip("tmp_path が git リポジトリの中にある")
    code, out = run_script("git-diff/diff.py", cwd=tmp_path)
    assert code == 1
    assert "git" in out


@pytest.mark.parametrize(
    ("script", "args"),
    [("search/search.py", ["foo"]), ("git-diff/diff.py", [])],
)
def test_scripts_print_utf8_on_single_byte_console(
    script: str, args: list[str], tree: Path
):
    """英語版 Windows でパイプに出すとき (cp1252) も日本語の出力で落ちない"""
    r = subprocess.run(
        [sys.executable, str(KIT_SKILLS / script), *args],
        capture_output=True,
        cwd=tree,
        env=dict(ctx.os.environ, PYTHONIOENCODING="cp1252"),
    )
    out = (r.stdout + r.stderr).decode("utf-8")
    assert "Traceback" not in out
    assert "UnicodeEncodeError" not in out


def test_apply_patch_assumes_previous_patch_applied():
    """結果が貼られないまま次の依頼が来ても、確認コマンドを出さずに続ける決まりがある

    (以前、適用できたか分からないとして確認用のコマンドを出してしまったことへの対策)
    """
    _, body = ctx.parse_frontmatter(
        ctx.read_text(KIT_SKILLS / "apply-patch" / "SKILL.md")
    )
    assert "前のパッチは成功して適用済みとみなします" in body
    assert "確認や、ファイルの現在の内容を\n   表示するコマンドを先に出さず" in body
    assert "すべて適用した後の内容" in body


def test_preamble_lets_skills_override_waiting_for_results():
    """共通の説明の「結果を待つ」は実行結果の中身に限り、スキルの決まりを優先する"""
    assert "結果が貼られるまで、実行結果を推測で決めつけないでください。" not in (
        ctx.SKILLS_PREAMBLE
    )
    assert "各スキルに別の決まりがあれば、そちらに従ってください" in ctx.SKILLS_PREAMBLE
