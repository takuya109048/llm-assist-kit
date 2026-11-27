"""SVG の図を PowerPoint の図形にする (skills/marp-slides/editable_pptx.py) のテスト"""

from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest

SKILL = Path(__file__).resolve().parent.parent / "skills" / "marp-slides"


def load():
    spec = importlib.util.spec_from_file_location(
        "editable_pptx", SKILL / "editable_pptx.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ep = load()

MARKER = (
    '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
    'markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
    '<path d="M0,0 L10,5 L0,10 z" fill="#666666"/></marker></defs>'
)


def svg(body: str, w: int = 1100, h: int = 440) -> bytes:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}">{body}</svg>'
    ).encode()


def draw(body: str, x: float = 0, y: float = 0, w: int = 1100, h: int = 440):
    return ep.svg_drawing(svg(body, w, h), x, y, w, h)


def geoms(drawing, kind: str | None = None) -> list:
    return [
        g
        for g in drawing.items
        if isinstance(g, ep.Geom) and (kind is None or g.kind == kind)
    ]


def texts(drawing) -> list:
    return [t for t in drawing.items if isinstance(t, ep.TextBox)]


def test_box_with_two_lines_of_text_becomes_one_shape():
    d = draw(
        '<rect x="20" y="110" width="200" height="140" rx="10" fill="#f3f5f8" '
        'stroke="#b3b3b3" stroke-width="2"/>'
        '<text x="120" y="172" font-size="26" font-weight="700" fill="#222222" '
        'text-anchor="middle">社員</text>'
        '<text x="120" y="208" font-size="20" fill="#666666" '
        'text-anchor="middle">質問を入力</text>',
        x=90,
        y=150,
    )
    [box] = geoms(d)
    assert texts(d) == []  # 文字は箱の中の段落になる
    assert box.kind == "roundRect" and box.radius == 10
    assert (box.x, box.y, box.w, box.h) == (110, 260, 200, 140)
    assert (box.fill, box.stroke, box.stroke_w) == ("F3F5F8", "B3B3B3", 2)
    first, second = box.paras
    assert ep.plain_text(first.runs) == "社員" and first.runs[0].bold
    assert (first.size, first.color, first.align) == (26, "222222", "ctr")
    assert ep.plain_text(second.runs) == "質問を入力" and second.color == "666666"
    # 1 行目の上端は、ベースライン (y=172) から文字の上までの距離だけ上
    assert box.inset_t == pytest.approx(172 - ep.SVG_TEXT_BASELINE * 26 - 110)
    top2 = 208 - ep.SVG_TEXT_BASELINE * 20
    top1_bottom = 172 - ep.SVG_TEXT_BASELINE * 26 + 26 * ep.SVG_TEXT_LINE
    assert second.space_before == pytest.approx(top2 - top1_bottom)
    assert box.inset_l == box.inset_r == 0  # 箱の真ん中


def test_marker_arrow_between_boxes_is_a_glued_connector():
    d = draw(
        MARKER + '<rect x="20" y="110" width="200" height="140" fill="#fff"/>'
        '<rect x="300" y="110" width="200" height="140" fill="#fff"/>'
        '<line x1="220" y1="180" x2="300" y2="180" stroke="#666666" '
        'stroke-width="3" marker-end="url(#arrow)"/>'
    )
    left, right, line = geoms(d)
    assert line.kind == "line" and line.fill is None
    assert (line.x, line.y, line.w, line.h) == (220, 180, 80, 0)
    assert (line.head, line.tail) == (None, "lg")
    assert line.glue_start == (left, 3)  # 右辺の真ん中
    assert line.glue_end == (right, 1)  # 左辺の真ん中


def test_polygon_arrowhead_is_merged_into_the_line():
    """線と三角形で描いた矢印 (以前の書き方) も、線の矢じりにする"""
    d = draw(
        '<line x1="220" y1="180" x2="286" y2="180" stroke="#666666" stroke-width="3"/>'
        '<polygon points="298,180 284,172 284,188" fill="#666666"/>'
        '<polyline points="970,250 970,330 680,330 680,264" fill="none" '
        'stroke="#666666" stroke-width="3" stroke-dasharray="10 8"/>'
        '<polygon points="680,252 672,266 688,266" fill="#666666"/>'
    )
    line, back = geoms(d)
    assert line.kind == "line" and line.tail == "lg" and line.w == 78  # 先端まで
    assert back.kind == "path" and back.tail == "lg" and back.dash
    assert back.fill is None
    assert back.path[-1] == ("L", [(0, 2)])  # 先端 (680, 252)。図形の左上は (680, 250)


def test_right_to_left_and_upward_lines_are_flipped():
    d = draw(
        MARKER + '<line x1="300" y1="200" x2="100" y2="100" stroke="#000" '
        'marker-start="url(#arrow)" marker-end="url(#arrow)"/>'
    )
    [line] = geoms(d)
    assert (line.x, line.y, line.w, line.h) == (100, 100, 200, 100)
    assert line.flip_h and line.flip_v
    assert line.head == line.tail == "lg"


def test_free_text_keeps_its_anchor():
    d = draw(
        '<text x="20" y="60" font-size="22" fill="#666666">左寄せ</text>'
        '<text x="1080" y="420" font-size="20" text-anchor="end">右寄せ</text>'
    )
    left, right = texts(d)
    assert left.x == 20 and left.paras[0].align == "l" and not left.wrap
    assert left.y == pytest.approx(60 - ep.SVG_TEXT_BASELINE * 22)
    assert right.x + right.w == pytest.approx(1080)
    assert right.paras[0].align == "r"


def test_text_not_attached_to_background_or_mismatched_box():
    d = draw(
        '<rect width="1100" height="440" fill="#ffffff"/>'
        '<rect x="100" y="100" width="300" height="200" fill="#eeeeee"/>'
        '<text x="250" y="180" text-anchor="middle" font-size="24">中央</text>'
        '<text x="110" y="280" font-size="20">左下</text>'
        '<text x="600" y="50" font-size="20">外</text>'
    )
    background, box = geoms(d)
    assert background.paras == []
    assert [ep.plain_text(p.runs) for p in box.paras] == ["中央"]
    assert [ep.plain_text(t.paras[0].runs) for t in texts(d)] == ["左下", "外"]


def test_tspan_colors_and_lines():
    d = draw(
        '<text x="300" y="100" font-size="20" fill="#222222">データ'
        '<tspan fill="#d32f2f" font-weight="bold">ベース</tspan></text>'
        '<text x="300" y="200" font-size="20" text-anchor="middle">'
        '<tspan x="300" dy="0">1 行目</tspan><tspan x="300" dy="28">2 行目</tspan>'
        "</text>"
    )
    first, line1, line2 = texts(d)
    runs = first.paras[0].runs
    assert [(r.text, r.color, r.bold) for r in runs] == [
        ("データ", None, False),
        ("ベース", "D32F2F", True),
    ]
    assert line2.y - line1.y == pytest.approx(28)


def test_group_translate_and_arcs():
    d = draw(
        '<g transform="translate(400 40)">'
        '<path d="M0,30 A100,30 0 0 1 200,30 L200,170 A100,30 0 0 1 0,170 Z" '
        'fill="#f3f5f8" stroke="#b3b3b3"/></g>'
        '<circle cx="120" cy="120" r="80" fill="#e8eef6"/>'
    )
    cylinder, circle = geoms(d)
    assert cylinder.kind == "path"
    assert {c for c, _ in cylinder.path} == {"M", "C", "L", "Z"}
    assert (cylinder.x, cylinder.y, cylinder.w) == pytest.approx((400, 40, 200))
    assert circle.kind == "ellipse"
    assert (circle.x, circle.y, circle.w, circle.h) == (40, 40, 160, 160)


def test_scaled_to_the_placed_size():
    """置き場所が小さいときは、位置・線の太さ・文字の大きさを同じ割合で縮める"""
    data = svg(
        '<rect x="0" y="0" width="100" height="100" stroke="#000" stroke-width="4"/>'
        '<text x="300" y="300" font-size="40">字</text>',
        w=1100,
        h=440,
    )
    d = ep.svg_drawing(data, 0, 0, 550, 220)
    [box] = geoms(d)
    [text] = texts(d)
    assert (box.w, box.stroke_w) == (50, 2)
    assert text.paras[0].size == 20


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (
            '<defs><linearGradient id="g"/></defs><rect width="9" height="9" '
            'fill="url(#g)"/>',
            "グラデーション",
        ),
        ('<rect width="9" height="9" transform="rotate(30)"/>', "rotate"),
        ('<image href="a.png" width="9" height="9"/>', "<image>"),
        ("<foreignObject/>", "<foreignObject>"),
        ('<rect width="50%" height="9"/>', "%"),
    ],
)
def test_unsupported_svg_is_an_error(body: str, reason: str):
    with pytest.raises(ep.SvgError, match=reason):
        draw(body)


def test_unsupported_svg_stays_an_image_with_a_warning(tmp_path: Path):
    (tmp_path / "g.svg").write_bytes(
        svg('<rect width="9" height="9" filter="x"/><image href="a.png"/>')
    )
    (tmp_path / "placeholder.svg").write_bytes(svg('<rect width="9" height="9"/>'))
    md = tmp_path / "s.md"
    md.write_text(
        "---\nmarp: true\n---\n\n<!-- _class: image -->\n\n## a\n\n![](g.svg)\n\n"
        "---\n\n<!-- _class: image -->\n\n## b\n\n![](placeholder.svg)\n",
        encoding="utf-8",
    )
    warnings = ep.convert(md, tmp_path / "s.pptx")
    assert warnings == [
        "SVG の図を PowerPoint の図形にできないので、画像のまま入れました"
        " (<image>): g.svg"
    ]
    with zipfile.ZipFile(tmp_path / "s.pptx") as zf:
        names = zf.namelist()
        assert "svgBlip" in zf.read("ppt/slides/slide1.xml").decode()
        # 仮の画像は差し替えるものなので、警告なしで画像のまま
        assert "svgBlip" in zf.read("ppt/slides/slide2.xml").decode()
    assert sum(n.endswith(".svg") for n in names) == 2


def test_example_figure_in_pptx_is_editable(tmp_path: Path):
    out = tmp_path / "example.pptx"
    assert ep.convert(SKILL / "example.md", out) == []
    with zipfile.ZipFile(out) as zf:
        xml = zf.read("ppt/slides/slide9.xml").decode("utf-8")
    root = ElementTree.fromstring(xml)  # XML として正しい
    p = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
    a = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    [group] = root.iter(f"{p}grpSp")
    connectors = list(group.iter(f"{p}cxnSp"))
    assert len(connectors) == 3
    for cxn in connectors:
        assert cxn.find(f".//{a}stCxn") is not None
        assert cxn.find(f".//{a}endCxn") is not None
        assert [e.get("type") for e in cxn.iter(f"{a}tailEnd")] == ["triangle"]
    # 箱の中の文字は、箱 (角の丸い四角) の文字
    boxes = [
        sp
        for sp in group.iter(f"{p}sp")
        if sp.find(f".//{a}prstGeom[@prst='roundRect']") is not None
    ]
    assert len(boxes) == 4
    words = ["".join(t.text or "" for t in b.iter(f"{a}t")) for b in boxes]
    assert words == [
        "社員質問を入力",
        "社内ポータル受け付け",
        "AI回答案を作る",
        "担当者確認して送信",
    ]
    # 戻りの点線は、矢じり付きのフリーフォーム
    freeform = [
        sp for sp in group.iter(f"{p}sp") if sp.find(f".//{a}custGeom") is not None
    ]
    assert len(freeform) == 1
    assert [e.get("val") for e in freeform[0].iter(f"{a}prstDash")] == ["dash"]
    assert freeform[0].find(f".//{a}tailEnd") is not None
    assert "svgBlip" not in xml
    # 図形の ID は重ならない
    ids = [e.get("id") for e in root.iter(f"{p}cNvPr")]
    assert len(ids) == len(set(ids))
