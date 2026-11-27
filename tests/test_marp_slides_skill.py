"""marp-slides スキル (skills/marp-slides/build.py とテーマ) のテスト

Marp CLI 自体は起動せず、コマンドの組み立て、marp.zip からの取り出し、
画像のコピーを確認する。
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

SKILL = Path(__file__).resolve().parent.parent / "skills" / "marp-slides"


def load_build() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "marp_slides_build", SKILL / "build.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = load_build()


@pytest.fixture
def slides(tmp_path: Path) -> Path:
    p = tmp_path / "deck" / "slides.md"
    p.parent.mkdir()
    p.write_text("---\nmarp: true\ntheme: kit-slides\n---\n\n# t\n", encoding="utf-8")
    return p


def test_theme_is_registered_as_kit_slides():
    css = (SKILL / "theme.css").read_text(encoding="utf-8")
    assert "/* @theme kit-slides */" in css
    # 表紙・ページ数 / 総ページ数・フッターのロゴ
    assert "section.cover" in css
    assert "data-marpit-pagination-total" in css
    assert "footer img" in css


LAYOUT_CLASSES = ["cols", "image-right", "image-left", "table", "image", "center"]


def test_skill_md_uses_the_theme_and_default_assets():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "theme: kit-slides" in text
    assert "<!-- _class: cover -->" in text
    for name in build.ASSET_FILES:
        assert f"assets/{name}" in text
        assert (SKILL / "assets" / name).is_file()


def test_example_uses_every_layout():
    """見本 (example.md) は表紙と全レイアウトを使い、画像はスキルの assets/ にある"""
    text = (SKILL / "example.md").read_text(encoding="utf-8")
    assert text.startswith("---\nmarp: true\ntheme: kit-slides\n")
    for name in ["cover", *LAYOUT_CLASSES]:
        assert f"<!-- _class: {name} -->" in text, name
    for ref in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text):
        assert (SKILL / ref).is_file(), ref
    assert (SKILL.parent.parent / "examples" / "marp-slides-example.pptx").is_file()


@pytest.mark.parametrize("name", LAYOUT_CLASSES)
def test_layout_classes_are_in_theme_and_skill(name: str):
    """本文のレイアウト (2 カラム・左右の画像) はテーマにあり、SKILL.md で説明している"""
    css = (SKILL / "theme.css").read_text(encoding="utf-8")
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert f"section.{name}" in css
    assert f"<!-- _class: {name} -->" in text or f"`{name}`" in text


def test_copies_missing_assets_only(slides: Path):
    assets = slides.parent / "assets"
    assets.mkdir()
    (assets / "logo.png").write_text("mine", encoding="utf-8")

    copied = build.copy_default_assets(slides.parent)

    assert copied == [assets / "background.png"]
    assert (assets / "logo.png").read_text(encoding="utf-8") == "mine"
    assert (assets / "background.png").read_bytes() == (
        SKILL / "assets" / "background.png"
    ).read_bytes()
    assert build.copy_default_assets(slides.parent) == []


def test_default_background_and_logo_are_png():
    """表紙の背景とロゴの既定は PNG。仮の画像 (placeholder.svg) は残す"""
    assert build.ASSET_FILES == ["background.png", "logo.png"]
    for name in build.ASSET_FILES:
        assert (SKILL / "assets" / name).read_bytes().startswith(b"\x89PNG")
    assert not (SKILL / "assets" / "background.svg").exists()
    assert not (SKILL / "assets" / "logo.svg").exists()
    assert (SKILL / "assets" / build.PLACEHOLDER).is_file()


def test_placeholder_is_copied_only_when_used(tmp_path: Path):
    """仮の画像は、スライドが使っているときだけコピーする (slideinit ではコピーしない)"""
    build.prepare_folder(tmp_path / "a", tmp_path)
    assert not (tmp_path / "a" / "assets" / "placeholder.svg").exists()
    build.prepare_folder(tmp_path / "a", tmp_path, "![](assets/placeholder.svg)")
    assert (tmp_path / "a" / "assets" / "placeholder.svg").is_file()


def fake_marp_zip(path: Path, key: str, data: bytes = b"fake marp") -> Path:
    exe = "marp.exe" if sys.platform == "win32" else "marp"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{key}/{exe}", data)
        zf.writestr("BUILD_INFO.txt", "test")
    return path


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """zip の場所と取り出し先を一時フォルダにする"""
    monkeypatch.setattr(build, "ZIP_PATH", tmp_path / "marp.zip")
    monkeypatch.setattr(build, "CACHE_DIR", tmp_path / ".bin")
    return tmp_path


def test_zip_binary_extracts_once(cache: Path):
    fake_marp_zip(build.ZIP_PATH, build.platform_key())

    first = build.zip_binary()

    assert first is not None
    assert first.read_bytes() == b"fake marp"
    assert first.is_relative_to(build.CACHE_DIR)
    first.write_bytes(b"cached")  # 2 回目は取り出し直さない
    assert build.zip_binary() == first
    assert first.read_bytes() == b"cached"


def test_zip_binary_uses_new_folder_when_zip_changes(cache: Path):
    fake_marp_zip(build.ZIP_PATH, build.platform_key(), b"v1")
    old = build.zip_binary()
    fake_marp_zip(build.ZIP_PATH, build.platform_key(), b"version 2")
    new = build.zip_binary()
    assert old and new and old != new
    assert new.read_bytes() == b"version 2"


def test_zip_binary_none_without_zip_or_platform(cache: Path):
    assert build.zip_binary() is None
    fake_marp_zip(build.ZIP_PATH, "other-os")
    assert build.zip_binary() is None


def test_marp_command_prefers_zip_then_marp_then_npx(
    cache: Path, monkeypatch: pytest.MonkeyPatch
):
    found: dict[str, str | None] = {"marp": None, "npx": "/bin/npx"}
    monkeypatch.setattr(build.shutil, "which", lambda name: found[name])
    assert build.marp_command() == ["/bin/npx", "--yes", "@marp-team/marp-cli"]

    found["marp"] = "/bin/marp"
    assert build.marp_command() == ["/bin/marp"]

    fake_marp_zip(build.ZIP_PATH, build.platform_key())
    [binary] = build.marp_command()
    assert Path(binary).is_relative_to(build.CACHE_DIR)

    build.ZIP_PATH.unlink()
    found["marp"] = found["npx"] = None
    with pytest.raises(FileNotFoundError):
        build.marp_command()


def test_bundled_zip_has_windows_marp():
    """同梱の marp.zip には Windows 用の単体版が入っている"""
    with zipfile.ZipFile(SKILL / "marp.zip") as zf:
        names = zf.namelist()
        assert "windows-x86_64/marp.exe" in names
        assert {"LICENSE", "BUILD_INFO.txt"} <= set(names)


@pytest.mark.parametrize(
    ("argv", "fmt"),
    [
        ([], "pdf"),
        (["--html"], "html"),
        (["--pptx"], "pptx"),
        (["--pptx-editable"], "pptx"),  # 以前の名前
        (["-o", "out.pptx"], "pptx"),
        (["-o", "out.txt"], "pdf"),
    ],
)
def test_format(argv: list[str], fmt: str):
    assert build.parse_args(["s.md", *argv]).format == fmt


def test_main_runs_marp_with_theme(
    slides: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    slides = slides.resolve()  # build.py は絶対パスにしてから渡す
    calls: list[list[str]] = []
    monkeypatch.setattr(build, "marp_command", lambda: ["marp"])
    monkeypatch.setattr(
        build.subprocess,
        "run",
        lambda cmd: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0),
    )

    assert build.main([str(slides), "--html"]) == 0

    out = slides.with_suffix(".html")
    assert calls == [
        [
            "marp",
            str(slides),
            "--theme-set",
            str(build.THEME),
            "--allow-local-files",
            "--html",
            "-o",
            str(out),
        ]
    ]
    assert (slides.parent / "assets" / "logo.png").is_file()
    assert f"作成しました: {out}" in capsys.readouterr().out


def test_main_shrinks_overflowing_slides_through_a_temporary_file(
    slides: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """入りきらない本文があれば、文字を小さくする CSS を足した一時ファイルを Marp に渡し、
    終わったら消す"""
    slides = slides.resolve()
    slides.write_text(
        "---\nmarp: true\n---\n\n## たくさん\n\n"
        + "".join(f"- {n}\n" for n in range(1, 41)),
        encoding="utf-8",
    )
    seen: list[str] = []

    def run(cmd: list[str]) -> subprocess.CompletedProcess:
        source = Path(cmd[1])
        assert source.parent == slides.parent and source != slides
        seen.append(source.read_text(encoding="utf-8"))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(build, "marp_command", lambda: ["marp"])
    monkeypatch.setattr(build.subprocess, "run", run)

    assert build.main([str(slides)]) == 0
    [text] = seen
    assert "<style scoped>" in text and "zoom: 0.5;" in text
    assert sorted(p.name for p in slides.parent.glob("*.md")) == [slides.name]
    assert "警告: スライド 1: 本文が多すぎて" in capsys.readouterr().err


def test_formats_are_exclusive():
    with pytest.raises(SystemExit):
        build.parse_args(["s.md", "--pdf", "--pptx"])


@pytest.mark.parametrize("option", ["--pptx", "--pptx-editable"])
def test_pptx_is_editable_and_made_without_marp(
    option: str,
    slides: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """PPTX は文字を編集できるもので、Marp CLI もブラウザも使わず Python だけで作る"""
    monkeypatch.setattr(build, "marp_command", lambda: pytest.fail("Marp CLI を呼んだ"))
    monkeypatch.setattr(
        build.subprocess, "run", lambda cmd: pytest.fail("外部コマンドを呼んだ")
    )

    assert build.main([str(slides), option]) == 0

    out = slides.resolve().with_suffix(".pptx")
    with zipfile.ZipFile(out) as zf:
        assert "ppt/slides/slide1.xml" in zf.namelist()
        assert "<a:t>t</a:t>" in zf.read("ppt/slides/slide1.xml").decode("utf-8")
    assert f"作成しました: {out}" in capsys.readouterr().out


def test_theme_fonts_are_segoe_ui_then_meiryo():
    """半角英数は Segoe UI、全角 (日本語) はメイリオ。編集できる PPTX も同じフォント"""
    css = (SKILL / "theme.css").read_text(encoding="utf-8")
    assert '--kit-font: "Segoe UI", "Meiryo"' in css
    pptx = build.load_editable_pptx()
    assert (pptx.LATIN_FONT, pptx.EA_FONT) == ("Segoe UI", "Meiryo")


def test_cols_overflow_stays_in_two_columns():
    """cols の本文が入りきらなくても、3 つ目のカラムに分かれて右がスライドの外に出ないよう、
    高さを内容に合わせて伸ばす。フッターなどはスライドの上端からの位置に置く
    (VS Code のプレビューでは文字が小さくならないので、はみ出す部分が見えるように)"""
    css = (SKILL / "theme.css").read_text(encoding="utf-8")
    rule = re.search(r"section\.cols \{\s*height: auto;\s*min-height: 720px;\s*\}", css)
    assert rule
    assert re.search(
        r"section\.cols::after,\s*section\.cols > footer \{\s*bottom: auto;\s*"
        r"top: calc\(720px - var\(--kit-footer-h\)\);",
        css,
    )
    assert "section.cols::before {" in css


def test_no_libreoffice_theme():
    """LibreOffice を使う古い方式のテーマは無い"""
    assert not (SKILL / "theme-editable.css").exists()
    assert "LibreOffice" not in (SKILL / "SKILL.md").read_text(encoding="utf-8")


def test_main_reports_missing_file(tmp_path: Path):
    assert build.main([str(tmp_path / "none.md")]) == 1


# ---- VS Code (Marp for VS Code) のプレビュー ----


def read_settings(root: Path) -> dict:
    return json.loads((root / ".vscode" / "settings.json").read_text(encoding="utf-8"))


def test_vscode_preview_copies_theme_and_registers_it(tmp_path: Path):
    """テーマをスライドの assets/ にコピーし、ワークスペースの設定に登録する"""
    workspace = tmp_path / "ws"
    slides = workspace / "slides" / "発表.md"
    slides.parent.mkdir(parents=True)
    slides.write_text("# t\n", encoding="utf-8")

    messages = build.setup_vscode_preview(slides.parent, workspace)

    theme = slides.parent / "assets" / "kit-slides.css"
    assert theme.read_bytes() == build.THEME.read_bytes()
    assert (
        read_settings(workspace)
        == {
            "markdown.marp.themes": ["./slides/assets/kit-slides.css"],
            "markdown.marp.enableHtml": True,  # 文字の色分け (<span>) をプレビューでも表示する
        }
    )
    assert len(messages) == 2
    # 2 回目は何もしない
    assert build.setup_vscode_preview(slides.parent, workspace) == []


def test_vscode_settings_keep_other_values(tmp_path: Path):
    settings = tmp_path / ".vscode" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(
        '{"editor.wordWrap": "on", "markdown.marp.themes": ["./other.css"]}',
        encoding="utf-8",
    )
    slides = tmp_path / "a" / "b" / "s.md"
    slides.parent.mkdir(parents=True)
    # 今のフォルダがワークスペースの外でも、.vscode のあるフォルダを使う
    build.register_vscode_theme(slides.parent, tmp_path / "a" / "b")
    assert read_settings(tmp_path) == {
        "editor.wordWrap": "on",
        "markdown.marp.themes": ["./other.css", "./a/b/assets/kit-slides.css"],
        "markdown.marp.enableHtml": True,
    }


def test_vscode_settings_with_comments_are_not_changed(tmp_path: Path):
    settings = tmp_path / ".vscode" / "settings.json"
    settings.parent.mkdir()
    text = '{\n  // コメント\n  "editor.wordWrap": "on"\n}\n'
    settings.write_text(text, encoding="utf-8")
    message = build.register_vscode_theme(tmp_path, tmp_path)
    assert message and "./assets/kit-slides.css" in message
    assert settings.read_text(encoding="utf-8") == text


def test_workspace_root(tmp_path: Path):
    slides = tmp_path / "ws" / "slides" / "s.md"
    slides.parent.mkdir(parents=True)
    # .vscode が無ければ、スライドが今のフォルダの中ならそこ、外ならスライドのフォルダ
    assert build.workspace_root(slides.parent, tmp_path / "ws") == tmp_path / "ws"
    assert build.workspace_root(slides.parent, tmp_path / "other") == slides.parent
    (tmp_path / ".vscode").mkdir()
    assert build.workspace_root(slides.parent, tmp_path / "ws") == tmp_path


def test_vscode_preview_is_skipped_inside_the_kit():
    assert build.setup_vscode_preview(SKILL, SKILL.parent.parent) == []


def test_missing_images_are_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    """見つからない画像は、書き出す前に知らせる (以前の SVG の名前なら PNG への書き換えを案内)"""
    slides = tmp_path / "s.md"
    slides.write_text(
        '---\nfooter: "![logo](assets/logo.svg)"\n---\n\n![bg](assets/background.png)\n'
        "\n![](https://example.com/a.png) ![](none.png)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(build, "build_pptx", lambda slides, output: 0)

    assert build.main([str(slides), "--pptx"]) == 0

    err = capsys.readouterr().err
    assert (
        "assets/logo.svg → スライドの assets/logo.svg を assets/logo.png に書き換えて"
        in err
    )
    assert "none.png" in err
    assert "background.png" not in err  # 既定の画像はコピーされるのであるもの
    assert "example.com" not in err


def test_example_flow_svg_follows_the_skill_rules():
    """見本の SVG の図は、SKILL.md の決まり (大きさ・使える要素) に沿っている"""
    from xml.etree import ElementTree

    path = SKILL / "assets" / "example-flow.svg"
    root = ElementTree.parse(path).getroot()
    assert (root.get("width"), root.get("height")) == ("1100", "440")
    assert root.get("viewBox") == "0 0 1100 440"
    allowed = {"rect", "line", "polyline", "polygon", "circle", "path", "text"}
    allowed |= {"defs", "marker"}  # 矢じり (PowerPoint では線の矢印になる)
    tags = {el.tag.split("}")[-1] for el in root.iter()} - {"svg"}
    assert tags <= allowed, tags - allowed
    text = path.read_text(encoding="utf-8")
    for banned in ("<style", "class=", "<foreignObject", "<filter", "<image"):
        assert banned not in text
    assert 'marker-end="url(#arrow)"' in text
    # 見本のスライドで使っていて、build.py の既定の画像 (slideinit でコピー) ではない
    assert "assets/example-flow.svg" in (SKILL / "example.md").read_text("utf-8")
    assert "example-flow.svg" not in build.ASSET_FILES


def test_skill_says_when_to_draw_svg_figures():
    """図は、ユーザーが求めたときと、LLM が必要と判断したときに、確認せずに作る"""
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    section = text[text.index("### 図を SVG で作る") :]
    assert "ユーザーが図を求めたとき" in section
    assert "図のほうが伝わるとあなたが判断したとき" in section
    assert "確認せず" in section
    # 仮の画像は、作れない画像 (写真・スクリーンショット) のときだけ
    assert "写真や画面のスクリーンショットなど" in text


def test_html_is_enabled_for_existing_settings(tmp_path: Path):
    """テーマは登録済みでも、HTML (色分けの <span>) が無効なら有効にする"""
    settings = tmp_path / ".vscode" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(
        '{"markdown.marp.themes": ["./assets/kit-slides.css"]}', encoding="utf-8"
    )
    assert build.register_vscode_theme(tmp_path, tmp_path)
    assert read_settings(tmp_path)["markdown.marp.enableHtml"] is True
    assert build.register_vscode_theme(tmp_path, tmp_path) is None  # 2 回目は何もしない


def test_pdf_command_enables_html():
    """Markdown の中の HTML (<span class="red"> など) を使えるように --html を付ける"""
    command = build.build_command(Path("s.md"), "pdf", Path("s.pdf"))
    assert "--html" in command and "--pdf" in command
    assert command.count("--html") == 1
    html = build.build_command(Path("s.md"), "html", Path("s.html"))
    assert html.count("--html") == 1 and "--pdf" not in html


def test_theme_has_span_colors():
    css = (SKILL / "theme.css").read_text(encoding="utf-8")
    for name in ("red", "blue", "green", "orange", "gray"):
        assert f"section .{name} {{\n  color: var(--kit-{name});" in css
    # *強調* は Markdown の標準のまま (色を付けない)
    assert "section em" not in css
