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


def test_sample_project_excludes(capsys: pytest.CaptureFixture[str]) -> None:
    """例で説明している除外が実際に効いていること"""
    ctx.main([str(SAMPLE_PROJECT), "--no-git", "--list"])
    out = capsys.readouterr().out
    for excluded in [
        "CONTEXT_PROMPT.md",
        ".ctxignore",
        ".env.example",
        "assets/logo.png",
        "docs/internal/meeting-notes.md",
    ]:
        assert excluded not in out
    assert (SAMPLE_PROJECT / "assets" / "logo.png").is_file()
    assert (SAMPLE_PROJECT / "docs" / "internal" / "meeting-notes.md").is_file()
