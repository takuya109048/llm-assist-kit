"""ctx.py のテスト (標準ライブラリ unittest。pytest でも実行可)

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ctx  # noqa: E402

HAS_GIT = shutil.which("git") is not None


def run_main(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = ctx.main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class ProjectCase(unittest.TestCase):
    """一時ディレクトリにテスト用プロジェクトを作るベースクラス"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "proj"
        self.root.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, rel: str, content: str | bytes) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content, encoding="utf-8")
        return p

    def listed(self, *extra: str) -> list[str]:
        """--list の結果から対象ファイル名だけを取り出す"""
        rc, out, _ = run_main(str(self.root), "--list", *extra)
        self.assertEqual(rc, 0)
        return [line.split("tok", 1)[1].strip() for line in out.splitlines() if " tok " in line]

    def stdout_text(self, *extra: str) -> str:
        rc, out, _ = run_main(str(self.root), "--stdout", *extra)
        self.assertEqual(rc, 0)
        return out


# ---------------------------------------------------------------------------
# 純粋関数
# ---------------------------------------------------------------------------

class TestIgnoreRules(unittest.TestCase):
    def rules(self, *lines: str, base: str = "") -> ctx.IgnoreRules:
        r = ctx.IgnoreRules()
        r.add_lines(list(lines), base)
        return r

    def test_basename_pattern_matches_any_depth(self):
        r = self.rules("*.log")
        self.assertTrue(r.ignored("a.log", False))
        self.assertTrue(r.ignored("x/y/a.log", False))
        self.assertFalse(r.ignored("a.txt", False))

    def test_comments_and_blank_lines(self):
        r = self.rules("# *.py", "", "   ")
        self.assertFalse(r.ignored("a.py", False))

    def test_negation(self):
        r = self.rules("*.log", "!keep.log")
        self.assertTrue(r.ignored("a.log", False))
        self.assertFalse(r.ignored("keep.log", False))

    def test_dir_only(self):
        r = self.rules("build/")
        self.assertTrue(r.ignored("build", True))
        self.assertFalse(r.ignored("build", False))

    def test_anchored(self):
        r = self.rules("/root.txt", "docs/*.md")
        self.assertTrue(r.ignored("root.txt", False))
        self.assertFalse(r.ignored("sub/root.txt", False))
        self.assertTrue(r.ignored("docs/a.md", False))
        self.assertFalse(r.ignored("x/docs/a.md", False))

    def test_double_star(self):
        r = self.rules("a/**/b.txt")
        self.assertTrue(r.ignored("a/b.txt", False))
        self.assertTrue(r.ignored("a/x/y/b.txt", False))

    def test_base_dir(self):
        r = self.rules("*.tmp", base="sub")
        self.assertTrue(r.ignored("sub/a.tmp", False))
        self.assertFalse(r.ignored("a.tmp", False))

    def test_escaped_hash(self):
        r = self.rules("\\#notes")
        self.assertTrue(r.ignored("#notes", False))


class TestMatchesAny(unittest.TestCase):
    def test_patterns(self):
        m = ctx.matches_any
        self.assertTrue(m("src/a/b.py", ["src/**"]))
        self.assertTrue(m("src/a/b.py", ["src/"]))
        self.assertTrue(m("src/a/b.py", ["*.py"]))
        self.assertTrue(m("src/b.py", ["./src/b.py"]))
        self.assertTrue(m("src/b.py", ["src\\b.py"]))  # Windows 区切り
        self.assertTrue(m("a/b/c.py", ["a/**/c.py"]))
        self.assertTrue(m("a/c.py", ["a/**/c.py"]))
        self.assertFalse(m("lib/b.py", ["src/**"]))
        self.assertFalse(m("srcx/b.py", ["src/**"]))

    def test_dotfile_pattern_not_stripped(self):
        self.assertTrue(ctx.matches_any(".env", [".env"]))
        self.assertTrue(ctx.matches_any("cfg/.env.local", [".env.*"]))
        self.assertFalse(ctx.matches_any("env", [".env"]))


class TestFormatting(unittest.TestCase):
    def test_fence_for(self):
        self.assertEqual(ctx.fence_for("plain"), "```")
        self.assertEqual(ctx.fence_for("a ``` b"), "````")
        self.assertEqual(ctx.fence_for("`````"), "``````")

    def test_lang_of(self):
        self.assertEqual(ctx.lang_of("a/b.py"), "python")
        self.assertEqual(ctx.lang_of("X.TS"), "typescript")
        self.assertEqual(ctx.lang_of("Dockerfile.dev"), "dockerfile")
        self.assertEqual(ctx.lang_of("Makefile"), "makefile")
        self.assertEqual(ctx.lang_of("LICENSE"), "")

    def test_build_tree(self):
        tree = ctx.build_tree("proj", ["b.txt", "src/z.py", "src/sub/a.py", "a.txt"])
        self.assertEqual(tree, "\n".join([
            "proj/",
            "├── src/",
            "│   ├── sub/",
            "│   │   └── a.py",
            "│   └── z.py",
            "├── a.txt",
            "└── b.txt",
        ]))

    def test_estimate_tokens(self):
        self.assertEqual(ctx.estimate_tokens(""), 0)
        self.assertEqual(ctx.estimate_tokens("abcdefgh"), 2)
        self.assertEqual(ctx.estimate_tokens("日本語"), 3)


class TestReadText(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def file(self, data: bytes) -> Path:
        p = self.dir / "f"
        p.write_bytes(data)
        return p

    def test_utf8_bom_and_newlines(self):
        p = self.file(b"\xef\xbb\xbfa\r\nb\rc\n")
        self.assertEqual(ctx.read_text(p), "a\nb\nc\n")

    def test_cp932(self):
        p = self.file("こんにちは".encode("cp932"))
        self.assertEqual(ctx.read_text(p), "こんにちは")
        self.assertFalse(ctx.is_binary(p))

    def test_utf8_japanese(self):
        p = self.file("日本語".encode("utf-8"))
        self.assertEqual(ctx.read_text(p), "日本語")
        self.assertFalse(ctx.is_binary(p))

    def test_utf8_cut_at_chunk_boundary(self):
        # 8192 バイト目でマルチバイト文字が切れても text と判定する
        p = self.file(b"a" * 8191 + "あ".encode("utf-8"))
        self.assertFalse(ctx.is_binary(p))

    def test_binary(self):
        self.assertTrue(ctx.is_binary(self.file(b"abc\x00def")))
        self.assertTrue(ctx.is_binary(self.file(bytes(range(128, 256)) * 4)))

    def test_empty_is_text(self):
        self.assertFalse(ctx.is_binary(self.file(b"")))


# ---------------------------------------------------------------------------
# ファイル収集 (git あり / なし両方)
# ---------------------------------------------------------------------------

class CollectMixin:
    use_git = False

    def setUp(self):
        super().setUp()
        if self.use_git:
            if not HAS_GIT:
                self.skipTest("git が無い")
            subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def ls(self, *extra: str) -> list[str]:
        return self.listed(*extra) if self.use_git else self.listed("--no-git", *extra)

    def test_default_excludes(self):
        self.write("src/main.py", "print(1)\n")
        self.write("node_modules/pkg/index.js", "x")
        self.write(".venv/lib/a.py", "x")
        self.write("dist/out.js", "x")
        self.write("package-lock.json", "{}")
        self.write(".env", "SECRET=1")
        self.write(".env.local", "SECRET=1")
        self.write("key.pem", "x")
        self.write("logo.png", b"\x89PNG\r\n\x1a\n\x00\x00")
        self.write("app.min.js", "x")
        self.assertEqual(self.ls(), ["src/main.py"])

    def test_gitignore(self):
        self.write(".gitignore", "*.log\ntmp/\n")
        self.write("a.py", "x")
        self.write("debug.log", "x")
        self.write("tmp/x.py", "x")
        self.write("sub/.gitignore", "local.txt\n")
        self.write("sub/local.txt", "x")
        self.write("sub/keep.txt", "x")
        self.assertEqual(self.ls(), [".gitignore", "a.py", "sub/.gitignore", "sub/keep.txt"])

    def test_ctxignore(self):
        self.write(".ctxignore", "docs/\n*.snap\n")
        self.write("a.py", "x")
        self.write("docs/guide.md", "x")
        self.write("t/a.snap", "x")
        self.assertEqual(self.ls(), ["a.py"])

    def test_include_exclude(self):
        self.write("src/a.py", "x")
        self.write("src/b.ts", "x")
        self.write("tests/t.py", "x")
        self.write("README.md", "x")
        self.assertEqual(self.ls("-i", "src/**"), ["src/a.py", "src/b.ts"])
        self.assertEqual(self.ls("-i", "*.py"), ["src/a.py", "tests/t.py"])
        self.assertEqual(self.ls("-x", "tests/**", "-x", "*.md"), ["src/a.py", "src/b.ts"])

    def test_include_overrides_default_file_exclude(self):
        self.write("a.py", "x")
        self.write("package-lock.json", "{}")
        self.assertEqual(self.ls("-i", "package-lock.json"), ["package-lock.json"])

    def test_binary_and_size_are_reported(self):
        self.write("a.py", "x")
        self.write("blob.dat", b"\x00\x01\x02")
        self.write("big.txt", "x" * 3000)
        rc, out, _ = run_main(str(self.root), "--list", "--max-size", "1",
                              *([] if self.use_git else ["--no-git"]))
        self.assertEqual(rc, 0)
        self.assertIn("skip  blob.dat  (バイナリ)", out)
        self.assertIn("skip  big.txt  (サイズ超過", out)
        self.assertNotIn(" tok  big.txt", out)

    def test_excludes_self_and_prompt_file(self):
        shutil.copy(ctx.__file__, self.root / "ctx.py")
        self.write("CONTEXT_PROMPT.md", "MY PROMPT")
        self.write("a.py", "x")
        args = [str(self.root / "ctx.py"), "--list"] + ([] if self.use_git else ["--no-git"])
        r = subprocess.run([sys.executable, *args], capture_output=True, text=True,
                           encoding="utf-8", cwd=self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("a.py", r.stdout)
        self.assertNotIn("ctx.py", r.stdout)
        self.assertNotIn("CONTEXT_PROMPT.md", r.stdout)


class TestCollectWalk(CollectMixin, ProjectCase):
    use_git = False


class TestCollectGit(CollectMixin, ProjectCase):
    use_git = True

    def test_deleted_tracked_file_is_skipped(self):
        self.write("a.py", "x")
        self.write("gone.py", "x")
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        (self.root / "gone.py").unlink()
        self.assertEqual(self.ls(), ["a.py"])

    def test_subdirectory_root_inside_repo(self):
        self.write("a.py", "x")
        self.write("pkg/b.py", "x")
        rc, out, _ = run_main(str(self.root / "pkg"), "--list")
        self.assertEqual(rc, 0)
        self.assertIn(" tok  b.py", out)
        self.assertNotIn("a.py", out)


# ---------------------------------------------------------------------------
# 出力内容
# ---------------------------------------------------------------------------

class TestOutput(ProjectCase):
    def test_full_output_structure(self):
        self.write("src/a.py", "print('hi')\n")
        self.write("README.md", "# T\n```py\nx\n```\n")
        text = self.stdout_text("--no-git")
        self.assertTrue(text.startswith(ctx.DEFAULT_PROMPT.rstrip()))
        self.assertIn("# プロジェクト: proj", text)
        self.assertIn("## ディレクトリツリー", text)
        self.assertIn("├── src/\n│   └── a.py\n└── README.md", text)
        self.assertIn("## ソースコード (2 ファイル)", text)
        self.assertIn("### src/a.py\n\n```python\nprint('hi')\n```", text)
        # ``` を含む Markdown は 4 連フェンス
        self.assertIn("### README.md\n\n````markdown\n# T\n```py\nx\n```\n````", text)
        # ツリーの後にファイル本文が続く順序
        self.assertLess(text.index("## ディレクトリツリー"), text.index("## ソースコード"))

    def test_prompt_file_priority(self):
        self.write("a.py", "x")
        self.write(".ctxprompt.md", "SECOND")
        self.assertTrue(self.stdout_text("--no-git").startswith("SECOND"))
        self.write("CONTEXT_PROMPT.md", "FIRST")
        self.assertTrue(self.stdout_text("--no-git").startswith("FIRST"))

    def test_prompt_option_and_no_prompt(self):
        self.write("a.py", "x")
        self.write("prompts/review.md", "REVIEW PROMPT")
        text = self.stdout_text("--no-git", "-p", "prompts/review.md")
        self.assertTrue(text.startswith("REVIEW PROMPT"))
        self.assertNotIn("### prompts/review.md", text)
        text = self.stdout_text("--no-git", "--no-prompt")
        self.assertTrue(text.startswith("# プロジェクト: proj"))

    def test_no_tree(self):
        self.write("a.py", "x")
        text = self.stdout_text("--no-git", "--no-tree")
        self.assertNotIn("## ディレクトリツリー", text)
        self.assertIn("## ソースコード", text)

    def test_line_numbers(self):
        self.write("a.py", "\n".join(f"l{i}" for i in range(1, 11)) + "\n")
        text = self.stdout_text("--no-git", "-n")
        self.assertIn(" 1| l1\n", text)
        self.assertIn("10| l10\n", text)

    def test_output_file(self):
        self.write("a.py", "日本語\n")
        out = self.root / "out" / "ctx.md"
        out.parent.mkdir()
        rc, _, err = run_main(str(self.root), "--no-git", "-o", str(out))
        self.assertEqual(rc, 0)
        self.assertIn("に出力しました", err)
        text = out.read_text(encoding="utf-8")
        self.assertIn("日本語", text)
        self.assertNotIn("### out/ctx.md", text)
        # 2 回目の実行でも出力ファイル自身は取り込まない
        run_main(str(self.root), "--no-git", "-o", str(out))
        self.assertNotIn("### out/ctx.md", out.read_text(encoding="utf-8"))

    def test_errors(self):
        rc, _, err = run_main(str(self.root / "nope"), "--stdout")
        self.assertEqual(rc, 1)
        self.assertIn("ディレクトリではありません", err)
        rc, _, err = run_main(str(self.root), "--stdout", "--no-git")
        self.assertEqual(rc, 1)
        self.assertIn("対象ファイルがありません", err)


# ---------------------------------------------------------------------------
# クリップボード
# ---------------------------------------------------------------------------

class TestClipboardDispatch(ProjectCase):
    """各 OS 用のコマンドに正しいバイト列を渡すか (外部コマンドはモック)"""

    def copy_with(self, platform: str, available: set[str], env: dict | None = None):
        calls = []

        def fake_run(cmd, input=None, check=False):
            calls.append((cmd, input))
            return subprocess.CompletedProcess(cmd, 0)

        with mock.patch.object(ctx.sys, "platform", platform), \
                mock.patch.object(ctx.shutil, "which", lambda n: n if n in available else None), \
                mock.patch.object(ctx.subprocess, "run", fake_run), \
                mock.patch.dict(os.environ, env or {}, clear=False):
            if env is None:
                os.environ.pop("WAYLAND_DISPLAY", None)
            how = ctx.copy_to_clipboard("あ\nb")
        return how, calls

    def test_macos(self):
        how, calls = self.copy_with("darwin", {"pbcopy"})
        self.assertEqual(how, "pbcopy")
        self.assertEqual(calls, [(["pbcopy"], "あ\nb".encode("utf-8"))])

    def test_wayland_preferred(self):
        how, _ = self.copy_with("linux", {"wl-copy", "xclip"}, {"WAYLAND_DISPLAY": "wayland-0"})
        self.assertEqual(how, "wl-copy")

    def test_xclip(self):
        how, calls = self.copy_with("linux", {"xclip", "xsel"})
        self.assertEqual(calls[0][0], ["xclip", "-selection", "clipboard"])

    def test_wsl_clip_exe_utf16(self):
        how, calls = self.copy_with("linux", {"clip.exe"})
        self.assertEqual(how, "clip.exe")
        self.assertEqual(calls[0][1], b"\xff\xfe" + "あ\r\nb".encode("utf-16-le"))

    def test_none_available(self):
        with self.assertRaises(OSError):
            self.copy_with("linux", set())

    def test_main_reports_failure(self):
        self.write("a.py", "x")
        with mock.patch.object(ctx, "copy_to_clipboard", side_effect=OSError("no clipboard")):
            rc, _, err = run_main(str(self.root), "--no-git")
        self.assertEqual(rc, 1)
        self.assertIn("--stdout", err)

    def test_main_copies_full_context(self):
        self.write("a.py", "x")
        with mock.patch.object(ctx, "copy_to_clipboard", return_value="fake") as m:
            rc, out, err = run_main(str(self.root), "--no-git")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")
        self.assertIn("クリップボードにコピーしました (fake)", err)
        self.assertIn("### a.py", m.call_args[0][0])


@unittest.skipUnless(sys.platform == "win32", "Windows 専用")
class TestWindowsClipboard(unittest.TestCase):
    """実際の Windows クリップボードに書き込み、読み戻して確認する"""

    @staticmethod
    def read_clipboard() -> str:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
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

    def test_roundtrip_japanese(self):
        text = "日本語テスト ✓ emoji 🎉\nline2\n" + "x" * 100_000
        self.assertEqual(ctx.copy_to_clipboard(text), "Win32 API")
        self.assertEqual(self.read_clipboard(), text.replace("\n", "\r\n"))


if __name__ == "__main__":
    unittest.main()
