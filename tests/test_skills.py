"""スキル (SKILL.md) の挿入と `ctx.py run` のテスト"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import ctx


def write(root: Path, rel: str, content: str | bytes) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content, encoding="utf-8")
    return p


def skill_md(name: str | None = None, description: str = "", body: str = "") -> str:
    meta = []
    if name is not None:
        meta.append(f"name: {name}")
    if description:
        meta.append(f"description: {description}")
    return "---\n" + "\n".join(meta) + "\n---\n" + body


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = tmp_path / "proj"
    r.mkdir()
    write(r, "src/main.py", "print('hi')\n")
    return r


def run_ctx(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    capsys.readouterr()
    rc = ctx.main(list(argv))
    out, err = capsys.readouterr()
    return rc, out, err


# ---------------------------------------------------------------------------
# parse_frontmatter
# ---------------------------------------------------------------------------


def test_frontmatter_basic():
    meta, body = ctx.parse_frontmatter(
        "---\nname: a\ndescription: 説明: コロン入り\n---\n\n本文\n"
    )
    assert meta == {"name": "a", "description": "説明: コロン入り"}
    assert body == "本文"


def test_frontmatter_quoted_and_ignored_lines():
    meta, _ = ctx.parse_frontmatter(
        "---\nname: \"q\"\ndescription: 'x'\n# comment\n  nested: 1\nbad\n---\n"
    )
    assert meta == {"name": "q", "description": "x"}


@pytest.mark.parametrize("text", ["本文だけ\n", "---\nname: a\n本文 (閉じない)\n", ""])
def test_frontmatter_absent_or_unclosed(text: str):
    meta, body = ctx.parse_frontmatter(text)
    assert meta == {}
    assert body == text


# ---------------------------------------------------------------------------
# load_skills
# ---------------------------------------------------------------------------


def test_load_skills_discovery(root: Path):
    write(root, ".ctx/skills/b-skill/SKILL.md", skill_md("beta", "B の説明", "B 本文"))
    write(root, ".ctx/skills/a-skill/SKILL.md", "フロントマター無し")
    write(root, ".ctx/skills/a-skill/run.py", "print(1)\n")
    write(root, ".ctx/skills/a-skill/lib/util.py", "x = 1\n")
    write(root, ".ctx/skills/a-skill/__pycache__/run.cpython.pyc", b"\0")
    write(root, ".ctx/skills/not-a-skill/README.md", "SKILL.md が無い")
    write(root, ".claude/skills/gamma/SKILL.md", skill_md(description="C"))
    skills = ctx.load_skills(root, ctx.SKILL_DIRS, None)
    assert [s.name for s in skills] == ["a-skill", "beta", "gamma"]
    a, b, c = skills
    assert a.description == ""
    assert a.body == "フロントマター無し"
    assert a.dir == ".ctx/skills/a-skill"
    assert a.skill_file == ".ctx/skills/a-skill/SKILL.md"
    assert a.files == ["lib/util.py", "run.py"]
    assert (b.description, b.body, b.files) == ("B の説明", "B 本文", [])
    assert c.dir == ".claude/skills/gamma"


def test_load_skills_first_dir_wins_on_same_name(root: Path):
    write(root, ".ctx/skills/x/SKILL.md", skill_md("same", body="ctx 側"))
    write(root, ".claude/skills/y/SKILL.md", skill_md("same", body="claude 側"))
    skills = ctx.load_skills(root, ctx.SKILL_DIRS, None)
    assert [(s.name, s.body) for s in skills] == [("same", "ctx 側")]


def test_load_skills_substitutes_skill_dir(root: Path):
    write(
        root,
        ".ctx/skills/s/SKILL.md",
        skill_md("s", body="python ${SKILL_DIR}/a.py ${SKILL_DIR}/b.py"),
    )
    (skill,) = ctx.load_skills(root, ctx.SKILL_DIRS, None)
    assert skill.body == "python .ctx/skills/s/a.py .ctx/skills/s/b.py"


def test_load_skills_select_in_given_order(root: Path):
    for n in ["a", "b", "c"]:
        write(root, f".ctx/skills/{n}/SKILL.md", skill_md(n))
    skills = ctx.load_skills(root, ctx.SKILL_DIRS, ["c", "a"])
    assert [s.name for s in skills] == ["c", "a"]
    with pytest.raises(ValueError, match="zzz"):
        ctx.load_skills(root, ctx.SKILL_DIRS, ["a", "zzz"])


def test_load_skills_none(root: Path):
    assert ctx.load_skills(root, ctx.SKILL_DIRS, None) == []


# ---------------------------------------------------------------------------
# コンテキストへの挿入
# ---------------------------------------------------------------------------


@pytest.fixture
def skilled(root: Path) -> Path:
    write(root, "CONTEXT_PROMPT.md", "冒頭プロンプト")
    write(
        root,
        ".ctx/skills/check/SKILL.md",
        skill_md("check", "テストを実行する", "python ctx.py run -- pytest -q"),
    )
    write(root, ".ctx/skills/check/helper.py", "print('helper')\n")
    return root


def test_skills_section_in_context(skilled: Path, capsys: pytest.CaptureFixture[str]):
    rc, out, err = run_ctx(capsys, str(skilled), "--no-git", "--stdout")
    assert rc == 0
    # 冒頭プロンプト → スキル → プロジェクトの順
    assert out.startswith("冒頭プロンプト\n")
    assert out.index("# スキル") < out.index("# プロジェクト: proj")
    assert "あなたはスクリプトやコマンドを直接実行できません" in out
    assert "## スキル: check\n" in out
    assert "- 説明: テストを実行する" in out
    assert "- フォルダ: `.ctx/skills/check/`" in out
    assert "- ファイル: `.ctx/skills/check/helper.py`" in out
    # SKILL.md はスキル欄に入るので本文には重複させない。スクリプトは本文に入る
    assert "### .ctx/skills/check/SKILL.md" not in out
    assert "### .ctx/skills/check/helper.py" in out
    assert "スキル 1" in err


def test_no_skills_and_select(skilled: Path, capsys: pytest.CaptureFixture[str]):
    write(skilled, ".ctx/skills/other/SKILL.md", skill_md("other"))
    _, out, _ = run_ctx(capsys, str(skilled), "--no-git", "--stdout", "--no-skills")
    assert "# スキル" not in out
    # --no-skills のときは SKILL.md も普通のファイルとして本文に入る
    assert "### .ctx/skills/check/SKILL.md" in out
    _, out, _ = run_ctx(capsys, str(skilled), "--no-git", "--stdout", "-s", "other")
    assert "## スキル: other" in out
    assert "## スキル: check" not in out
    assert "### .ctx/skills/check/SKILL.md" in out


def test_unknown_skill_is_error(skilled: Path, capsys: pytest.CaptureFixture[str]):
    rc, _, err = run_ctx(capsys, str(skilled), "--no-git", "--stdout", "-s", "nope")
    assert rc == 1
    assert "スキルが見つかりません: nope" in err
    assert "check" in err


def test_skills_dir_option(root: Path, capsys: pytest.CaptureFixture[str]):
    write(root, "prompts/skills/x/SKILL.md", skill_md("x"))
    write(root, ".ctx/skills/y/SKILL.md", skill_md("y"))
    _, out, _ = run_ctx(
        capsys, str(root), "--no-git", "--stdout", "--skills-dir", "prompts/skills"
    )
    assert "## スキル: x" in out
    assert "## スキル: y" not in out


def test_list_shows_skills(skilled: Path, capsys: pytest.CaptureFixture[str]):
    rc, out, err = run_ctx(capsys, str(skilled), "--no-git", "--list")
    assert rc == 0
    assert "skill  check  (.ctx/skills/check/SKILL.md)" in out
    assert " tok  .ctx/skills/check/helper.py" in out
    assert "tok  .ctx/skills/check/SKILL.md" not in out
    assert "スキル 1" in err


def test_runner_path_when_ctx_is_in_project(skilled: Path):
    """ctx.py をプロジェクトに置いたとき、スキル欄の実行例はその置き場所を指す"""
    tools = skilled / "tools"
    tools.mkdir()
    shutil.copy(ctx.__file__, tools / "ctx.py")
    r = subprocess.run(
        [sys.executable, str(tools / "ctx.py"), "..", "--no-git", "--stdout"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=tools,
    )
    assert r.returncode == 0, r.stderr
    assert "`python tools/ctx.py run --`" in r.stdout


# ---------------------------------------------------------------------------
# run: 出力の整形
# ---------------------------------------------------------------------------


def test_format_run_result():
    text = ctx.format_run_result("pytest -q", 1, "a\nb\n", 0)
    assert text == (
        "## 実行結果\n\n"
        "```powershell\nPS> pytest -q\n```\n\n"
        "- 終了コード: 1 (失敗)\n\n"
        "```text\na\nb\n```\n"
    )


def test_format_run_result_success_and_empty():
    text = ctx.format_run_result("x", 0, "\n", 200)
    assert "- 終了コード: 0 (成功)" in text
    assert "```text\n(出力なし)\n```" in text


def test_format_run_result_tail():
    output = "\n".join(str(i) for i in range(1, 11))
    text = ctx.format_run_result("x", 0, output, 3)
    assert "(先頭 7 行を省略。全 10 行のうち最後の 3 行)\n8\n9\n10\n" in text
    assert "\n7\n" not in text


def test_format_run_result_fences_backticks():
    text = ctx.format_run_result("x", 0, "```\ncode\n```", 0)
    assert "````text\n```\ncode\n```\n````" in text


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ("日本語\r\n".encode(), "日本語\n"),
        ("日本語".encode("cp932"), "日本語"),
        (b"\x1b[31mred\x1b[0m \x1b]0;title\x07ok", "red ok"),
        (b"10%\r50%\r100%\ndone", "100%\ndone"),
    ],
)
def test_decode_output(data: bytes, expected: str):
    assert ctx.decode_output(data) == expected


def test_decode_output_cp932_on_single_byte_locale(monkeypatch: pytest.MonkeyPatch):
    """英語版 Windows (既定 cp1252) でも cp932 の出力を化けさせない"""
    monkeypatch.setattr(ctx.locale, "getpreferredencoding", lambda _=True: "cp1252")
    assert ctx.decode_output("日本語".encode("cp932")) == "日本語"
    # UTF-8 でも cp932 でも読めないものは OS の既定で読む
    assert ctx.decode_output("café".encode("cp1252")) == "café"


# ---------------------------------------------------------------------------
# run: 実行
# ---------------------------------------------------------------------------

PY = sys.executable


def run_stdout(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    capsys.readouterr()
    rc = ctx.main(["run", "--stdout", *argv])
    return rc, capsys.readouterr().out


def test_run_merges_output_and_returns_exit_code(capsys: pytest.CaptureFixture[str]):
    code = (
        "import sys; print('標準出力'); print('エラー', file=sys.stderr); sys.exit(3)"
    )
    rc, out = run_stdout(capsys, "--", PY, "-c", code)
    assert rc == 3
    assert "- 終了コード: 3 (失敗)" in out
    assert "標準出力\nエラー\n```" in out
    assert f"PS> {PY} -c" in out or f'PS> "{PY}" -c' in out


def test_run_tail_option(capsys: pytest.CaptureFixture[str]):
    rc, out = run_stdout(
        capsys, "--tail", "2", "--", PY, "-c", "for i in range(5): print(i)"
    )
    assert rc == 0
    assert "(先頭 3 行を省略。全 5 行のうち最後の 2 行)\n3\n4\n" in out


def test_run_missing_command(capsys: pytest.CaptureFixture[str]):
    rc, out = run_stdout(capsys, "--", "no-such-command-xyz", "arg")
    assert rc == 127
    assert "コマンドが見つかりません: no-such-command-xyz" in out


def test_run_shell_string(capsys: pytest.CaptureFixture[str]):
    if sys.platform == "win32":
        command = "Write-Output 'あ'; Write-Output b; exit 4"
    else:
        command = "echo あ; echo b 1>&2; exit 4"
    rc, out = run_stdout(capsys, command)
    assert rc == 4
    assert f"PS> {command}\n" in out
    assert "あ\nb\n" in out


def test_run_requires_command(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit):
        ctx.main(["run"])
    with pytest.raises(SystemExit):
        ctx.main(["run", "--"])


def test_run_unquoted_command_needs_double_dash():
    # -- が無いと -q を ctx.py のオプションとして解釈してしまうのでエラーにする
    with pytest.raises(SystemExit):
        ctx.main(["run", "pytest", "-q"])


def test_run_output_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    out = tmp_path / "result.md"
    rc = ctx.main(["run", "-o", str(out), "--", PY, "-c", "print('ok')"])
    assert rc == 0
    assert "```text\nok\n```" in out.read_text(encoding="utf-8")
    assert "に出力しました" in capsys.readouterr().err


def test_run_copies_to_clipboard(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    copied: list[str] = []

    def fake_copy(text: str) -> str:
        copied.append(text)
        return "fake"

    monkeypatch.setattr(ctx, "copy_to_clipboard", fake_copy)
    rc = ctx.main(["run", "--", PY, "-c", "print('clip')"])
    assert rc == 0
    assert copied and "```text\nclip\n```" in copied[0]
    err = capsys.readouterr().err
    assert "clip" in err  # 実行中の出力は画面にも流れる
    assert "実行結果をクリップボードにコピーしました (fake)" in err


def test_run_clipboard_failure_keeps_failure_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    def fail(text: str) -> str:
        raise OSError("no clipboard")

    monkeypatch.setattr(ctx, "copy_to_clipboard", fail)
    assert ctx.main(["run", "--", PY, "-c", "pass"]) == 1
    assert ctx.main(["run", "--", PY, "-c", "raise SystemExit(5)"]) == 5
    assert "--stdout" in capsys.readouterr().err
