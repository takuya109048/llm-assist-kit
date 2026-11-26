"""commands/slides.py (PowerShell の関数 slideinit / slidepdf / slidepptx) のテスト"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest
import slides as slides_command  # commands/slides.py

import install

KIT = Path(__file__).resolve().parent.parent
SCRIPT = KIT / "commands" / "slides.py"
EXAMPLE = KIT / "skills" / "marp-slides" / "example.md"


def run(cwd: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        env=dict(os.environ, PYTHONIOENCODING="cp1252"),  # 英語版 Windows のパイプ相当
    )
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", errors="replace")


@pytest.mark.parametrize(
    ("name", "args"),
    [("slideinit", ("init",)), ("slidepdf", ("pdf",)), ("slidepptx", ("pptx",))],
)
def test_registered_in_install(name: str, args: tuple[str, ...]):
    f = next(f for f in install.FUNCTIONS if f.name == name)
    assert (f.script, f.args) == ("commands/slides.py", args)
    block = install.render_block([f], "python", Path("C:/kit"))
    assert (
        f"function {name} {{ & 'python' '{Path('C:/kit') / f.script}' '{args[0]}' @args }}"
        in block
    )


def test_slideinit_prepares_the_folder(tmp_path: Path):
    code, out = run(tmp_path)
    assert code == 2 and "使い方" in out

    code, out = run(tmp_path, "init")
    assert code == 0, out
    assets = tmp_path / "slides" / "assets"
    names = sorted(p.name for p in assets.iterdir())
    assert names == ["background.svg", "kit-slides.css", "logo.svg", "placeholder.svg"]
    settings = json.loads((tmp_path / ".vscode" / "settings.json").read_text("utf-8"))
    assert settings == {"markdown.marp.themes": ["./slides/assets/kit-slides.css"]}

    # 2 回目は何も変えない (差し替えた画像も残る)
    (assets / "logo.svg").write_text("mine", encoding="utf-8")
    code, out = run(tmp_path, "init")
    assert code == 0, out
    assert "コピーしました" not in out
    assert (assets / "logo.svg").read_text(encoding="utf-8") == "mine"


def test_slideinit_with_folder(tmp_path: Path):
    code, out = run(tmp_path, "init", "資料")
    assert code == 0, out
    assert (tmp_path / "資料" / "assets" / "kit-slides.css").is_file()


def test_slidepptx_exports_every_slide_in_the_folder(tmp_path: Path):
    folder = tmp_path / "slides"
    folder.mkdir()
    for name in ("a.md", "b.md"):
        (folder / name).write_text(
            EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8"
        )
    code, out = run(tmp_path, "pptx")
    assert code == 0, out
    for name in ("a.pptx", "b.pptx"):
        with zipfile.ZipFile(folder / name) as zf:
            assert "ppt/slides/slide11.xml" in zf.namelist()


def test_export_reports_missing_files(tmp_path: Path):
    code, out = run(tmp_path, "pdf")
    assert code == 1
    assert "見つかりません" in out
    code, out = run(tmp_path, "pptx", "none.md")
    assert code == 1
    assert "none.md" in out


def test_slidepdf_calls_build_with_pdf(tmp_path: Path):
    calls: list[list[str]] = []
    fake = ModuleType("fake_build")
    setattr(fake, "main", lambda argv: calls.append(argv) or 0)
    deck = tmp_path / "deck.md"
    deck.write_text("# t\n", encoding="utf-8")
    assert slides_command.export("pdf", [str(deck)], fake) == 0
    assert calls == [[str(deck), "--pdf"]]


def test_skill_tells_to_run_slideinit_with_the_first_patch():
    text = (KIT / "skills" / "marp-slides" / "SKILL.md").read_text(encoding="utf-8")
    first = text.index("$OutputEncoding = [System.Text.UTF8Encoding]")
    assert text[first:].splitlines()[1] == "slideinit"
    assert "slidepdf" in text and "slidepptx" in text
    apply_patch = (KIT / "skills" / "apply-patch" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "slideinit" in apply_patch
    assert (KIT / "skills" / "apply-patch" / "apply.py").is_file()
