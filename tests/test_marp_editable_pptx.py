"""marp-slides スキルの、編集できる PPTX (skills/marp-slides/editable_pptx.py) のテスト

位置の期待値は、見本 (example.md) を Marp (marp-core) で HTML にし、Chromium で描画して
測った要素の上端 (px、スライドは 1280x720)。PPTX の段落の上端がこれと一致することを確かめる。
"""

from __future__ import annotations

import importlib.util
import re
import sys
import zipfile
from pathlib import Path
from types import ModuleType
from xml.etree import ElementTree

import pytest

SKILL = Path(__file__).resolve().parent.parent / "skills" / "marp-slides"
EXAMPLE = SKILL / "example.md"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "editable_pptx", SKILL / "editable_pptx.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ep = load()


def slides_of(text: str) -> list:
    return ep.parse_markdown(text)


def pages_of(path: Path = EXAMPLE) -> list:
    slides = ep.parse_markdown(path.read_text(encoding="utf-8"))
    layout = ep.Layout(path.parent, [])
    return [layout.slide(s, n, len(slides)) for n, s in enumerate(slides, start=1)]


def para_tops(page) -> dict[str, tuple[float, float]]:
    """上寄せのテキストボックスの、各段落の (左端, 上端)。キーは段落の先頭 8 文字"""
    tops: dict[str, tuple[float, float]] = {}
    for shape in page.shapes:
        if isinstance(shape, ep.TextBox) and shape.anchor == "t":
            y = shape.y + shape.inset_t
            for p in shape.paras:
                y += p.space_before
                key = ep.plain_text(p.runs).replace("\n", "")[:8].rstrip()
                tops.setdefault(key, (shape.x + p.mar_l, y))
                lines = ep.count_lines(p.runs, p.size, shape.w - p.mar_l)
                y += lines * p.line + p.space_after
    return tops


def shapes_named(page, name: str) -> list:
    return [s for s in page.shapes if getattr(s, "name", "") == name]


# ---- Markdown を読む ----


def test_front_matter_and_directives():
    slides = slides_of(
        "---\nmarp: true\ntheme: kit-slides\npaginate: true\n"
        'footer: "![logo](assets/logo.svg)"\n---\n\n'
        "<!-- _class: cover -->\n\n# 表紙\n\n---\n\n<!-- class: cols -->\n\n## A\n\n"
        "---\n\n<!-- _paginate: false -->\n\n## B\n\n---\n\n## C\n"
    )
    assert [s.cls for s in slides] == ["cover", "cols", "cols", "cols"]
    assert [s.paginate for s in slides] == [True, True, False, True]
    assert slides[0].footer == "![logo](assets/logo.svg)"


def test_speaker_notes_comments_are_not_text():
    [slide] = slides_of("## A\n\n<!-- 発表者のメモ -->\n\n本文\n")
    assert [type(b).__name__ for b in slide.blocks] == ["Heading", "Paragraph"]


def test_background_images_are_taken_out_of_the_text():
    [slide] = slides_of("![bg](assets/background.svg)\n\n# タイトル\n")
    assert [(b.src, b.alt) for b in slide.backgrounds] == [
        ("assets/background.svg", "bg")
    ]
    assert [type(b).__name__ for b in slide.blocks] == ["Heading"]


def test_code_fence_with_dashes_is_not_a_slide_break():
    slides = slides_of("## A\n\n```\n---\n```\n\n---\n\n## B\n")
    assert len(slides) == 2
    assert slides[0].blocks[1].text == "---"


def test_nested_lists():
    [slide] = slides_of(
        "- 1\n  - 1-1\n    - 1-1-1\n  - 1-2\n- 2\n\n3. 三\n4. 四\n   1. 四の一\n"
    )
    ul, ol = slide.blocks
    assert not ul.ordered and len(ul.items) == 2
    child = ul.items[0].children[0]
    assert [ep.plain_text(i.runs) for i in child.items] == ["1-1", "1-2"]
    assert ep.plain_text(child.items[0].children[0].items[0].runs) == "1-1-1"
    assert ol.ordered and ol.start == 3
    assert ep.plain_text(ol.items[1].children[0].items[0].runs) == "四の一"


def test_table_with_alignment():
    [slide] = slides_of("| a | b | c |\n| :-- | :-: | --: |\n| 1 | 2 |\n")
    [table] = slide.blocks
    assert table.aligns == ["l", "ctr", "r"]
    assert [[ep.plain_text(c) for c in row] for row in table.rows] == [["1", "2", ""]]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("**太字** と *斜体*", [("太字", "b"), (" と ", ""), ("斜体", "i")]),
        (
            "`a*b*` と \\*星\\*",
            [("a*b*", "c"), (" と ", ""), ("*", ""), ("星", ""), ("*", "")],
        ),
        ("[リンク](https://example.com)", [("リンク", "l")]),
        ("1 行目\n2 行目", [("1 行目", ""), ("\n", ""), ("2 行目", "")]),
        ("A &amp; B<br>C", [("A & B", ""), ("\n", ""), ("C", "")]),
        ("snake_case_name", [("snake_case_name", "")]),
    ],
)
def test_inline(text: str, expected: list[tuple[str, str]]):
    def flags(r) -> str:
        return (
            ("b" if r.bold else "")
            + ("i" if r.italic else "")
            + ("c" if r.code else "")
            + ("l" if r.link else "")
        )

    assert [(r.text, flags(r)) for r in ep.parse_inline(text)] == expected


# ---- 文字の幅と折り返し ----


def test_count_lines_wraps_japanese_by_character_and_english_by_word():
    jp = [ep.Run("あ" * 10)]
    assert ep.count_lines(jp, 20, 200) == 1
    assert ep.count_lines(jp, 20, 199) == 2
    words = [ep.Run("hello world")]
    width = ep.max_content_width([ep.Run("world")], 20)  # "world" のほうが長い
    assert ep.count_lines(words, 20, width + 1) == 2
    assert ep.count_lines([ep.Run("a"), ep.Run("\n"), ep.Run("b")], 20, 500) == 2


def test_closing_punctuation_does_not_start_a_line():
    """「。」は前の文字といっしょに次の行に送る (行頭の禁則)"""
    runs = [ep.Run("ああああ。")]
    assert ep.count_lines(runs, 10, 40) == 2
    units = ep.text_units(runs, 10)
    assert [w for _, w in units] == [10, 10, 10, 20]


# ---- 位置 (Chromium で測った値と比べる) ----

# (スライド番号, 段落の先頭, 左端, 上端) ― Chromium で測った値
MEASURED = [
    (2, "現状の課題（1", 108.0, 93.2),
    (2, "まとめ（ど真ん中", 108.0, 457.2),
    (3, "問い合わせ件数が", 108.0, 93.2),
    (3, "2024年度：月", 160.0, 132.2),
    (3, "回答までに平均", 108.0, 223.2),
    (4, "定型の質問は A", 56.0, 88.0),
    (4, "社内規程と過去の", 108.0, 134.5),
    (4, "難しい質問は担当", 56.0, 243.0),
    (4, "AI が回答でき", 108.0, 289.5),
    (5, "現行の対応", 56.0, 88.0),
    (5, "新方式", 672.0, 88.0),
    (5, "回答まで当日中を", 724.0, 225.5),
    (6, "社内ポータルから", 108.0, 93.2),
    (7, "一次回答", 676.8, 88.0),
    (7, "難しい質問は要点", 676.8, 244.0),
    (9, "問い合わせ対応シ", 56.0, 88.0),
    (9, "社内ポータル・A", 56.0, 619.0),
    (10, "工数の削減分で、", 108.0, 305.0),
    (1, "情報システム部", 96.0, 388.0),
]


@pytest.mark.parametrize(("page", "text", "x", "y"), MEASURED)
def test_paragraph_positions_match_marp(page: int, text: str, x: float, y: float):
    tops = para_tops(pages_of()[page - 1])
    assert tops[text] == (pytest.approx(x, abs=0.5), pytest.approx(y, abs=0.5))


def test_header_footer_and_lines_match_theme():
    page = pages_of()[1]
    [title] = shapes_named(page, "タイトル")
    assert (title.x, title.y, title.w, title.h, title.anchor) == (
        56,
        0,
        1168,
        68,
        "ctr",
    )
    assert title.paras[0].size == 36 and title.paras[0].bold
    assert title.paras[0].color == ep.TEXT  # 文字は黒 (青ではない)
    # 線は同じ太さ (2px) のグレーで、左右の端から 24px 離す
    rects = [s for s in page.shapes if isinstance(s, ep.Rect)]
    lines = [(s.x, s.y, s.w, s.h, s.color) for s in rects]
    assert lines == [(24, 66, 1232, 2, "B3B3B3"), (24, 668, 1232, 2, "B3B3B3")]
    [logo] = shapes_named(page, "ロゴ")
    # footer img: 高さ 34px、右端は 1280 - 56、フッター (高さ 52px) の上下の真ん中
    assert (logo.h, logo.x + logo.w, logo.y) == (34, 1224, 677)
    assert logo.w == pytest.approx(34 * 160 / 48)
    [number] = shapes_named(page, "ページ番号")
    assert [r.text for r in number.paras[0].runs] == ["2", " / 11"]
    assert number.paras[0].size == ep.PAGE_NUMBER_SIZE == 24
    assert number.paras[0].field_slidenum


def test_cover_layout():
    page = pages_of()[0]
    assert page.background == ep.ACCENT
    bg, title, line, sub = page.shapes
    assert (bg.x, bg.y, bg.w, bg.h) == (0, 0, 1280, 720)
    assert (title.x, title.y, title.w, title.h, title.anchor) == (96, 0, 1088, 329, "b")
    assert (line.x, line.y, line.w, line.h) == (96, 357, 1088, 3)
    assert (sub.x, sub.y) == (96, 388)
    runs = [r.text for r in sub.paras[0].runs]
    assert runs == ["情報システム部 業務改善課", "\n", "2026年11月25日"]


def test_side_images_match_marp():
    """image-right / image-left の画像 (Chromium: 幅 588.8、上端 149.2)"""
    right = [
        s for s in pages_of()[5].shapes if isinstance(s, ep.Picture) and s.name == "図"
    ]
    left = [
        s for s in pages_of()[6].shapes if isinstance(s, ep.Picture) and s.name == "図"
    ]
    assert [(round(s.x, 1), round(s.y, 1), round(s.w, 1)) for s in right] == [
        (635.2, 149.2, 588.8)
    ]
    assert [(round(s.x, 1), round(s.y, 1), round(s.w, 1)) for s in left] == [
        (56.0, 149.2, 588.8)
    ]


def test_table_layout_matches_marp():
    """table クラスの表 (Chromium: 上端 186.5、行の高さ 61、幅 1168)"""
    page = pages_of()[7]
    [table] = [s for s in page.shapes if isinstance(s, ep.TableShape)]
    assert table.y == pytest.approx(187.0)
    assert table.row_heights == [61.0] * 6
    assert sum(table.col_widths) == pytest.approx(1168)
    header = table.rows[0][0]
    assert header.fill == ep.ACCENT and header.paras[0].color == ep.WHITE
    assert header.paras[0].align == "ctr" and table.rows[1][0].paras[0].align == "l"
    assert [r[0].fill for r in table.rows[1:]] == [ep.WHITE, ep.ZEBRA] * 2 + [ep.WHITE]


def test_normal_table_fits_its_text():
    """ふつうの表は文字に合わせた幅 (列は文字が 1 行に収まる幅)"""
    page = pages_of()[9]
    [table] = [s for s in page.shapes if isinstance(s, ep.TableShape)]
    assert (table.x, table.y) == (56.5, 88.5)
    assert table.row_heights == [50.0] * 4  # 8 + 33 + 8 + 1
    assert 400 < sum(table.col_widths) < 460


def test_image_layout_fills_the_rest():
    """image クラスの画像は、小見出しと説明の残りの高さいっぱい (Chromium: 137.5、高さ 470.5)"""
    page = pages_of()[8]
    [pic] = [s for s in page.shapes if isinstance(s, ep.Picture) and s.name == "図"]
    assert (round(pic.y, 1), round(pic.h, 1)) == (137.5, 470.5)
    assert pic.x + pic.w / 2 == pytest.approx(640)


def test_center_layout_is_one_box_centered_vertically():
    page = pages_of()[10]
    [body] = shapes_named(page, "本文")
    assert (body.x, body.y, body.w, body.h, body.anchor) == (56, 88, 1168, 564, "ctr")
    h3, p = body.paras
    assert (h3.size, h3.align, p.size, p.align) == (44, "ctr", 34, "ctr")
    assert p.space_before == pytest.approx(22 + 10.2)  # h3 の下 + p の上 (重ねない)


def test_center_list_is_centered_as_a_block():
    [slide] = slides_of("<!-- _class: center -->\n\n## A\n\n- 短い\n- もう少し長い\n")
    page = ep.Layout(Path("."), []).slide(slide, 1, 1)
    [body] = shapes_named(page, "本文")
    first, second = body.paras
    assert first.mar_l == second.mar_l
    width = 68 + 6 * 34 * ep.WIDTH_SLACK  # 記号の幅 + 「もう少し長い」
    assert first.mar_l == pytest.approx((1168 - width) / 2 + 68)
    assert body.inset_t == pytest.approx(0.2 * 34)  # ul の上の余白


# ---- PPTX ファイル ----


@pytest.fixture(scope="module")
def example_pptx(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("pptx") / "example.pptx"
    assert ep.convert(EXAMPLE, out) == []
    return out


def test_package_parts_are_valid_and_linked(example_pptx: Path):
    with zipfile.ZipFile(example_pptx) as zf:
        names = set(zf.namelist())
        assert zf.testzip() is None
        types = ElementTree.fromstring(zf.read("[Content_Types].xml"))
        overrides = {e.get("PartName", "")[1:] for e in types if e.get("PartName")}
        defaults = {e.get("Extension") for e in types if e.get("Extension")}
        for name in names:
            if name.endswith(".xml") or name.endswith(".rels"):
                ElementTree.fromstring(zf.read(name))  # XML として正しい
            if name.endswith(".xml") and name != "[Content_Types].xml":
                assert name in overrides, name
            else:
                assert (
                    name.rsplit(".", 1)[-1] in defaults or name == "[Content_Types].xml"
                )
        for name in names:
            if not name.endswith(".rels"):
                continue
            base = name.replace("_rels/", "").removesuffix(".rels")
            folder = base.rsplit("/", 1)[0] if "/" in base else ""
            for rel in ElementTree.fromstring(zf.read(name)):
                if rel.get("TargetMode") == "External":
                    continue
                target = rel.get("Target", "")
                path = (Path(folder) / target).as_posix() if folder else target
                parts: list[str] = []
                for part in path.split("/"):
                    if part == "..":
                        parts.pop()
                    elif part not in ("", "."):
                        parts.append(part)
                assert "/".join(parts) in names, (name, target)


def test_slides_have_editable_text_tables_and_lists(example_pptx: Path):
    with zipfile.ZipFile(example_pptx) as zf:
        slides = sorted(
            n for n in zf.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)
        )
        assert len(slides) == 11
        xml = {n: zf.read(n).decode("utf-8") for n in slides}
        presentation = zf.read("ppt/presentation.xml").decode("utf-8")
    assert '<p:sldSz cx="12192000" cy="6858000"/>' in presentation  # 1280x720px
    assert "<a:t>現状の課題</a:t>" in xml["ppt/slides/slide3.xml"]
    assert '<a:buChar char="•"/>' in xml["ppt/slides/slide3.xml"]
    assert '<a:buAutoNum type="arabicPeriod"/>' in xml["ppt/slides/slide2.xml"]
    assert "<a:tbl>" in xml["ppt/slides/slide8.xml"]
    assert "<a:t>一部部署で試験運用</a:t>" in xml["ppt/slides/slide8.xml"]
    assert 'type="slidenum"' in xml["ppt/slides/slide2.xml"]
    # 半角英数は Segoe UI、日本語はメイリオ。行の高さは固定 (26px × 1.5 = 29.25pt)
    assert (
        '<a:latin typeface="Segoe UI"/><a:ea typeface="Meiryo"/>'
        in xml["ppt/slides/slide3.xml"]
    )
    assert '<a:lnSpc><a:spcPts val="2925"/></a:lnSpc>' in xml["ppt/slides/slide3.xml"]
    # 自動で文字を縮めない
    assert all("<a:normAutofit" not in x for x in xml.values())


def test_images_are_embedded(example_pptx: Path):
    """PNG (背景・ロゴ) はそのまま、SVG (仮の画像) は代わりの PNG を付けて入れる"""
    with zipfile.ZipFile(example_pptx) as zf:
        names = zf.namelist()
        cover = zf.read("ppt/slides/slide1.xml").decode("utf-8")
        cover_rels = zf.read("ppt/slides/_rels/slide1.xml.rels").decode("utf-8")
        background = zf.read("ppt/media/image1.png")
        side = zf.read("ppt/slides/slide6.xml").decode("utf-8")
    assert background == (SKILL / "assets" / "background.png").read_bytes()
    assert "../media/image1.png" in cover_rels and "svgBlip" not in cover
    assert "svgBlip" in side
    assert "ppt/media/fallback.png" in names
    # 同じ画像は 1 回だけ入れる (ロゴは全ページで同じもの)
    media = sorted(n for n in names if n.startswith("ppt/media/"))
    assert media == [
        "ppt/media/fallback.png",
        "ppt/media/image1.png",
        "ppt/media/image2.png",
        "ppt/media/image3.svg",
    ]


def test_png_fallback_is_a_valid_png():
    data = ep.png_1x1()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert ep.image_size_from_bytes(data, ".png") == (1.0, 1.0)


def test_missing_image_is_a_warning(tmp_path: Path):
    md = tmp_path / "s.md"
    md.write_text(
        "---\nmarp: true\n---\n\n<!-- _class: image -->\n\n## A\n\n![](none.png)\n",
        encoding="utf-8",
    )
    warnings = ep.convert(md, tmp_path / "s.pptx")
    assert warnings == ["画像がありません (省きました): none.png"]
    assert (tmp_path / "s.pptx").is_file()


def test_special_characters_are_escaped(tmp_path: Path):
    md = tmp_path / "s.md"
    md.write_text('## A & B <c> "d"\n\n- 1 < 2 & 3\n', encoding="utf-8")
    ep.convert(md, tmp_path / "s.pptx")
    with zipfile.ZipFile(tmp_path / "s.pptx") as zf:
        xml = zf.read("ppt/slides/slide1.xml").decode("utf-8")
    ElementTree.fromstring(xml)
    # HTML のタグは (<br> 以外) Marp と同じく文字のまま表示する
    assert "<a:t>A &amp; B &lt;c&gt; &quot;d&quot;</a:t>" in xml
    assert "<a:t>1 &lt; 2 &amp; 3</a:t>" in xml


@pytest.mark.parametrize(
    ("name", "data", "size"),
    [
        (
            "a.svg",
            b'<svg xmlns="http://www.w3.org/2000/svg" width="160" height="48"/>',
            (160, 48),
        ),
        (
            "b.svg",
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 30"/>',
            (40, 30),
        ),
        (
            "c.svg",
            b'<svg xmlns="http://www.w3.org/2000/svg" width="80" viewBox="0 0 40 30"/>',
            (80, 60),
        ),
        ("d.gif", b"GIF89a\x10\x00\x20\x00" + b"\x00" * 10, (16, 32)),
    ],
)
def test_image_size(tmp_path: Path, name: str, data: bytes, size: tuple[int, int]):
    path = tmp_path / name
    path.write_bytes(data)
    assert ep.image_size(path) == size


def test_theme_values_match_theme_css():
    """editable_pptx.py の寸法と色は theme.css と同じ (theme.css を変えたら合わせる)"""
    css = (SKILL / "theme.css").read_text(encoding="utf-8")
    assert f"--kit-accent: #{ep.ACCENT.lower()};" in css
    assert f"--kit-header-h: {ep.HEADER_H}px;" in css
    assert f"--kit-footer-h: {ep.FOOTER_H}px;" in css
    assert f"--kit-side: {ep.SIDE}px;" in css
    assert f"--kit-line: #{ep.LINE.lower()};" in css
    assert f"--kit-line-w: {ep.LINE_W}px;" in css
    assert f"--kit-line-inset: {ep.LINE_INSET}px;" in css
    assert f"--kit-body-gap-top: {ep.BODY_GAP_TOP}px;" in css
    assert f"--kit-body-gap-bottom: {ep.BODY_GAP_BOTTOM}px;" in css
    assert "(var(--kit-header-h) + var(--kit-body-gap-top)) var(--kit-side)" in css
    assert "font-size: 26px;\n  line-height: 1.5;" in css
    assert "column-gap: 64px;" in css
    assert "--kit-image-w: 46%;" in css
    assert "padding: 0 96px;" in css
    assert f"height: {ep.LOGO_H}px;" in css
    assert f"font-size: {ep.PAGE_NUMBER_SIZE}px;\n  color: var(--kit-muted);" in css
    # 文字は黒が基本 (青は線・表の見出しの背景・表紙の背景だけ)
    assert not re.search(r"(?<![-\w])color: var\(--kit-accent\)", css)


def test_headings_are_black():
    """見出し (ヘッダーのタイトル・小見出し・center の小見出し) の文字は黒"""
    pages = pages_of()
    for page in pages[1:]:
        for shape in page.shapes:
            if isinstance(shape, ep.TextBox):
                for p in shape.paras:
                    assert p.color in (ep.TEXT, ep.MUTED), (shape.name, p.color)
