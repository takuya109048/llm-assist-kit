"""examples/sample-context.md が ctx.py の実際の出力と一致することを確認する

ctx.py の出力形式を意図して変えたときは、次のコマンドで例を作り直す:
    CTX_UPDATE_EXAMPLE=1 pytest tests/test_example.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import ctx

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
SAMPLE_PROJECT = EXAMPLES / "sample-project"
SAMPLE_CONTEXT = EXAMPLES / "sample-context.md"


def test_sample_context_is_up_to_date(capsys: pytest.CaptureFixture[str]) -> None:
    rc = ctx.main([str(SAMPLE_PROJECT), "--no-git", "--stdout"])
    assert rc == 0
    actual = capsys.readouterr().out
    if os.environ.get("CTX_UPDATE_EXAMPLE"):
        SAMPLE_CONTEXT.write_text(actual, encoding="utf-8", newline="\n")
    # Windows の autocrlf で CRLF になっていても比較できるよう改行をそろえる
    expected = SAMPLE_CONTEXT.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert actual == expected, (
        "examples/sample-context.md が古くなっています。"
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
    ("CONTEXT_PROMPT.md", False, "冒頭プロンプトとして使用"),
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
