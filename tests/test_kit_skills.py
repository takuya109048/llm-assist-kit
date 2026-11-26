"""キットに同梱しているスキル (skills/) の SKILL.md のテスト

スクリプト (apply.py など) の動作は tests/test_apply_patch_skill.py で確認する。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import ctx

KIT_SKILLS = Path(__file__).resolve().parent.parent / "skills"
SKILL_DIRS = sorted(p for p in KIT_SKILLS.iterdir() if (p / "SKILL.md").is_file())
REMOVED_SKILLS = ["git-diff", "run-tests", "search"]


def apply_patch_body() -> str:
    _, body = ctx.parse_frontmatter(
        ctx.read_text(KIT_SKILLS / "apply-patch" / "SKILL.md")
    )
    return body


def test_kit_has_skills():
    assert [p.name for p in SKILL_DIRS] == ["apply-patch", "marp-slides"]
    for removed in REMOVED_SKILLS:
        assert not (KIT_SKILLS / removed).exists(), removed


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


def test_no_reference_to_removed_skills():
    """削除したスキル (git-diff / run-tests / search) を参照していない"""
    for skill_dir in SKILL_DIRS:
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        for removed in [*REMOVED_SKILLS, "search.py", "diff.py"]:
            assert removed not in text, (skill_dir.name, removed)


def test_apply_patch_assumes_previous_patch_applied():
    """結果が貼られないまま次の依頼が来ても、確認コマンドを出さずに続ける決まりがある

    (以前、適用できたか分からないとして確認用のコマンドを出してしまったことへの対策)
    """
    body = apply_patch_body()
    assert "前のパッチは成功して適用済みとみなします" in body
    assert "確認や、ファイルの現在の内容を\n   表示するコマンドを先に出さず" in body
    assert "すべて適用した後の内容" in body


def test_no_verification_command_after_patch():
    """パッチの後に、差分確認などのコマンドを続けて求めない

    (以前、パッチ適用後に差分確認のコマンドを毎回求めてしまったことへの対策)
    """
    assert "適用後の確認のためのコマンドを求めないでください" in apply_patch_body()


def test_failure_recovery_uses_ctx_to_show_the_file():
    """失敗したときだけ、そのファイルの現在の内容を ctx.py で貼ってもらう"""
    command = (
        'python ${CTX} -i "<失敗したファイルのパス>" --no-prompt --no-skills --no-tree'
    )
    assert command in apply_patch_body()


def test_preamble_lets_skills_override_waiting_for_results():
    """共通の説明の「結果を待つ」は実行結果の中身に限り、スキルの決まりを優先する"""
    assert "結果が貼られるまで、実行結果を推測で決めつけないでください。" not in (
        ctx.SKILLS_PREAMBLE
    )
    assert "各スキルに別の決まりがあれば、そちらに従ってください" in ctx.SKILLS_PREAMBLE
