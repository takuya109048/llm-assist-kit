"""examples/ の取得例が ctx.py の実際の出力と一致することを確認する

スキルはキットの skills/ を使う。キットの場所はマシンごとに違うので、
例では `C:/tools/llm-assist-kit` に置いたものとして表す (比較時に置き換える)。

ctx.py の出力形式を意図して変えたときは、次のコマンドで例を作り直す:
    CTX_UPDATE_EXAMPLE=1 pytest tests/test_example.py
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import ctx

KIT = Path(__file__).resolve().parent.parent
KIT_IN_EXAMPLE = "C:/tools/llm-assist-kit"
EXAMPLES = KIT / "examples"
SAMPLE_PROJECT = EXAMPLES / "sample-project"
SAMPLE_CONTEXT = EXAMPLES / "sample-context.md"
SAMPLE_RUN_RESULT = EXAMPLES / "sample-run-result.md"
EXAMPLES_README = EXAMPLES / "README.md"
# examples/README.md の「対象ファイルの確認」に載せている --list の出力
LIST_BLOCK = re.compile(r"(```text\nPS> ctx --list\n)(.*?)(```)", re.S)
# LLM の回答の例 (apply-patch スキルのパッチを適用する PowerShell コマンド入り)
SAMPLE_LLM_ANSWER = EXAMPLES / "sample-llm-answer.md"
# examples/README.md に載せている run の実行例 (上の回答のパッチを --dry-run で確認)
SAMPLE_RUN_COMMAND = [
    "python",
    f"{KIT.as_posix()}/skills/apply-patch/apply.py",
    "-f",
    "../sample-llm-answer.md",
    "--dry-run",
]


def normalize(text: str) -> str:
    """実際のキットの場所を、例で使う場所に置き換える"""
    return text.replace(KIT.as_posix(), KIT_IN_EXAMPLE)


@pytest.mark.kit_skills
def test_sample_context_is_up_to_date(capsys: pytest.CaptureFixture[str]) -> None:
    rc = ctx.main([str(SAMPLE_PROJECT), "--no-git", "--stdout"])
    assert rc == 0
    actual = normalize(capsys.readouterr().out)
    assert "## スキル: apply-patch" in actual
    if os.environ.get("CTX_UPDATE_EXAMPLE"):
        SAMPLE_CONTEXT.write_text(actual, encoding="utf-8", newline="\n")
    # Windows の autocrlf で CRLF になっていても比較できるよう改行をそろえる
    expected = SAMPLE_CONTEXT.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert actual == expected, (
        "examples/sample-context.md が古くなっています。"
        "CTX_UPDATE_EXAMPLE=1 pytest tests/test_example.py で更新してください"
    )


@pytest.mark.kit_skills
def test_examples_readme_list_is_up_to_date(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """examples/README.md の `ctx --list` の例が実際の出力と一致する"""
    # 推定トークン数はスキルのパスの長さで変わるので、キットが例の場所にあるものとして数える
    estimate = ctx.estimate_tokens
    monkeypatch.setattr(ctx, "estimate_tokens", lambda text: estimate(normalize(text)))
    rc = ctx.main([str(SAMPLE_PROJECT), "--no-git", "--list"])
    assert rc == 0
    captured = capsys.readouterr()
    actual = normalize(captured.out + captured.err)
    readme = EXAMPLES_README.read_text(encoding="utf-8").replace("\r\n", "\n")
    m = LIST_BLOCK.search(readme)
    assert m, "examples/README.md に --list の例がありません"
    if os.environ.get("CTX_UPDATE_EXAMPLE"):
        readme = readme[: m.start(2)] + actual + readme[m.end(2) :]
        EXAMPLES_README.write_text(readme, encoding="utf-8", newline="\n")
        m = LIST_BLOCK.search(readme)
        assert m
    assert actual == m.group(2), (
        "examples/README.md の --list の例が古くなっています。"
        "CTX_UPDATE_EXAMPLE=1 pytest tests/test_example.py で更新してください"
    )


@pytest.mark.skipif(shutil.which("python") is None, reason="python コマンドが無い")
def test_sample_run_result_is_up_to_date(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """examples/sample-run-result.md が `ctx.py run` の実際の出力と一致する"""
    monkeypatch.chdir(SAMPLE_PROJECT)
    rc = ctx.main(["run", "--stdout", "--", *SAMPLE_RUN_COMMAND])
    assert rc == 0
    actual = normalize(capsys.readouterr().out)
    if os.environ.get("CTX_UPDATE_EXAMPLE"):
        SAMPLE_RUN_RESULT.write_text(actual, encoding="utf-8", newline="\n")
    expected = SAMPLE_RUN_RESULT.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert actual == expected, (
        "examples/sample-run-result.md が古くなっています。"
        "CTX_UPDATE_EXAMPLE=1 pytest tests/test_example.py で更新してください"
    )


# (パス, 出力に入るか, 理由) — examples/sample-project/.ctxignore の各パターン
CTXIGNORE_CASES = [
    ("src/todo/cli.py.bak", False, "1. *.bak"),
    ("keep.bak", True, "2. !keep.bak で含め直す"),
    ("web/tmp/cache.js", False, "3. tmp/ (ディレクトリ)"),
    ("tests/fixtures/tmp", True, "3. tmp/ はファイルにはマッチしない"),
    ("TODO.md", False, "4. /TODO.md (ルート固定)"),
    ("docs/TODO.md", True, "4. ルート以外の TODO.md"),
    ("config/dev.local.toml", False, "5. config/*.local.toml"),
    ("config/stage/prod.local.toml", True, "5. * は / をまたがない"),
    ("docs/internal/meeting-notes.md", False, "6. docs/internal/"),
    (
        "docs/internal/public.md",
        False,
        "7. !docs/internal/public.md でも除外ディレクトリ内は戻せない",
    ),
    ("web/generated.js", False, "8. web/**/generated.js (** = 0 個のディレクトリ)"),
    ("web/lib/generated.js", False, "8. web/**/generated.js (** = 1 個以上)"),
    ("docs/draft1.md", False, "9. docs/draft?.md"),
    ("docs/draft10.md", True, "9. ? は 1 文字だけ"),
    ("src/todo/scratch1.py", False, "10. scratch[0-9].py"),
    ("src/todo/scratch_a.py", True, "10. a は [0-9] に含まれない"),
    ("#memo.txt", False, "11. \\#memo.txt"),
    # .ctxignore 以外の理由で除外されるもの
    ("AGENTS.md", False, "冒頭プロンプトとして使用"),
    (".ctxignore", False, "設定ファイル"),
    (".env.example", False, "既定の秘密情報パターン .env.*"),
    ("assets/logo.png", False, "既定の画像パターン *.png"),
]


@pytest.fixture(scope="module", params=["walk", "git"])
def sample_listing(request: pytest.FixtureRequest) -> set[str]:
    """sample-project の取得対象ファイル (git なし / あり)"""
    import contextlib
    import io

    argv = [str(SAMPLE_PROJECT), "--list"]
    if request.param == "walk":
        argv.append("--no-git")
    elif ctx.git_list_files(SAMPLE_PROJECT) is None:
        pytest.skip("git 管理下ではない")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        assert ctx.main(argv) == 0
    return {
        line.split("tok", 1)[1].strip()
        for line in buf.getvalue().splitlines()
        if " tok " in line
    }


@pytest.mark.parametrize(
    ("rel", "included", "reason"),
    CTXIGNORE_CASES,
    ids=[c[0] for c in CTXIGNORE_CASES],
)
def test_sample_project_patterns(
    sample_listing: set[str], rel: str, included: bool, reason: str
) -> None:
    """例の README で説明している含める/除外するが実際にそうなっていること"""
    assert (SAMPLE_PROJECT / rel).is_file(), f"例のファイルが無い: {rel}"
    assert (rel in sample_listing) is included, reason


def test_every_ctxignore_pattern_is_exercised() -> None:
    """.ctxignore の全パターンに、テストケースが少なくとも 1 つあること"""
    lines = (SAMPLE_PROJECT / ".ctxignore").read_text(encoding="utf-8").splitlines()
    patterns = [ln for ln in lines if ln.strip() and not ln.startswith("#")]
    reasons = " ".join(reason for _, _, reason in CTXIGNORE_CASES)
    for pattern in patterns:
        assert pattern in reasons, f"テストされていないパターン: {pattern}"


def test_sample_llm_answer_applies_and_tests_pass(tmp_path: Path) -> None:
    """例の回答のパッチが、擬似プロジェクトに実際に適用でき、そのテストも通る"""
    spec = importlib.util.spec_from_file_location(
        "apply_patch_skill", KIT / "skills" / "apply-patch" / "apply.py"
    )
    assert spec and spec.loader
    apply = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(apply)
    exe = "apply_patch.exe" if sys.platform == "win32" else "apply_patch"
    with zipfile.ZipFile(apply.ZIP_PATH) as zf:
        if f"{apply.platform_key()}/{exe}" not in zf.namelist():
            pytest.skip("この OS 用の apply_patch が zip に入っていない")
    project = tmp_path / "sample-project"
    shutil.copytree(SAMPLE_PROJECT, project)
    r = subprocess.run(
        [
            sys.executable,
            str(KIT / "skills" / "apply-patch" / "apply.py"),
            "-f",
            str(SAMPLE_LLM_ANSWER),
        ],
        capture_output=True,
        cwd=project,
    )
    out = r.stdout.decode("utf-8", errors="replace")
    assert r.returncode == 0, out
    assert "Success. Updated the following files:" in out
    assert "def remove(self, task_id: int) -> None:" in (
        project / "src" / "todo" / "storage.py"
    ).read_text(encoding="utf-8")

    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
        capture_output=True,
        cwd=project,
        env=dict(os.environ, PYTHONPATH=str(project / "src")),
    )
    assert tests.returncode == 0, tests.stdout.decode("utf-8", errors="replace")
    assert b"5 passed" in tests.stdout


def test_marp_slides_examples_are_up_to_date() -> None:
    """見本の PPTX が、今の元 (example.md・テーマ・画像など) から作られている"""
    spec = importlib.util.spec_from_file_location(
        "build_examples", KIT / "tools" / "build_examples.py"
    )
    assert spec and spec.loader
    build_examples = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_examples)
    assert build_examples.is_up_to_date(), (
        "examples/marp-slides-example.pptx が古くなっています。"
        "python tools/build_examples.py で作り直してください"
    )
