"""ctx.py のテスト (pytest)"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import ctx

HAS_GIT = shutil.which("git") is not None


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


class Project:
    """一時ディレクトリ上のテスト用プロジェクト"""

    def __init__(self, root: Path, capsys: pytest.CaptureFixture[str]) -> None:
        self.root = root
        self._capsys = capsys

    def write(self, rel: str, content: str | bytes) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content, encoding="utf-8")
        return p

    def run(self, *argv: str, root: Path | None = None) -> tuple[int, str, str]:
        self._capsys.readouterr()
        rc = ctx.main([str(root or self.root), *argv])
        out, err = self._capsys.readouterr()
        return rc, out, err

    def listed(self, *argv: str) -> list[str]:
        """--list の結果から対象ファイル名だけを取り出す"""
        rc, out, _ = self.run("--list", *argv)
        assert rc == 0
        return [
            line.split("tok", 1)[1].strip()
            for line in out.splitlines()
            if " tok " in line
        ]

    def stdout(self, *argv: str) -> str:
        rc, out, _ = self.run("--stdout", *argv)
        assert rc == 0
        return out


@pytest.fixture
def project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Project:
    root = tmp_path / "proj"
    root.mkdir()
    return Project(root, capsys)


@pytest.fixture(params=["walk", "git"])
def mode(request: pytest.FixtureRequest, project: Project) -> list[str]:
    """ファイル収集を git なし (--no-git) / git あり の両方で試す。追加引数を返す"""
    if request.param == "walk":
        return ["--no-git"]
    if not HAS_GIT:
        pytest.skip("git が無い")
    subprocess.run(["git", "init", "-q", str(project.root)], check=True)
    return []


# ---------------------------------------------------------------------------
# IgnoreRules
# ---------------------------------------------------------------------------


def rules(*lines: str, base: str = "") -> ctx.IgnoreRules:
    r = ctx.IgnoreRules()
    r.add_lines(list(lines), base)
    return r


def test_ignore_basename_pattern_matches_any_depth():
    r = rules("*.log")
    assert r.ignored("a.log", False)
    assert r.ignored("x/y/a.log", False)
    assert not r.ignored("a.txt", False)


def test_ignore_comments_and_blank_lines():
    assert not rules("# *.py", "", "   ").ignored("a.py", False)


def test_ignore_negation():
    r = rules("*.log", "!keep.log")
    assert r.ignored("a.log", False)
    assert not r.ignored("keep.log", False)


def test_ignore_dir_only():
    r = rules("build/")
    assert r.ignored("build", True)
    assert not r.ignored("build", False)


def test_ignore_anchored():
    r = rules("/root.txt", "docs/*.md")
    assert r.ignored("root.txt", False)
    assert not r.ignored("sub/root.txt", False)
    assert r.ignored("docs/a.md", False)
    assert not r.ignored("x/docs/a.md", False)


def test_ignore_double_star():
    r = rules("a/**/b.txt")
    assert r.ignored("a/b.txt", False)
    assert r.ignored("a/x/y/b.txt", False)


def test_ignore_base_dir():
    r = rules("*.tmp", base="sub")
    assert r.ignored("sub/a.tmp", False)
    assert not r.ignored("a.tmp", False)


def test_ignore_escaped_hash():
    assert rules("\\#notes").ignored("#notes", False)


def test_ignore_escaped_bang():
    assert rules("\\!important").ignored("!important", False)


@pytest.mark.parametrize(
    ("pattern", "rel", "expected"),
    [
        # * と ? は / をまたがない (git と同じ)
        ("config/*.toml", "config/a.toml", True),
        ("config/*.toml", "config/sub/a.toml", False),
        ("a/?.txt", "a/b.txt", True),
        ("a/?.txt", "a/bc.txt", False),
        ("a/?.txt", "a/b/c.txt", False),
        # ** は 0 個以上のディレクトリ
        ("**/x.py", "x.py", True),
        ("**/x.py", "a/b/x.py", True),
        ("a/**/b.txt", "a/b.txt", True),
        ("a/**/b.txt", "a/x/y/b.txt", True),
        ("a/**/b.txt", "z/a/b.txt", False),
        ("logs/**", "logs/a/b.txt", True),
        ("logs/**", "logsx/a.txt", False),
        # 文字クラス
        ("s[0-9].py", "s1.py", True),
        ("s[0-9].py", "s10.py", False),
        ("s[0-9].py", "sa.py", False),
        ("[!a]bc", "zbc", True),
        ("[!a]bc", "abc", False),
        ("[^a]bc", "abc", False),
        ("x[", "x[", True),  # 閉じない [ は文字として扱う
        # 正規表現の特殊文字はそのまま文字として扱う
        ("a+b(1).txt", "a+b(1).txt", True),
        ("a.txt", "abtxt", False),
        # 途中の \ は次の 1 文字を文字として扱う
        ("a\\*b", "a*b", True),
        ("a\\*b", "axb", False),
    ],
)
def test_ignore_glob(pattern: str, rel: str, expected: bool):
    assert rules(pattern).ignored(rel, False) is expected


def test_ignore_cannot_reinclude_inside_excluded_dir(project: Project):
    """除外したディレクトリの中は ! で含め直せない (git と同じ)"""
    project.write(".ctxignore", "secret/\n!secret/ok.txt\n")
    project.write("a.py", "x")
    project.write("secret/ok.txt", "x")
    assert project.listed("--no-git") == ["a.py"]


# ---------------------------------------------------------------------------
# matches_any
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rel", "pattern", "expected"),
    [
        ("src/a/b.py", "src/**", True),
        ("src/a/b.py", "src/", True),
        ("src/a/b.py", "*.py", True),
        ("src/b.py", "./src/b.py", True),
        ("src/b.py", "src\\b.py", True),  # Windows 区切り
        ("a/b/c.py", "a/**/c.py", True),
        ("a/c.py", "a/**/c.py", True),
        ("lib/b.py", "src/**", False),
        ("srcx/b.py", "src/**", False),
        (".env", ".env", True),  # 先頭のドットを削らない
        ("cfg/.env.local", ".env.*", True),
        ("env", ".env", False),
    ],
)
def test_matches_any(rel: str, pattern: str, expected: bool):
    assert ctx.matches_any(rel, [pattern]) is expected


# ---------------------------------------------------------------------------
# 整形用の関数
# ---------------------------------------------------------------------------


def test_fence_for():
    assert ctx.fence_for("plain") == "```"
    assert ctx.fence_for("a ``` b") == "````"
    assert ctx.fence_for("`````") == "``````"


@pytest.mark.parametrize(
    ("rel", "lang"),
    [
        ("a/b.py", "python"),
        ("X.TS", "typescript"),
        ("Dockerfile.dev", "dockerfile"),
        ("Makefile", "makefile"),
        ("LICENSE", ""),
    ],
)
def test_lang_of(rel: str, lang: str):
    assert ctx.lang_of(rel) == lang


def test_build_tree():
    tree = ctx.build_tree("proj", ["b.txt", "src/z.py", "src/sub/a.py", "a.txt"])
    assert tree == "\n".join(
        [
            "proj/",
            "├── src/",
            "│   ├── sub/",
            "│   │   └── a.py",
            "│   └── z.py",
            "├── a.txt",
            "└── b.txt",
        ]
    )


def test_estimate_tokens():
    assert ctx.estimate_tokens("") == 0
    assert ctx.estimate_tokens("abcdefgh") == 2
    assert ctx.estimate_tokens("日本語") == 3


# ---------------------------------------------------------------------------
# 文字コード・バイナリ判定
# ---------------------------------------------------------------------------


def test_read_text_utf8_bom_and_newlines(tmp_path: Path):
    p = tmp_path / "f"
    p.write_bytes(b"\xef\xbb\xbfa\r\nb\rc\n")
    assert ctx.read_text(p) == "a\nb\nc\n"


@pytest.mark.parametrize("encoding", ["utf-8", "cp932"])
def test_read_text_japanese(tmp_path: Path, encoding: str):
    p = tmp_path / "f"
    p.write_bytes("こんにちは".encode(encoding))
    assert ctx.read_text(p) == "こんにちは"
    assert not ctx.is_binary(p)


def test_utf8_cut_at_chunk_boundary_is_text(tmp_path: Path):
    # 8192 バイト目でマルチバイト文字が切れても text と判定する
    p = tmp_path / "f"
    p.write_bytes(b"a" * 8191 + "あ".encode("utf-8"))
    assert not ctx.is_binary(p)


@pytest.mark.parametrize(
    ("data", "binary"),
    [
        (b"abc\x00def", True),
        (bytes(range(128, 256)) * 4, True),
        (b"", False),
    ],
)
def test_is_binary(tmp_path: Path, data: bytes, binary: bool):
    p = tmp_path / "f"
    p.write_bytes(data)
    assert ctx.is_binary(p) is binary


# ---------------------------------------------------------------------------
# ファイル収集 (git あり / なし両方)
# ---------------------------------------------------------------------------


def test_default_excludes(project: Project, mode: list[str]):
    project.write("src/main.py", "print(1)\n")
    project.write("node_modules/pkg/index.js", "x")
    project.write(".venv/lib/a.py", "x")
    project.write("dist/out.js", "x")
    project.write("package-lock.json", "{}")
    project.write(".env", "SECRET=1")
    project.write(".env.local", "SECRET=1")
    project.write("key.pem", "x")
    project.write("logo.png", b"\x89PNG\r\n\x1a\n\x00\x00")
    project.write("app.min.js", "x")
    assert project.listed(*mode) == ["src/main.py"]


def test_gitignore(project: Project, mode: list[str]):
    project.write(".gitignore", "*.log\ntmp/\n")
    project.write("a.py", "x")
    project.write("debug.log", "x")
    project.write("tmp/x.py", "x")
    project.write("sub/.gitignore", "local.txt\n")
    project.write("sub/local.txt", "x")
    project.write("sub/keep.txt", "x")
    assert project.listed(*mode) == [
        ".gitignore",
        "a.py",
        "sub/.gitignore",
        "sub/keep.txt",
    ]


def test_ctxignore(project: Project, mode: list[str]):
    project.write(".ctxignore", "docs/\n*.snap\n")
    project.write("a.py", "x")
    project.write("docs/guide.md", "x")
    project.write("t/a.snap", "x")
    assert project.listed(*mode) == ["a.py"]


def test_include_exclude(project: Project, mode: list[str]):
    project.write("src/a.py", "x")
    project.write("src/b.ts", "x")
    project.write("tests/t.py", "x")
    project.write("README.md", "x")
    assert project.listed(*mode, "-i", "src/**") == ["src/a.py", "src/b.ts"]
    assert project.listed(*mode, "-i", "*.py") == ["src/a.py", "tests/t.py"]
    assert project.listed(*mode, "-x", "tests/**", "-x", "*.md") == [
        "src/a.py",
        "src/b.ts",
    ]


def test_include_overrides_default_file_exclude(project: Project, mode: list[str]):
    project.write("a.py", "x")
    project.write("package-lock.json", "{}")
    assert project.listed(*mode, "-i", "package-lock.json") == ["package-lock.json"]


def test_binary_and_size_are_reported(project: Project, mode: list[str]):
    project.write("a.py", "x")
    project.write("blob.dat", b"\x00\x01\x02")
    project.write("big.txt", "x" * 3000)
    rc, out, _ = project.run("--list", "--max-size", "1", *mode)
    assert rc == 0
    assert "skip  blob.dat  (バイナリ)" in out
    assert "skip  big.txt  (サイズ超過" in out
    assert " tok  big.txt" not in out


def test_excludes_self_and_prompt_file(project: Project, mode: list[str]):
    shutil.copy(ctx.__file__, project.root / "ctx.py")
    project.write("CONTEXT_PROMPT.md", "MY PROMPT")
    project.write("a.py", "x")
    r = subprocess.run(
        [sys.executable, str(project.root / "ctx.py"), "--list", *mode],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=project.root,
    )
    assert r.returncode == 0, r.stderr
    assert "a.py" in r.stdout
    assert "ctx.py" not in r.stdout
    assert "CONTEXT_PROMPT.md" not in r.stdout


@pytest.mark.skipif(not HAS_GIT, reason="git が無い")
def test_git_deleted_tracked_file_is_skipped(project: Project):
    subprocess.run(["git", "init", "-q", str(project.root)], check=True)
    project.write("a.py", "x")
    project.write("gone.py", "x")
    subprocess.run(["git", "-C", str(project.root), "add", "."], check=True)
    (project.root / "gone.py").unlink()
    assert project.listed() == ["a.py"]


@pytest.mark.skipif(not HAS_GIT, reason="git が無い")
def test_git_subdirectory_root_inside_repo(project: Project):
    subprocess.run(["git", "init", "-q", str(project.root)], check=True)
    project.write("a.py", "x")
    project.write("pkg/b.py", "x")
    rc, out, _ = project.run("--list", root=project.root / "pkg")
    assert rc == 0
    assert " tok  b.py" in out
    assert "a.py" not in out


# ---------------------------------------------------------------------------
# 出力内容
# ---------------------------------------------------------------------------


def test_full_output_structure(project: Project):
    project.write("src/a.py", "print('hi')\n")
    project.write("README.md", "# T\n```py\nx\n```\n")
    text = project.stdout("--no-git")
    assert text.startswith(ctx.DEFAULT_PROMPT.rstrip())
    assert "# プロジェクト: proj" in text
    assert "├── src/\n│   └── a.py\n└── README.md" in text
    assert "## ソースコード (2 ファイル)" in text
    assert "### src/a.py\n\n```python\nprint('hi')\n```" in text
    # ``` を含む Markdown は 4 連フェンス
    assert "### README.md\n\n````markdown\n# T\n```py\nx\n```\n````" in text
    # ツリーの後にファイル本文が続く順序
    assert text.index("## ディレクトリツリー") < text.index("## ソースコード")


def test_prompt_file_priority(project: Project):
    project.write("a.py", "x")
    project.write(".ctxprompt.md", "SECOND")
    assert project.stdout("--no-git").startswith("SECOND")
    project.write("CONTEXT_PROMPT.md", "FIRST")
    assert project.stdout("--no-git").startswith("FIRST")


def test_prompt_option_and_no_prompt(project: Project):
    project.write("a.py", "x")
    project.write("prompts/review.md", "REVIEW PROMPT")
    text = project.stdout("--no-git", "-p", "prompts/review.md")
    assert text.startswith("REVIEW PROMPT")
    assert "### prompts/review.md" not in text
    text = project.stdout("--no-git", "--no-prompt")
    assert text.startswith("# プロジェクト: proj")


def test_no_tree(project: Project):
    project.write("a.py", "x")
    text = project.stdout("--no-git", "--no-tree")
    assert "## ディレクトリツリー" not in text
    assert "## ソースコード" in text


def test_line_numbers(project: Project):
    project.write("a.py", "\n".join(f"l{i}" for i in range(1, 11)) + "\n")
    text = project.stdout("--no-git", "-n")
    assert " 1| l1\n" in text
    assert "10| l10\n" in text


def test_output_file(project: Project):
    project.write("a.py", "日本語\n")
    out = project.root / "out" / "ctx.md"
    out.parent.mkdir()
    rc, _, err = project.run("--no-git", "-o", str(out))
    assert rc == 0
    assert "に出力しました" in err
    text = out.read_text(encoding="utf-8")
    assert "日本語" in text
    assert "### out/ctx.md" not in text
    # 2 回目の実行でも出力ファイル自身は取り込まない
    project.run("--no-git", "-o", str(out))
    assert "### out/ctx.md" not in out.read_text(encoding="utf-8")


def test_errors(project: Project):
    rc, _, err = project.run("--stdout", root=project.root / "nope")
    assert rc == 1
    assert "ディレクトリではありません" in err
    rc, _, err = project.run("--stdout", "--no-git")
    assert rc == 1
    assert "対象ファイルがありません" in err


# ---------------------------------------------------------------------------
# クリップボード
# ---------------------------------------------------------------------------


def copy_with(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    available: set[str],
    wayland: bool = False,
) -> tuple[str, list[tuple[list[str], bytes]]]:
    """外部コマンドを差し替えて copy_to_clipboard を呼び、渡した内容を返す"""
    calls: list[tuple[list[str], bytes]] = []

    def fake_run(cmd: list[str], input: bytes, check: bool = False):
        calls.append((cmd, input))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(shutil, "which", lambda n: n if n in available else None)
    monkeypatch.setattr(subprocess, "run", fake_run)
    if wayland:
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    else:
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    how = ctx.copy_to_clipboard("あ\nb")
    return how, calls


def test_clipboard_macos(monkeypatch: pytest.MonkeyPatch):
    how, calls = copy_with(monkeypatch, "darwin", {"pbcopy"})
    assert how == "pbcopy"
    assert calls == [(["pbcopy"], "あ\nb".encode())]


def test_clipboard_wayland_preferred(monkeypatch: pytest.MonkeyPatch):
    how, _ = copy_with(monkeypatch, "linux", {"wl-copy", "xclip"}, wayland=True)
    assert how == "wl-copy"


def test_clipboard_xclip(monkeypatch: pytest.MonkeyPatch):
    _, calls = copy_with(monkeypatch, "linux", {"xclip", "xsel"})
    assert calls[0][0] == ["xclip", "-selection", "clipboard"]


def test_clipboard_wsl_clip_exe_utf16(monkeypatch: pytest.MonkeyPatch):
    how, calls = copy_with(monkeypatch, "linux", {"clip.exe"})
    assert how == "clip.exe"
    assert calls[0][1] == b"\xff\xfe" + "あ\r\nb".encode("utf-16-le")


def test_clipboard_none_available(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(OSError):
        copy_with(monkeypatch, "linux", set())


def test_main_reports_clipboard_failure(
    project: Project, monkeypatch: pytest.MonkeyPatch
):
    project.write("a.py", "x")

    def fail(text: str) -> str:
        raise OSError("no clipboard")

    monkeypatch.setattr(ctx, "copy_to_clipboard", fail)
    rc, _, err = project.run("--no-git")
    assert rc == 1
    assert "--stdout" in err


def test_main_copies_full_context(project: Project, monkeypatch: pytest.MonkeyPatch):
    project.write("a.py", "x")
    copied: list[str] = []

    def fake_copy(text: str) -> str:
        copied.append(text)
        return "fake"

    monkeypatch.setattr(ctx, "copy_to_clipboard", fake_copy)
    rc, out, err = project.run("--no-git")
    assert rc == 0
    assert out == ""
    assert "クリップボードにコピーしました (fake)" in err
    assert "### a.py" in copied[0]


def read_windows_clipboard() -> str:
    import ctypes
    from ctypes import wintypes

    user32, kernel32 = ctx.win32_dlls()
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    if not user32.OpenClipboard(None):
        raise OSError("OpenClipboard failed")
    try:
        h = user32.GetClipboardData(13)  # CF_UNICODETEXT
        ptr = kernel32.GlobalLock(h)
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 専用")
def test_windows_clipboard_roundtrip_japanese():
    """実際の Windows クリップボードに書き込み、読み戻して確認する"""
    text = "日本語テスト ✓ emoji 🎉\nline2\n" + "x" * 100_000
    assert ctx.copy_to_clipboard(text) == "Win32 API"
    assert read_windows_clipboard() == text.replace("\n", "\r\n")


@pytest.mark.skipif(sys.platform == "win32", reason="Windows 以外で確認する")
def test_non_windows_rejects_win32_path():
    with pytest.raises(OSError):
        ctx._copy_windows("x")
