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
# load_skills (スキルはプロジェクトの外に置く)
# ---------------------------------------------------------------------------


@pytest.fixture
def kit(tmp_path: Path) -> Path:
    """プロジェクトの外にあるスキル置き場 (キットの skills/ に相当)"""
    k = tmp_path / "kit" / "skills"
    k.mkdir(parents=True)
    return k


def test_load_skills_discovery(root: Path, kit: Path):
    write(kit, "b-skill/SKILL.md", skill_md("beta", "B の説明", "B 本文"))
    write(kit, "a-skill/SKILL.md", "フロントマター無し")
    write(kit, "a-skill/run.py", "print(1)\n")
    write(kit, "a-skill/lib/util.py", "x = 1\n")
    write(kit, "a-skill/__pycache__/run.cpython.pyc", b"\0")
    write(kit, "a-skill/.bin/cache/tool.exe", b"\0")  # 隠しフォルダは一覧に出さない
    write(kit, "not-a-skill/README.md", "SKILL.md が無い")
    skills = ctx.load_skills([kit], None, root)
    assert [s.name for s in skills] == ["a-skill", "beta"]
    a, b = skills
    assert a.description == ""
    assert a.body == "フロントマター無し"
    # プロジェクトの外なので絶対パス (/ 区切り)
    assert a.dir == (kit / "a-skill").resolve().as_posix()
    assert a.skill_file == a.dir + "/SKILL.md"
    assert a.files == ["lib/util.py", "run.py"]
    assert (b.description, b.body, b.files) == ("B の説明", "B 本文", [])


def test_load_skills_inside_root_uses_relative_path(root: Path):
    write(root, "tools/skills/s/SKILL.md", skill_md("s"))
    (skill,) = ctx.load_skills([root / "tools" / "skills"], None, root)
    assert skill.dir == "tools/skills/s"


def test_load_skills_first_dir_wins_on_same_name(root: Path, tmp_path: Path):
    first, second = tmp_path / "first", tmp_path / "second"
    write(first, "x/SKILL.md", skill_md("same", body="first"))
    write(second, "y/SKILL.md", skill_md("same", body="second"))
    write(second, "z/SKILL.md", skill_md("other"))
    skills = ctx.load_skills([first, second], None, root)
    assert [(s.name, s.body) for s in skills] == [("same", "first"), ("other", "")]


def test_load_skills_substitutes_skill_dir(root: Path, kit: Path):
    write(
        kit, "s/SKILL.md", skill_md("s", body="python ${SKILL_DIR}/a.py ${SKILL_DIR}/b")
    )
    (skill,) = ctx.load_skills([kit], None, root)
    d = (kit / "s").resolve().as_posix()
    assert skill.body == f"python {d}/a.py {d}/b"


def test_load_skills_substitutes_skills_dir(root: Path, kit: Path):
    """${SKILLS_DIR} はスキルを並べたフォルダ (ほかのスキルのスクリプトを指すのに使う)"""
    write(kit, "s/SKILL.md", skill_md("s", body="python ${SKILLS_DIR}/t/x.py"))
    (skill,) = ctx.load_skills([kit], None, root)
    assert skill.body == f"python {kit.resolve().as_posix()}/t/x.py"


def test_load_skills_select_in_given_order(root: Path, kit: Path):
    for n in ["a", "b", "c"]:
        write(kit, f"{n}/SKILL.md", skill_md(n))
    skills = ctx.load_skills([kit], ["c", "a"], root)
    assert [s.name for s in skills] == ["c", "a"]
    with pytest.raises(ValueError, match="zzz"):
        ctx.load_skills([kit], ["a", "zzz"], root)


def test_load_skills_missing_dir(root: Path, tmp_path: Path):
    assert ctx.load_skills([tmp_path / "nope"], None, root) == []


def test_default_skill_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    script = tmp_path / "kit" / "ctx.py"
    monkeypatch.delenv(ctx.SKILLS_ENV, raising=False)
    assert ctx.default_skill_dirs(script) == [tmp_path / "kit" / "skills"]
    monkeypatch.setenv(ctx.SKILLS_ENV, f"/a{ctx.os.pathsep}/b{ctx.os.pathsep}")
    assert ctx.default_skill_dirs(script) == [Path("/a"), Path("/b")]


def test_display_path(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    assert ctx.display_path(root / "a" / "b.py", root) == "a/b.py"
    assert (
        ctx.display_path(tmp_path / "kit", root)
        == (tmp_path / "kit").resolve().as_posix()
    )


# ---------------------------------------------------------------------------
# コンテキストへの挿入
# ---------------------------------------------------------------------------


@pytest.fixture
def skilled(root: Path, kit: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """プロジェクト (root) と、外にあるスキル (CTX_SKILLS_DIR で指定)"""
    write(root, "AGENTS.md", "冒頭プロンプト")
    write(
        kit,
        "check/SKILL.md",
        skill_md(
            "check",
            "テストを実行する",
            "python ${CTX} run -- python ${SKILL_DIR}/helper.py",
        ),
    )
    write(kit, "check/helper.py", "print('helper')\n")
    monkeypatch.setenv(ctx.SKILLS_ENV, str(kit))
    return root


def test_skills_section_in_context(
    skilled: Path, kit: Path, capsys: pytest.CaptureFixture[str]
):
    rc, out, err = run_ctx(capsys, str(skilled), "--no-git", "--stdout")
    assert rc == 0
    d = (kit / "check").resolve().as_posix()
    # 冒頭プロンプト → スキル → プロジェクトの順
    assert out.startswith("冒頭プロンプト\n")
    assert out.index("# スキル") < out.index("# プロジェクト: proj")
    assert "あなたはスクリプトやコマンドを直接実行できません" in out
    assert "## スキル: check\n" in out
    assert "- 説明: テストを実行する" in out
    assert f"- フォルダ: `{d}/`" in out
    assert f"- ファイル: `{d}/helper.py`" in out
    runner = Path(ctx.__file__).resolve().as_posix()
    assert f"python {runner} run -- python {d}/helper.py" in out
    # スキルはプロジェクトの外なので、ツリーやソースコード欄には出てこない
    assert "helper.py\n```" not in out.split("# プロジェクト")[1]
    assert "スキル 1" in err


def test_runner_path_is_absolute_when_ctx_is_outside(
    skilled: Path, capsys: pytest.CaptureFixture[str]
):
    _, out, _ = run_ctx(capsys, str(skilled), "--no-git", "--stdout")
    runner = Path(ctx.__file__).resolve().as_posix()
    assert f"`python {runner} run --`" in out


def test_root_defaults_to_current_dir(
    skilled: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.chdir(skilled / "src")
    rc, out, _ = run_ctx(capsys, "--no-git", "--stdout")
    assert rc == 0
    assert "# プロジェクト: src" in out
    assert "### main.py" in out


def test_no_skills_and_select(
    skilled: Path, kit: Path, capsys: pytest.CaptureFixture[str]
):
    write(kit, "other/SKILL.md", skill_md("other"))
    _, out, _ = run_ctx(capsys, str(skilled), "--no-git", "--stdout", "--no-skills")
    assert "# スキル" not in out
    _, out, _ = run_ctx(capsys, str(skilled), "--no-git", "--stdout", "-s", "other")
    assert "## スキル: other" in out
    assert "## スキル: check" not in out


def test_unknown_skill_is_error(skilled: Path, capsys: pytest.CaptureFixture[str]):
    rc, _, err = run_ctx(capsys, str(skilled), "--no-git", "--stdout", "-s", "nope")
    assert rc == 1
    assert "スキルが見つかりません: nope" in err
    assert "check" in err


def test_skills_dir_option_overrides_env(
    skilled: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    other = tmp_path / "other-skills"
    write(other, "x/SKILL.md", skill_md("x"))
    _, out, _ = run_ctx(
        capsys, str(skilled), "--no-git", "--stdout", "--skills-dir", str(other)
    )
    assert "## スキル: x" in out
    assert "## スキル: check" not in out


def test_list_shows_skills(
    skilled: Path, kit: Path, capsys: pytest.CaptureFixture[str]
):
    rc, out, err = run_ctx(capsys, str(skilled), "--no-git", "--list")
    assert rc == 0
    d = (kit / "check").resolve().as_posix()
    assert f"skill  check  ({d}/SKILL.md)" in out
    assert "スキル 1" in err


def test_skill_file_inside_project_is_not_duplicated(
    root: Path, capsys: pytest.CaptureFixture[str]
):
    """スキル置き場をプロジェクト内に指定した場合、SKILL.md は本文に重複させない"""
    write(root, "tools/skills/s/SKILL.md", skill_md("s"))
    write(root, "tools/skills/s/run.py", "print(1)\n")
    _, out, _ = run_ctx(
        capsys,
        str(root),
        "--no-git",
        "--stdout",
        "--skills-dir",
        str(root / "tools/skills"),
    )
    assert "## スキル: s" in out
    assert "### tools/skills/s/SKILL.md" not in out
    assert "### tools/skills/s/run.py" in out


def test_runner_path_when_ctx_is_in_project(root: Path, kit: Path):
    """ctx.py をプロジェクトにコピーして使う場合、実行例はその置き場所を指す"""
    write(kit, "s/SKILL.md", skill_md("s"))
    tools = root / "tools"
    tools.mkdir()
    shutil.copy(ctx.__file__, tools / "ctx.py")
    r = subprocess.run(
        [sys.executable, str(tools / "ctx.py"), "--no-git", "--stdout"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=root,
        env=dict(ctx.os.environ, **{ctx.SKILLS_ENV: str(kit)}),
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
