"""apply-patch スキル (skills/apply-patch/apply.py と同梱の apply_patch) のテスト"""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

SKILL = Path(__file__).resolve().parent.parent / "skills" / "apply-patch"


def load_apply() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "apply_patch_skill", SKILL / "apply.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


apply = load_apply()


def has_binary() -> bool:
    exe = "apply_patch.exe" if sys.platform == "win32" else "apply_patch"
    with zipfile.ZipFile(apply.ZIP_PATH) as zf:
        return f"{apply.platform_key()}/{exe}" in zf.namelist()


needs_binary = pytest.mark.skipif(
    not has_binary(), reason="この OS 用の apply_patch が zip に入っていない"
)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    monkeypatch.chdir(root)
    return root


def run_apply(
    capsys: pytest.CaptureFixture[str], patch_text: str, *args: str
) -> tuple[int, str]:
    """パッチをファイル経由で渡して apply.main を呼ぶ"""
    Path("patch.txt").write_text(patch_text, encoding="utf-8")
    try:
        capsys.readouterr()
        code = apply.main(["-f", "patch.txt", *args])
        return code, capsys.readouterr().out
    finally:
        Path("patch.txt").unlink()


# ---------------------------------------------------------------------------
# パッチの取り出し
# ---------------------------------------------------------------------------

PATCH = """*** Begin Patch
*** Add File: a.txt
+hello
*** End Patch
"""


def test_extract_from_llm_message():
    message = (
        "次のように修正します。\r\n\r\n```text\r\n"
        + PATCH.replace("\n", "\r\n")
        + "```\r\n\r\n適用してください。"
    )
    assert apply.extract_patches(message) == [PATCH]


def test_extract_multiple_and_none():
    second = PATCH.replace("a.txt", "b.txt")
    assert apply.extract_patches(PATCH + "\n間の文章\n" + second) == [PATCH, second]
    assert apply.extract_patches("パッチなし") == []


def test_extract_unclosed_is_error():
    with pytest.raises(ValueError, match="End Patch"):
        apply.extract_patches("*** Begin Patch\n*** Add File: a\n+x\n")


def test_extract_restarts_on_new_begin():
    text = "*** Begin Patch\n*** Add File: broken\n" + PATCH
    assert apply.extract_patches(text) == [PATCH]


def test_extract_strips_only_control_lines():
    text = (
        "  *** Begin Patch\n"
        "  *** Update File: a.md  \n"
        "@@\n"
        " *** 本文の区切り線 ***\n"
        "-  old\n"
        "+  new\n"
        "  *** End of File\n"
        "  *** End Patch  \n"
    )
    (patch,) = apply.extract_patches(text)
    assert patch == (
        "*** Begin Patch\n"
        "*** Update File: a.md\n"
        "@@\n"
        " *** 本文の区切り線 ***\n"
        "-  old\n"
        "+  new\n"
        "*** End of File\n"
        "*** End Patch\n"
    )


def test_summarize():
    patch = (
        "*** Begin Patch\n*** Add File: n.py\n+x\n*** Update File: a.py\n"
        "*** Move to: b.py\n@@\n-x\n+y\n*** Delete File: old.py\n*** End Patch\n"
    )
    assert apply.summarize(patch) == [
        ("Add File", "n.py"),
        ("Update File", "a.py"),
        ("Move to", "b.py"),
        ("Delete File", "old.py"),
    ]


@pytest.mark.parametrize(
    ("path", "unsafe"),
    [
        ("src/a.py", False),
        ("./a.py", False),
        ("a/../b.py", False),
        ("../a.py", True),
        ("a/../../b.py", True),
        ("/etc/passwd", True),
        ("C:\\Windows\\x.txt", True),
        ("C:x.txt", True),
        ("\\\\server\\share\\x", True),
        ("a\\..\\..\\b", True),
    ],
)
def test_unsafe_path(path: str, unsafe: bool):
    assert apply.unsafe_path(path) is unsafe


# ---------------------------------------------------------------------------
# main (apply_patch を実行しない部分)
# ---------------------------------------------------------------------------


def test_dry_run(project: Path, capsys: pytest.CaptureFixture[str]):
    patch = (
        "*** Begin Patch\n*** Add File: n.py\n+x\n*** Update File: a.py\n"
        "*** Move to: b.py\n@@\n-x\n+y\n*** Delete File: old.py\n*** End Patch\n"
    )
    code, out = run_apply(capsys, patch, "--dry-run")
    assert code == 0
    assert "  追加: n.py\n  更新: a.py\n    → 移動先: b.py\n  削除: old.py\n" in out
    assert "--dry-run のため適用していません" in out
    assert not (project / "n.py").exists()


def test_rejects_paths_outside_project(
    project: Path, capsys: pytest.CaptureFixture[str]
):
    code, out = run_apply(capsys, PATCH.replace("a.txt", "../evil.txt"))
    assert code == 1
    assert "プロジェクトの外を指すパス" in out
    assert "../evil.txt" in out
    assert not (project.parent / "evil.txt").exists()


def test_no_patch(project: Path, capsys: pytest.CaptureFixture[str]):
    code, out = run_apply(capsys, "ただの文章")
    assert code == 1
    assert "パッチが見つかりません" in out


def test_reads_clipboard_by_default(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(apply, "read_clipboard", lambda: "回答\n" + PATCH)
    assert apply.main(["--dry-run"]) == 0
    assert "追加: a.txt" in capsys.readouterr().out


def test_reads_stdin(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(sys, "stdin", io.StringIO(PATCH))
    assert apply.main(["-f", "-", "--dry-run"]) == 0
    assert "追加: a.txt" in capsys.readouterr().out


def test_missing_platform_binary(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(apply, "platform_key", lambda: "plan9-mips")
    code, out = run_apply(capsys, PATCH)
    assert code == 1
    assert "この OS (plan9-mips) 用の apply_patch は zip に入っていません" in out
    assert not (project / "a.txt").exists()


def test_backup_restore(project: Path):
    (project / "keep.txt").write_text("before", encoding="utf-8")
    backup = apply.Backup(["keep.txt", "new.txt", "keep.txt"])
    (project / "keep.txt").write_text("after", encoding="utf-8")
    (project / "new.txt").write_text("created", encoding="utf-8")
    assert sorted(backup.restore()) == ["keep.txt", "new.txt"]
    assert (project / "keep.txt").read_text(encoding="utf-8") == "before"
    assert not (project / "new.txt").exists()
    assert backup.restore() == []  # 変化が無ければ何もしない


def test_zip_contents():
    with zipfile.ZipFile(apply.ZIP_PATH) as zf:
        names = set(zf.namelist())
        info = zf.read("BUILD_INFO.txt").decode("utf-8")
    assert {"LICENSE", "NOTICE", "BUILD_INFO.txt"} <= names
    assert {"linux-x86_64/apply_patch", "windows-x86_64/apply_patch.exe"} <= names
    assert "commit: " in info
    assert "github.com/openai/codex" in info


# ---------------------------------------------------------------------------
# 実際に apply_patch で適用する
# ---------------------------------------------------------------------------


@needs_binary
def test_add_update_move_delete(project: Path, capsys: pytest.CaptureFixture[str]):
    (project / "src").mkdir()
    (project / "src" / "app.py").write_text(
        "def greet():\n    print('Hi')\n\n\ndef main():\n    greet()\n",
        encoding="utf-8",
    )
    (project / "old.txt").write_text("old\n", encoding="utf-8")
    patch = """以下を適用してください。
```
*** Begin Patch
*** Add File: docs/日本語.md
+# 見出し
+
+本文
*** Update File: src/app.py
*** Move to: src/main.py
@@ def greet():
-    print('Hi')
+    print('こんにちは')
*** Delete File: old.txt
*** End Patch
```
"""
    code, out = run_apply(capsys, patch)
    assert code == 0, out
    assert "Success. Updated the following files:" in out
    assert (project / "docs" / "日本語.md").read_text(encoding="utf-8") == (
        "# 見出し\n\n本文\n"
    )
    assert not (project / "src" / "app.py").exists()
    assert (project / "src" / "main.py").read_text(encoding="utf-8") == (
        "def greet():\n    print('こんにちは')\n\n\ndef main():\n    greet()\n"
    )
    assert not (project / "old.txt").exists()


@needs_binary
def test_failure_rolls_back_everything(
    project: Path, capsys: pytest.CaptureFixture[str]
):
    (project / "a.txt").write_text("one\n", encoding="utf-8")
    (project / "b.txt").write_text("keep\n", encoding="utf-8")
    first = "*** Begin Patch\n*** Add File: first.txt\n+1\n*** End Patch\n"
    # 2 つ目のパッチ: a.txt の削除と new.txt の追加の後、存在しない行の更新で失敗する
    second = (
        "*** Begin Patch\n"
        "*** Delete File: a.txt\n"
        "*** Add File: new.txt\n+new\n"
        "*** Update File: b.txt\n@@\n-no such line\n+x\n"
        "*** End Patch\n"
    )
    code, out = run_apply(capsys, first + second)
    assert code != 0
    assert "すべての変更を元に戻しました" in out
    assert (project / "a.txt").read_text(encoding="utf-8") == "one\n"
    assert (project / "b.txt").read_text(encoding="utf-8") == "keep\n"
    assert not (project / "new.txt").exists()
    assert not (project / "first.txt").exists()


@needs_binary
def test_through_ctx_run(project: Path):
    """実際の使い方: ctx.py run 経由で実行し、結果を LLM に貼る形にする"""
    (project / "patch.txt").write_text(PATCH, encoding="utf-8")
    ctx_py = SKILL.parent.parent / "ctx.py"
    r = subprocess.run(
        [
            sys.executable,
            str(ctx_py),
            "run",
            "--stdout",
            "--",
            sys.executable,
            str(SKILL / "apply.py"),
            "-f",
            "patch.txt",
        ],
        capture_output=True,
        cwd=project,
    )
    # Windows では標準出力の改行が \r\n になるのでそろえる
    out = r.stdout.decode("utf-8").replace("\r\n", "\n")
    assert r.returncode == 0, out + r.stderr.decode("utf-8", errors="replace")
    assert "- 終了コード: 0 (成功)" in out
    assert "追加: a.txt" in out
    assert "Success. Updated the following files:\nA a.txt" in out
    assert (project / "a.txt").read_text(encoding="utf-8") == "hello\n"
