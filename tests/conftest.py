from __future__ import annotations

from pathlib import Path

import pytest

import ctx


@pytest.fixture(autouse=True)
def no_kit_skills(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """既定では、キットの skills/ をテスト対象のコンテキストに混ぜない

    キットのスキルを使うテストには @pytest.mark.kit_skills を付ける
    """
    if request.node.get_closest_marker("kit_skills"):
        monkeypatch.delenv(ctx.SKILLS_ENV, raising=False)
        return
    empty = tmp_path / "_no_skills"
    empty.mkdir(exist_ok=True)
    monkeypatch.setenv(ctx.SKILLS_ENV, str(empty))
