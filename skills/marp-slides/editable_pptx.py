"""Marp のスライド (kit-slides テーマ) を、PowerPoint で編集できる PPTX にする

使い方:
    python editable_pptx.py slides.md               # slides.pptx を作る
    python editable_pptx.py slides.md -o out.pptx

ふつうは build.py の --pptx から使う。標準ライブラリだけで動き、Marp CLI・
ブラウザ・LibreOffice は使わない。

- 対象は SKILL.md の書き方に沿った Markdown (表紙、ヘッダー/フッター、本文のレイアウト
  cols / image-right / image-left / table / image / center、見出し・段落・箇条書き・
  番号付きリスト・表・画像・太字・斜体・コード・リンク)
- 文字は PowerPoint の段落と箇条書き、表は PowerPoint の表、画像・線・ロゴは個別の
  図形になるので、そのまま PowerPoint で編集できる
- 位置と大きさは theme.css (と Marp の default テーマ) の寸法を、そのまま
  1px = 1/96 インチで写す。行の高さは「固定値」で指定し、箱の内側の余白は 0 にする。
  折り返しの位置だけは文字の幅を見積もって計算するので、ブラウザと 1 文字程度ずれることがある
- 本文の SVG の図 (SKILL.md の書き方のもの) は、PowerPoint の図形・矢印・テキストのグループに
  置き換える。置き換えられない SVG と仮の画像は SVG のまま埋め込む (PowerPoint 2016 以降で表示
  できる)。PNG / JPEG / GIF も使える
"""

from __future__ import annotations

import argparse
import math
import re
import struct
import sys
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from xml.etree import ElementTree

# ---- テーマの寸法 (theme.css と Marp の default テーマ。単位は px、スライドは 1280x720) ----

SLIDE_W = 1280
SLIDE_H = 720
EMU_PER_PX = 9525  # 1px = 1/96 インチ = 9525 EMU
HEADER_H = 68  # --kit-header-h
FOOTER_H = 52  # --kit-footer-h
LINE_W = 2  # --kit-line-w (ヘッダー・フッターの線の太さ)
LINE_INSET = 24  # --kit-line-inset (線の左右の端からの距離)
BODY_GAP_TOP = 20  # --kit-body-gap-top
BODY_GAP_BOTTOM = 16  # --kit-body-gap-bottom
SIDE = 56  # --kit-side
BODY_TOP = HEADER_H + BODY_GAP_TOP
BODY_BOTTOM = SLIDE_H - (FOOTER_H + BODY_GAP_BOTTOM)
BODY_LEFT = SIDE
BODY_W = SLIDE_W - 2 * SIDE
COLS_GAP = 64  # section.cols の column-gap
IMAGE_W = SLIDE_W * 0.46  # section.image-right / image-left の --kit-image-w
IMAGE_GAP = 32  # 画像とテキストの間
COVER_SIDE = 96  # section.cover の左右の余白
COVER_TITLE_H = SLIDE_H / 2  # 表紙のタイトル (h1) の高さ (下端が中央の線)
COVER_TITLE_PAD = 28
COVER_LINE = 3
LOGO_H = 34  # footer img の高さ
PAGE_NUMBER_SIZE = 24  # ページ番号 (section::after) の文字の大きさ

ACCENT = "1F4E8C"  # --kit-accent
LINE = "B3B3B3"  # --kit-line (ヘッダー・フッターの線)
TEXT = "222222"  # --kit-text
MUTED = "666666"  # --kit-muted
WHITE = "FFFFFF"
QUOTE_COLOR = "59636E"
BORDER = "D1D9E0"  # 表の罫線、引用の線、コードの枠
ZEBRA = "F6F8FA"  # 表の偶数行、コードの背景
CODE_TEXT = "1F2328"
INLINE_CODE_BG = "EEEFF1"  # rgba(129, 139, 152, 0.12) を白の上に重ねた色

LATIN_FONT = "Segoe UI"  # 半角英数 (theme.css の --kit-font)
EA_FONT = "Meiryo"  # 全角 (日本語)
MONO_FONT = "Consolas"
BULLET_FONT = "Arial"

ACCEPTED_IMAGES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
}

# ---- Markdown の中身 ----


@dataclass
class Run:
    """同じ書式の文字のまとまり。text が "\\n" のものは改行"""

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    strike: bool = False
    link: str | None = None
    color: str | None = None  # 文字の色 (<span class="red"> など)。None なら段落の色
    underline: bool = False


@dataclass
class Heading:
    level: int
    runs: list[Run]


@dataclass
class Paragraph:
    runs: list[Run]


@dataclass
class Image:
    src: str
    alt: str = ""


@dataclass
class ListItem:
    runs: list[Run]
    children: list[ListBlock] = field(default_factory=list)


@dataclass
class ListBlock:
    ordered: bool
    start: int = 1
    items: list[ListItem] = field(default_factory=list)


@dataclass
class Table:
    header: list[list[Run]]
    rows: list[list[list[Run]]]
    aligns: list[str | None]


@dataclass
class Quote:
    runs: list[Run]


@dataclass
class Code:
    text: str


Block = Heading | Paragraph | Image | ListBlock | Table | Quote | Code


@dataclass
class Slide:
    blocks: list[Block]
    cls: str = ""
    paginate: bool = False
    footer: str = ""
    backgrounds: list[Image] = field(default_factory=list)


# ---- Markdown を読む ----

FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
LIST_RE = re.compile(r"^(\s*)([-*+]|\d{1,9}[.)])(\s+|$)(.*)$")
QUOTE_RE = re.compile(r"^\s{0,3}>\s?(.*)$")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
COMMENT_RE = re.compile(r"<!--(.*?)-->", re.S)
DIRECTIVE_RE = re.compile(r"^\s*(_?)([A-Za-z]+)\s*:\s*(.*?)\s*$")
IMAGE_ONLY_RE = re.compile(
    r"^\s*!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)\s*$"
)
BG_IMAGE_RE = re.compile(
    r"!\[(bg(?:\s[^\]]*)?)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)"
)
LOCAL_DIRECTIVES = {"class", "paginate", "footer", "header"}


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """先頭の YAML (--- で囲んだ部分) を、キーと値の辞書と残りの本文に分ける"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    for end in range(1, len(lines)):
        if lines[end].strip() in ("---", "..."):
            meta = {}
            for line in lines[1:end]:
                m = DIRECTIVE_RE.match(line)
                if m and not m.group(1):
                    meta[m.group(2)] = unquote(m.group(3))
            return meta, "\n".join(lines[end + 1 :])
    return {}, text


def unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def split_slides(body: str) -> list[str]:
    """--- だけの行でスライドに分ける (コードブロックの中は除く)"""
    slides: list[list[str]] = [[]]
    fence = ""
    for line in body.splitlines():
        m = FENCE_RE.match(line)
        if m:
            if not fence:
                fence = m.group(1)[0] * 3
            elif line.strip().startswith(fence):
                fence = ""
        if not fence and line.strip() == "---":
            slides.append([])
        else:
            slides[-1].append(line)
    texts = ["\n".join(lines) for lines in slides]
    # 本文の先頭が --- のとき (フロントマターの直後) にできる空のスライドは除く
    if len(texts) > 1 and not texts[0].strip():
        texts = texts[1:]
    return texts


def parse_directives(comment: str) -> dict[str, tuple[str, bool]] | None:
    """HTML コメントがディレクティブなら {名前: (値, そのスライドだけか)}、違えば None"""
    found: dict[str, tuple[str, bool]] = {}
    for line in comment.strip().splitlines():
        if not line.strip():
            continue
        m = DIRECTIVE_RE.match(line)
        if not m:
            return None
        found[m.group(2)] = (unquote(m.group(3)), bool(m.group(1)))
    return found or None


def to_bool(value: str) -> bool:
    return value.strip().lower() in ("true", "yes", "on", "1")


def parse_markdown(text: str) -> list[Slide]:
    """Marp の Markdown をスライドの一覧にする"""
    meta, body = split_front_matter(text.replace("\r\n", "\n"))
    state = {key: meta[key] for key in LOCAL_DIRECTIVES if key in meta}
    slides = []
    for chunk in split_slides(body):
        local: dict[str, str] = {}
        for m in COMMENT_RE.finditer(chunk):
            for key, (value, only_here) in (parse_directives(m.group(1)) or {}).items():
                if key not in LOCAL_DIRECTIVES:
                    continue
                if only_here:
                    local[key] = value
                else:
                    state[key] = value
        chunk = COMMENT_RE.sub("", chunk)
        settings = {**state, **local}
        backgrounds: list[Image] = []

        def take_bg(m: re.Match[str]) -> str:
            backgrounds.append(Image(m.group(2), m.group(1)))
            return ""

        chunk = BG_IMAGE_RE.sub(take_bg, chunk)
        slides.append(
            Slide(
                blocks=parse_blocks(chunk.split("\n")),
                cls=settings.get("class", "").strip(),
                paginate=to_bool(settings.get("paginate", "false")),
                footer=settings.get("footer", ""),
                backgrounds=backgrounds,
            )
        )
    return slides


def is_block_start(line: str) -> bool:
    return bool(
        HEADING_RE.match(line)
        or FENCE_RE.match(line)
        or QUOTE_RE.match(line)
        or LIST_RE.match(line)
    )


def parse_blocks(lines: list[str]) -> list[Block]:
    blocks: list[Block] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if m := FENCE_RE.match(line):
            fence = m.group(1)
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence):
                code.append(lines[i])
                i += 1
            blocks.append(Code("\n".join(code)))
            i += 1
            continue
        if m := HEADING_RE.match(line):
            blocks.append(Heading(len(m.group(1)), parse_inline(m.group(2))))
            i += 1
            continue
        if "|" in line and i + 1 < len(lines) and TABLE_SEP_RE.match(lines[i + 1]):
            i = parse_table(lines, i, blocks)
            continue
        if QUOTE_RE.match(line):
            quoted = []
            while i < len(lines) and lines[i].strip():
                m = QUOTE_RE.match(lines[i])
                quoted.append(m.group(1) if m else lines[i])
                i += 1
            blocks.append(Quote(parse_inline("\n".join(q for q in quoted))))
            continue
        if LIST_RE.match(line):
            i = parse_list(lines, i, blocks)
            continue
        para = [line.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not is_block_start(lines[i]):
            para.append(lines[i].strip())
            i += 1
        text = "\n".join(para)
        if m := IMAGE_ONLY_RE.match(text):
            blocks.append(Image(m.group(2), m.group(1)))
        elif text.strip():
            blocks.append(Paragraph(parse_inline(text)))
    return blocks


def split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    cells = re.split(r"(?<!\\)\|", line)
    return [c.strip().replace("\\|", "|") for c in cells]


def parse_table(lines: list[str], i: int, blocks: list[Block]) -> int:
    header = split_row(lines[i])
    aligns: list[str | None] = []
    for cell in split_row(lines[i + 1]):
        left, right = cell.startswith(":"), cell.endswith(":")
        aligns.append(
            "ctr" if left and right else "r" if right else "l" if left else None
        )
    i += 2
    rows = []
    while i < len(lines) and lines[i].strip() and "|" in lines[i]:
        rows.append(split_row(lines[i]))
        i += 1
    n = len(header)
    aligns = (aligns + [None] * n)[:n]
    blocks.append(
        Table(
            [parse_inline(c) for c in header],
            [[parse_inline(c) for c in (row + [""] * n)[:n]] for row in rows],
            aligns,
        )
    )
    return i


def parse_list(lines: list[str], i: int, blocks: list[Block]) -> int:
    """箇条書き・番号付きリスト (入れ子あり) を読む"""
    # stack: (リスト, 記号の桁, 中身の桁)
    stack: list[tuple[ListBlock, int, int]] = []
    root: ListBlock | None = None
    texts: dict[int, list[str]] = {}  # id(item) -> 行
    items: list[ListItem] = []
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            # 空行の次も (字下げした) リストの続きなら続ける
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and (
                LIST_RE.match(lines[j]) or lines[j].startswith((" " * 2, "\t"))
            ):
                if LIST_RE.match(lines[j]) and not lines[j][0].isspace():
                    m = LIST_RE.match(lines[j])
                    assert m
                    if root and (m.group(2)[0].isdigit()) != root.ordered:
                        break
                i = j
                continue
            break
        m = LIST_RE.match(line)
        if m:
            indent = len(m.group(1).expandtabs(4))
            marker = m.group(2)
            ordered = marker[0].isdigit()
            content_col = indent + len(marker) + max(1, len(m.group(3)))
            while stack and indent < stack[-1][1]:
                stack.pop()
            if stack and indent >= stack[-1][2] and stack[-1][0].items:
                parent = stack[-1][0].items[-1]
                child = ListBlock(ordered, int(marker[:-1]) if ordered else 1)
                parent.children.append(child)
                stack.append((child, indent, content_col))
            elif not stack:
                if root is not None:
                    break
                root = ListBlock(ordered, int(marker[:-1]) if ordered else 1)
                stack.append((root, indent, content_col))
            elif stack[-1][0].ordered != ordered and len(stack) == 1:
                break  # 種類の違うリストは別のリスト
            item = ListItem([])
            stack[-1][0].items.append(item)
            items.append(item)
            texts[id(item)] = [m.group(4).strip()]
        else:
            if not items or is_block_start(line) and not line[0].isspace():
                break
            texts[id(items[-1])].append(line.strip())
        i += 1
    for item in items:
        item.runs = parse_inline("\n".join(t for t in texts[id(item)] if t))
    if root:
        blocks.append(root)
    return i


INLINE_RE = re.compile(
    r"(?P<esc>\\(?P<escch>[!-/:-@\[-`{-~]))"
    r"|(?P<code>(?P<ticks>`+)(?P<codetext>.+?)(?P=ticks))"
    r"|(?P<img>!\[(?P<imgalt>[^\]]*)\]\([^)]*\))"
    r"|(?P<link>\[(?P<linktext>[^\]]+)\]\(\s*<?(?P<href>[^)\s>]*)>?(?:\s+\"[^\"]*\")?\s*\))"
    r"|(?P<autolink><(?P<auto>https?://[^>\s]+)>)"
    r"|(?P<bold>\*\*(?P<boldtext>.+?)\*\*|__(?P<boldtext2>.+?)__)"
    r"|(?P<strike>~~(?P<striketext>.+?)~~)"
    r"|(?P<em>\*(?P<emtext>[^*\s](?:.*?[^*\s])?)\*"
    r"|(?<![0-9A-Za-z])_(?P<emtext2>[^_\s](?:.*?[^_\s])?)_(?![0-9A-Za-z]))"
    r"|(?P<span><span(?P<spanattrs>(?:\s[^>]*)?)>(?P<spantext>.*?)</span\s*>)"
    r"|(?P<htag><(?P<htagname>b|strong|i|em|u|s|del)>(?P<htagtext>.*?)</(?P=htagname)\s*>)"
    r"|(?P<br><br\s*/?>)"
    r"|(?P<tag></?[A-Za-z][^>]*>)"
    r"|(?P<nl>[ \t]*\n[ \t]*)",
    re.S,
)


# 文字の色分け (<span class="red">) の色。theme.css の --kit-red などと同じ
SPAN_COLORS = {
    "red": "D32F2F",
    "blue": "1F4E8C",
    "green": "2E7D32",
    "orange": "E65100",
    "gray": "757575",
    "grey": "757575",
}
# style="color: ..." で使える色の名前 (よく使うものだけ)
NAMED_COLORS = {
    **SPAN_COLORS,
    "black": "000000",
    "white": "FFFFFF",
    "purple": "800080",
    "yellow": "FFFF00",
    "navy": "000080",
    "darkred": "8B0000",
}
CLASS_ATTR_RE = re.compile(r"""\bclass\s*=\s*["']([^"']*)["']""", re.I)
STYLE_COLOR_RE = re.compile(r"""(?:^|[;"'\s])color\s*:\s*([^;"']+)""", re.I)


def parse_color(value: str) -> str | None:
    """CSS の色 (#rgb・#rrggbb・rgb(r, g, b)・名前) を RRGGBB にする"""
    value = value.strip().lower()
    if m := re.fullmatch(r"#([0-9a-f]{3})", value):
        return "".join(c * 2 for c in m.group(1)).upper()
    if m := re.fullmatch(r"#([0-9a-f]{6})", value):
        return m.group(1).upper()
    if m := re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)[^)]*\)", value):
        return "".join(f"{min(int(v), 255):02X}" for v in m.groups())
    return NAMED_COLORS.get(value)


def span_color(attrs: str) -> str | None:
    """<span> の属性から文字の色を取り出す (style の color が class より優先)"""
    if m := STYLE_COLOR_RE.search(attrs):
        color = parse_color(m.group(1))
        if color:
            return color
    if m := CLASS_ATTR_RE.search(attrs):
        for name in m.group(1).split():
            if name.lower() in SPAN_COLORS:
                return SPAN_COLORS[name.lower()]
    return None


def delimiter_of(g: dict[str, str | None]) -> str | None:
    """強調・太字・取り消し線の記号 (* ** ~~)。_ は前後が英数字かを正規表現で見ている"""
    if g["bold"] and g["boldtext"] is not None:
        return "**"
    if g["strike"]:
        return "~~"
    if g["em"] and g["emtext"] is not None:
        return "*"
    return None


def is_punct(ch: str) -> bool:
    """CommonMark (markdown-it) の「句読点・記号」(ASCII の記号と Unicode の P・S)"""
    return (
        ch.isascii()
        and not ch.isalnum()
        and not ch.isspace()
        or (unicodedata.category(ch)[0] in "PS")
    )


def delimiters_flank(text: str, start: int, end: int, n: int) -> bool:
    """開く記号 (start から n 文字) と閉じる記号 (end の手前 n 文字) が、CommonMark の
    left-flanking / right-flanking の決まりを満たすか (満たさないと強調にならない)"""
    before = text[start - 1] if start > 0 else " "
    after_open = text[start + n] if start + n < len(text) else " "
    before_close = text[end - n - 1] if end - n - 1 >= 0 else " "
    after = text[end] if end < len(text) else " "
    left = not after_open.isspace() and (
        not is_punct(after_open) or before.isspace() or is_punct(before)
    )
    right = not before_close.isspace() and (
        not is_punct(before_close) or after.isspace() or is_punct(after)
    )
    return left and right


def parse_inline(text: str, base: Run | None = None) -> list[Run]:
    """行の中の書式 (太字・斜体・コード・リンク・色・改行) を Run の並びにする"""
    base = base or Run("")
    runs: list[Run] = []

    def add(s: str, code: bool = False, link: str | None = None) -> None:
        if s:
            runs.append(
                replace(base, text=s, code=base.code or code, link=link or base.link)
            )

    def nested(s: str, sub: Run) -> None:
        runs.extend(parse_inline(s, sub))

    pos = 0
    search_from = 0
    while m := INLINE_RE.search(text, search_from):
        g = m.groupdict()
        delim = delimiter_of(g)
        if delim and not delimiters_flank(text, m.start(), m.end(), len(delim)):
            # Marp (markdown-it) と同じく、前後の文字によっては * ** ~~ を強調に
            # しない (例: 日本語の直後の **<span>...</span>**)。開く記号を文字のまま
            # 残し、その次から探し直す (記号の連なりは 1 つとして扱う)
            search_from = m.start() + len(delim)
            while search_from < len(text) and text[search_from] == delim[0]:
                search_from += 1
            continue
        add(unescape(text[pos : m.start()]))
        pos = search_from = m.end()
        if g["esc"]:
            add(g["escch"])
        elif g["code"]:
            add(g["codetext"].strip() or g["codetext"], code=True)
        elif g["img"]:
            add(g["imgalt"])
        elif g["link"]:
            nested(g["linktext"], replace(base, link=g["href"]))
        elif g["autolink"]:
            add(g["auto"], link=g["auto"])
        elif g["bold"]:
            nested(g["boldtext"] or g["boldtext2"] or "", replace(base, bold=True))
        elif g["strike"]:
            nested(g["striketext"], replace(base, strike=True))
        elif g["em"]:
            nested(g["emtext"] or g["emtext2"] or "", replace(base, italic=True))
        elif g["span"]:
            color = span_color(g["spanattrs"] or "") or base.color
            nested(g["spantext"], replace(base, color=color))
        elif g["htag"]:
            tag = g["htagname"].lower()
            sub = {
                "b": replace(base, bold=True),
                "strong": replace(base, bold=True),
                "i": replace(base, italic=True),
                "em": replace(base, italic=True),
                "u": replace(base, underline=True),
            }.get(tag, replace(base, strike=True))
            nested(g["htagtext"], sub)
        elif g["br"] or g["nl"]:
            runs.append(Run("\n"))
        # そのほかの HTML タグ (g["tag"]) は表示しない (Marp も HTML として扱う)
    add(unescape(text[pos:]))
    return runs


def plain_text(runs: list[Run]) -> str:
    return "".join(r.text for r in runs)


# ---- 文字の幅の見積もり (折り返しと表の列幅に使う) ----

# Segoe UI の半角文字の幅 (1em に対する割合)
LATIN_WIDTHS: dict[str, float] = {" ": 0.274}
for _chars, _width in [
    ("0123456789", 0.559),
    ("il|!.,:;'", 0.245),
    ("jI", 0.27),
    ("frt()[]{}", 0.34),
    ('`"', 0.38),
    ("szJ-/\\*", 0.42),
    ("ckvxyLT?_", 0.48),
    ("abdeghnopquFEZ", 0.54),
    ("SPKRXYBC^~", 0.58),
    ("VAG$#+<>=", 0.64),
    ("DHNOQU", 0.74),
    ("w&%", 0.76),
    ("mM", 0.86),
    ("W@", 0.95),
]:
    for _ch in _chars:
        LATIN_WIDTHS[_ch] = _width

# 行頭に来ない文字 (前の文字とつなげる) と、行末に来ない文字 (次の文字とつなげる)
NO_LINE_START = set(
    "、。，．・：；？！ー）」』】〕〉》｝］’”ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々〜…‥,.:;!?)]}%"
)
NO_LINE_END = set("（「『【〔〈《｛［‘“([{")


# 文字の幅は見積もりなので、幅を文字に合わせるとき (表の列・center の箇条書き) は少し広げる。
# 狭すぎると PowerPoint で 1 文字だけ次の行に送られてしまうため
WIDTH_SLACK = 1.06


def char_em(ch: str) -> float:
    if ch in LATIN_WIDTHS:
        return LATIN_WIDTHS[ch]
    if ch.isascii():
        return 0.5
    kind = unicodedata.east_asian_width(ch)
    if kind in ("W", "F"):
        return 1.0
    if kind == "H":
        return 0.5
    return 0.6


def is_wide(ch: str) -> bool:
    return unicodedata.east_asian_width(ch) in ("W", "F")


def run_char_width(ch: str, run: Run, size: float) -> float:
    if run.code:
        return 0.55 * size * 0.85
    width = char_em(ch) * size
    if run.bold and not is_wide(ch):
        width *= 1.06
    return width


def text_units(runs: list[Run], size: float) -> list[tuple[str, float]]:
    """折り返しの単位 ("br" / "space" / "word", 幅) の並びにする

    日本語は 1 文字ずつ (行頭・行末の禁則はつなげる)、英数字は単語ごと。
    """
    units: list[list] = []  # [kind, width, 最後の文字]
    for run in runs:
        if run.text == "\n":
            units.append(["br", 0.0, ""])
            continue
        if run.code:
            units.append(["word", 0.4 * size * 0.85 * 2, ""])  # 左右の余白
        for ch in run.text:
            w = run_char_width(ch, run, size)
            last = units[-1] if units else None
            if ch == " " or ch == "\t":
                units.append(["space", w, " "])
            elif ch in NO_LINE_START and last and last[0] == "word":
                last[1] += w
                last[2] = ch
            elif last and last[0] == "word" and last[2] in NO_LINE_END:
                last[1] += w
                last[2] = ch
            elif is_wide(ch):
                units.append(["word", w, ch])
            elif last and last[0] == "word" and last[2] and not is_wide(last[2]):
                last[1] += w
                last[2] = ch
            else:
                units.append(["word", w, ch])
    return [(u[0], u[1]) for u in units]


def count_lines(runs: list[Run], size: float, width: float) -> int:
    """幅 width に収めたときの行数"""
    lines, x = 1, 0.0
    pending_space = 0.0
    for kind, w in text_units(runs, size):
        if kind == "br":
            lines, x, pending_space = lines + 1, 0.0, 0.0
        elif kind == "space":
            pending_space += w
        else:
            if x > 0 and x + pending_space + w > width + 0.5:
                lines += 1
                x = 0.0
            else:
                x += pending_space
            pending_space = 0.0
            while w > width and x == 0 and width > 0:
                lines += 1
                w -= width
            x += w
    return lines


def max_content_width(runs: list[Run], size: float) -> float:
    widths, x = [0.0], 0.0
    for kind, w in text_units(runs, size):
        if kind == "br":
            widths.append(x)
            x = 0.0
        else:
            x += w
    widths.append(x)
    return max(widths)


def min_content_width(runs: list[Run], size: float) -> float:
    return max((w for kind, w in text_units(runs, size) if kind == "word"), default=0.0)


# ---- PowerPoint の図形 (位置と大きさは px) ----


@dataclass
class Para:
    runs: list[Run]
    size: float  # 文字の大きさ (px)
    line: float  # 行の高さ (px)
    color: str = TEXT
    bold: bool = False
    italic: bool = False
    align: str = "l"
    space_before: float = 0.0
    space_after: float = 0.0
    mar_l: float = 0.0
    indent: float = 0.0
    bullet: str | None = None  # 記号 ("•" など)
    bullet_font: str = BULLET_FONT
    autonum: str | None = None  # 番号の種類 ("arabicPeriod" など)
    start: int = 1
    field_slidenum: bool = False  # 先頭の run をスライド番号にする
    level: int = 0  # 箇条書きの深さ (番号を入れ子の後ろでも続けるのに使う)


@dataclass
class TextBox:
    x: float
    y: float
    w: float
    h: float
    paras: list[Para]
    anchor: str = "t"
    inset_t: float = 0.0
    inset_b: float = 0.0
    inset_l: float = 0.0
    inset_r: float = 0.0
    fill: str | None = None
    border: str | None = None
    name: str = "テキスト"
    wrap: bool = True  # False なら折り返さない (SVG の図の文字)


@dataclass
class Picture:
    x: float
    y: float
    w: float
    h: float
    path: Path
    alt: str = ""
    crop: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # 左上右下 (割合)
    name: str = "図"


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float
    color: str
    name: str = "線"


@dataclass
class Cell:
    paras: list[Para]
    fill: str | None
    pad_x: float
    pad_y: float


@dataclass
class TableShape:
    x: float
    y: float
    col_widths: list[float]
    row_heights: list[float]
    rows: list[list[Cell]]
    name: str = "表"


@dataclass
class Geom:
    """SVG の図の 1 つの図形 (四角・円・線・自由な形)。位置はスライドの px

    kind は "rect" / "roundRect" / "ellipse" / "line" (直線のコネクタ) / "path" (フリーフォーム)。
    path の点は (x, y) からの相対位置で、命令は "M" "L" "C" "Q" "Z"。
    """

    kind: str
    x: float
    y: float
    w: float
    h: float
    fill: str | None = None
    stroke: str | None = None
    stroke_w: float = 1.0
    dash: bool = False
    fill_alpha: float = 1.0
    stroke_alpha: float = 1.0
    radius: float = 0.0  # roundRect の角の丸み (px)
    path: list[tuple[str, list[tuple[float, float]]]] = field(default_factory=list)
    flip_h: bool = False  # line: 右から左へ引く線
    flip_v: bool = False  # line: 下から上へ引く線
    head: str | None = None  # 始点の矢印の大きさ ("sm" / "med" / "lg")
    tail: str | None = None  # 終点の矢印の大きさ
    glue_start: tuple[Geom, int] | None = None  # 線の始点をつなぐ図形と接続点の番号
    glue_end: tuple[Geom, int] | None = None
    paras: list[Para] = field(default_factory=list)  # 図形の中の文字
    align: str = "ctr"
    inset_l: float = 0.0
    inset_r: float = 0.0
    inset_t: float = 0.0
    wrap: bool = True
    name: str = "図形"


@dataclass
class Drawing:
    """SVG の図を PowerPoint の図形に置き換えたもの (1 つのグループ)"""

    x: float
    y: float
    w: float
    h: float
    items: list[Geom | TextBox]
    alt: str = ""
    name: str = "図"


Shape = TextBox | Picture | Rect | TableShape | Drawing


@dataclass
class PageShapes:
    background: str
    shapes: list[Shape]


# ---- 文字のスタイル ----


@dataclass
class Context:
    """本文の文字の基準 (ふつうは 26px / 行の高さ 1.5、center は 34px / 1.6)"""

    size: float = 26.0
    line: float = 1.5
    color: str = TEXT
    center: bool = False  # 中央ぞろえ (center / table / image クラス)
    flex: bool = False  # 余白を重ねない (display: flex の中)
    layout: str = ""  # center / table / image など


NORMAL = Context()


def heading_style(level: int, ctx: Context) -> tuple[float, str, float, float]:
    """見出しの (文字の大きさ, 色, 上の余白, 下の余白)"""
    if level == 3 or level == 2:
        if ctx.layout == "center":
            return 44.0, TEXT, 0.0, 22.0
        if ctx.layout in ("table", "image"):
            return 30.0, TEXT, 0.0, 12.0
        return 30.0, TEXT, 24.0, 9.0
    size = {1: 1.6, 4: 1.05, 5: 1.0, 6: 0.9}[level] * ctx.size
    color = ctx.color  # 見出しも本文と同じ黒 (theme.css)
    return size, color, 24.0, 16.0


def block_margins(block: Block, ctx: Context) -> tuple[float, float]:
    if isinstance(block, Heading):
        _, _, top, bottom = heading_style(block.level, ctx)
        return top, bottom
    if isinstance(block, ListBlock):
        return 0.2 * ctx.size, 0.2 * ctx.size
    if isinstance(block, Paragraph):
        if ctx.layout == "center":
            return 0.3 * ctx.size, 0.3 * ctx.size
        if ctx.layout == "image":
            return 0.5 * 22, 0.0  # 画像の下の説明
        return 0.0, 16.0
    return 0.0, 16.0  # 表・引用・コード・画像


def para_style(block: Block, ctx: Context) -> tuple[float, float, str]:
    """段落の (文字の大きさ, 行の高さ, 色)"""
    if isinstance(block, Paragraph) and ctx.layout == "image":
        return 22.0, 33.0, MUTED
    return ctx.size, ctx.size * ctx.line, ctx.color


BULLETS = [("•", BULLET_FONT), ("o", "Courier New"), ("§", "Wingdings")]
NUMBERS = ["arabicPeriod", "romanLcPeriod", "alphaLcPeriod"]


def list_paras(
    lst: ListBlock,
    ctx: Context,
    width: float,
    left: float = 0.0,
    depth: int = 0,
    ol_depth: int = 0,
    first: bool = True,
) -> tuple[list[Para], float]:
    """リストを段落にする。(段落, 高さ) を返す

    left はリストの左端 (テキストボックスの左端から)。記号は CSS の outside の位置に
    合わせて、本文の左端 (left + 2em) から少し左に置く。
    """
    size, line = ctx.size, ctx.size * ctx.line
    indent_w = 2 * size
    paras: list[Para] = []
    height = 0.0
    for n, item in enumerate(lst.items):
        gap = 0.0 if (n == 0) else 0.25 * size
        mar_l = left + indent_w
        avail = max(width - mar_l, size)
        para = Para(
            item.runs,
            size,
            line,
            ctx.color,
            align="l",
            space_before=gap,
            mar_l=mar_l,
            level=min(depth, 8),
        )
        if lst.ordered:
            para.autonum = NUMBERS[min(ol_depth, len(NUMBERS) - 1)]
            para.start = lst.start
            para.indent = -1.08 * size
        else:
            para.bullet, para.bullet_font = BULLETS[min(depth, len(BULLETS) - 1)]
            para.indent = -0.9 * size
        paras.append(para)
        height += gap + count_lines(item.runs, size, avail) * line
        for child in item.children:
            sub, h = list_paras(
                child,
                ctx,
                width,
                mar_l,
                depth + 1,
                ol_depth + (1 if child.ordered else 0),
            )
            paras.extend(sub)
            height += h
    return paras, height


def list_width(lst: ListBlock, ctx: Context, left: float = 0.0) -> float:
    """リストの最大の幅 (center で真ん中に置くのに使う)"""
    width = 0.0
    for item in lst.items:
        text_w = max_content_width(item.runs, ctx.size) * WIDTH_SLACK
        width = max(width, left + 2 * ctx.size + text_w)
        for child in item.children:
            width = max(width, list_width(child, ctx, left + 2 * ctx.size))
    return width


def text_paras(block: Block, ctx: Context, width: float) -> tuple[list[Para], float]:
    """文字のブロック (見出し・段落・リスト) を段落にする。(段落, 高さ) を返す"""
    align = "ctr" if ctx.center else "l"
    if isinstance(block, Heading):
        size, color, _, _ = heading_style(block.level, ctx)
        line = size * 1.25
        # h1 は下に余白 (padding-bottom: 0.3em) があるので、段落の後の間隔にする
        after = 0.3 * size if block.level == 1 else 0.0
        para = Para(
            block.runs, size, line, color, bold=True, align=align, space_after=after
        )
        return [para], count_lines(block.runs, size, width) * line + after
    if isinstance(block, ListBlock):
        left = 0.0
        if ctx.center:
            lw = min(list_width(block, ctx), width)
            left = max((width - lw) / 2, 0.0)
        return list_paras(block, ctx, width, left, ol_depth=0)
    if isinstance(block, (Paragraph, Quote)):
        size, line, color = para_style(block, ctx)
        para = Para(block.runs, size, line, color, align=align)
        return [para], count_lines(block.runs, size, width) * line
    raise TypeError(block)


def is_text(block: Block) -> bool:
    return isinstance(block, (Heading, Paragraph, ListBlock))


# ---- 画像 ----


def image_size(path: Path) -> tuple[float, float]:
    """画像の大きさ (px)。分からなければ 4:3"""
    try:
        data = path.read_bytes()
    except OSError:
        return 800.0, 600.0
    return image_size_from_bytes(data, path.suffix.lower())


def image_size_from_bytes(data: bytes, suffix: str) -> tuple[float, float]:
    try:
        if suffix == ".svg":
            return svg_size(data)
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", data[16:24])
            return float(w), float(h)
        if data[:6] in (b"GIF87a", b"GIF89a"):
            w, h = struct.unpack("<HH", data[6:10])
            return float(w), float(h)
        if data[:2] == b"\xff\xd8":
            return jpeg_size(data)
    except (struct.error, ValueError, ElementTree.ParseError):
        pass
    return 800.0, 600.0


def css_length(value: str | None) -> float | None:
    if not value:
        return None
    m = re.match(r"^\s*([0-9.]+)\s*(px|pt|in|cm|mm)?\s*$", value)
    if not m:
        return None
    scale = {"pt": 96 / 72, "in": 96, "cm": 96 / 2.54, "mm": 96 / 25.4}.get(
        m.group(2) or "px", 1.0
    )
    return float(m.group(1)) * scale


def svg_size(data: bytes) -> tuple[float, float]:
    root = ElementTree.fromstring(data)
    w = css_length(root.get("width"))
    h = css_length(root.get("height"))
    box = root.get("viewBox")
    if box:
        parts = [float(v) for v in re.split(r"[\s,]+", box.strip())]
        if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
            if w and not h:
                h = w * parts[3] / parts[2]
            elif h and not w:
                w = h * parts[2] / parts[3]
            elif not w and not h:
                w, h = parts[2], parts[3]
    return (w or 300.0), (h or 150.0)


def jpeg_size(data: bytes) -> tuple[float, float]:
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        length = struct.unpack(">H", data[i + 2 : i + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", data[i + 5 : i + 9])
            return float(w), float(h)
        i += 2 + length
    raise ValueError("JPEG の大きさが分かりません")


def contain(
    x: float, y: float, w: float, h: float, iw: float, ih: float, upscale: bool = False
) -> tuple[float, float, float, float]:
    """(x, y, w, h) の中に縦横比を保って収め、真ん中に置いた位置 (object-fit: contain)"""
    scale = min(w / iw, h / ih)
    if not upscale:
        scale = min(scale, 1.0)
    nw, nh = iw * scale, ih * scale
    return x + (w - nw) / 2, y + (h - nh) / 2, nw, nh


def cover_crop(
    iw: float, ih: float, w: float, h: float
) -> tuple[float, float, float, float]:
    """(w, h) をすき間なく埋めるように切り取る割合 (background-size: cover)"""
    if iw / ih > w / h:
        cut = (1 - (w / h) / (iw / ih)) / 2
        return cut, 0.0, cut, 0.0
    cut = (1 - (iw / ih) / (w / h)) / 2
    return 0.0, cut, 0.0, cut


# ---- SVG の図を PowerPoint の図形にする ----
#
# SKILL.md の決まりで作った図 (rect・circle・ellipse・line・polyline・polygon・path・text と g) は、
# 画像ではなく PowerPoint の図形・矢印・文字の 1 つのグループにして、そのまま編集できるようにする。
# 箱の中の文字は箱の図形の文字に、矢印 (marker-end / marker-start、または線の先の三角形) は
# 線の矢じりにし、箱の辺の真ん中に届く直線は箱につなぐ (箱を動かすと線がついてくる)。
# 置き換えられないもの (<image>・グラデーション・回転など) があれば、図全体を画像のまま入れる。

SVG_TEXT_LINE = 1.2  # 図の文字の行の高さ (文字の大きさに対する割合)
# 行の上端からベースラインまで (文字の大きさに対する割合)。メイリオ (ascent 1.0577、
# descent 0.4423) を行の高さ 1.2 の真ん中に置いたときの値
SVG_TEXT_BASELINE = SVG_TEXT_LINE / 2 + (1.0577 - 0.4423) / 2
SVG_GLUE_DISTANCE = 8.0  # 線の端と箱の辺の真ん中がこれより近ければつなぐ (px)
SVG_INHERITED = (
    "fill",
    "stroke",
    "stroke-width",
    "stroke-dasharray",
    "fill-opacity",
    "stroke-opacity",
    "font-size",
    "font-weight",
    "font-style",
    "text-anchor",
    "dominant-baseline",
    "marker-start",
    "marker-end",
    "color",
)
# SVG (CSS) の色の名前。<span> の色 (SPAN_COLORS) とは別に、ブラウザと同じ値にする
SVG_COLORS = {
    "black": "000000",
    "white": "FFFFFF",
    "red": "FF0000",
    "green": "008000",
    "blue": "0000FF",
    "yellow": "FFFF00",
    "orange": "FFA500",
    "purple": "800080",
    "gray": "808080",
    "grey": "808080",
    "silver": "C0C0C0",
    "lightgray": "D3D3D3",
    "lightgrey": "D3D3D3",
    "darkgray": "A9A9A9",
    "darkgrey": "A9A9A9",
    "navy": "000080",
    "darkblue": "00008B",
    "steelblue": "4682B4",
    "skyblue": "87CEEB",
    "lightblue": "ADD8E6",
    "teal": "008080",
    "darkgreen": "006400",
    "maroon": "800000",
    "darkred": "8B0000",
}
SVG_NUMBER_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
SVG_PATH_TOKEN_RE = re.compile(
    r"([MmLlHhVvCcSsQqTtAaZz])|([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)"
)

Point = tuple[float, float]
Transform = tuple[
    float, float, float, float
]  # (sx, sy, tx, ty): (x, y) -> (sx*x+tx, sy*y+ty)


class SvgError(Exception):
    """PowerPoint の図形にできない SVG (理由を持つ)"""


@dataclass
class SvgText:
    """図の 1 行の文字 (位置はスライドの px、y はベースライン)"""

    x: float
    y: float
    anchor: str  # "start" / "middle" / "end"
    size: float
    color: str
    runs: list[Run]

    @property
    def width(self) -> float:
        return max_content_width(self.runs, self.size) * WIDTH_SLACK

    @property
    def left(self) -> float:
        offset = {"middle": 0.5, "end": 1.0}.get(self.anchor, 0.0)
        return self.x - self.width * offset

    @property
    def top(self) -> float:
        return self.y - SVG_TEXT_BASELINE * self.size

    def para(self, align: str) -> Para:
        return Para(
            self.runs, self.size, self.size * SVG_TEXT_LINE, self.color, align=align
        )


def svg_tag(el: ElementTree.Element) -> str:
    return el.tag.rsplit("}", 1)[-1] if isinstance(el.tag, str) else ""


def svg_numbers(value: str | None) -> list[float]:
    return [float(v) for v in SVG_NUMBER_RE.findall(value or "")]


def svg_length(value: str | None, default: float = 0.0, em: float = 16.0) -> float:
    if value is None or not value.strip():
        return default
    value = value.strip()
    if value.endswith("%"):
        raise SvgError("% の長さ")
    if value.endswith("em"):
        return float(value[:-2]) * em
    length = css_length(value)
    if length is None:
        raise SvgError(f"長さ {value}")
    return length


def svg_attrs(el: ElementTree.Element) -> dict[str, str]:
    """要素の属性 (style="fill: ..." の中も属性として読む)"""
    attrs = {k.rsplit("}", 1)[-1]: v for k, v in el.attrib.items()}
    for item in attrs.pop("style", "").split(";"):
        if ":" in item:
            key, value = item.split(":", 1)
            attrs[key.strip()] = value.strip()
    return attrs


def svg_transform(value: str | None) -> Transform:
    """transform を (sx, sy, tx, ty) にする。回転・斜めの変形は図形にできない"""
    sx, sy, tx, ty = 1.0, 1.0, 0.0, 0.0
    if not value:
        return sx, sy, tx, ty
    items = re.findall(r"([a-zA-Z]+)\s*\(([^)]*)\)", value)
    for name, args in reversed(items):  # 右に書いたものから順に当てる
        nums = svg_numbers(args)
        if name == "translate" and nums:
            ax, ay, bx, by = 1.0, 1.0, nums[0], nums[1] if len(nums) > 1 else 0.0
        elif name == "scale" and nums:
            ax, ay, bx, by = nums[0], nums[1] if len(nums) > 1 else nums[0], 0.0, 0.0
        elif name == "matrix" and len(nums) == 6 and nums[1] == 0 and nums[2] == 0:
            ax, ay, bx, by = nums[0], nums[3], nums[4], nums[5]
        elif name == "rotate" and nums and nums[0] % 360 == 0:
            continue
        else:
            raise SvgError(f"変形 {name}")
        sx, sy, tx, ty = ax * sx, ay * sy, ax * tx + bx, ay * ty + by
    if sx <= 0 or sy <= 0:
        raise SvgError("反転・0 倍の変形")
    return sx, sy, tx, ty


def compose(outer: Transform, inner: Transform) -> Transform:
    osx, osy, otx, oty = outer
    isx, isy, itx, ity = inner
    return osx * isx, osy * isy, osx * itx + otx, osy * ity + oty


def apply(tf: Transform, p: Point) -> Point:
    return tf[0] * p[0] + tf[2], tf[1] * p[1] + tf[3]


def svg_color(value: str, current: str | None = None) -> str | None:
    value = value.strip().lower()
    if value in ("none", "transparent"):
        return None
    if value.startswith("url("):
        raise SvgError("グラデーション・模様の塗り")
    if value == "currentcolor":
        return svg_color(current or "black")
    if value.startswith("#") or value.startswith("rgb"):
        color = parse_color(value)
    else:
        color = SVG_COLORS.get(value)
    if color is None:
        raise SvgError(f"色 {value}")
    return color


def arc_to_cubics(
    p0: Point, rx: float, ry: float, angle: float, large: bool, sweep: bool, p1: Point
) -> list[list[Point]]:
    """円弧 (path の A) を 3 次ベジェ曲線に分ける (SVG 仕様の F.6 の方法)"""
    if p0 == p1:
        return []
    if rx == 0 or ry == 0:
        return [[p0, p1, p1]]
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(angle % 360)
    cos, sin = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1 = cos * dx + sin * dy
    y1 = -sin * dx + cos * dy
    lam = (x1 / rx) ** 2 + (y1 / ry) ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    coef = math.sqrt(max(num, 0) / den) if den else 0.0
    if large == sweep:
        coef = -coef
    cx1, cy1 = coef * rx * y1 / ry, -coef * ry * x1 / rx
    cx = cos * cx1 - sin * cy1 + (p0[0] + p1[0]) / 2
    cy = sin * cx1 + cos * cy1 + (p0[1] + p1[1]) / 2

    def ang(ux: float, uy: float, vx: float, vy: float) -> float:
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)

    t1 = ang(1, 0, (x1 - cx1) / rx, (y1 - cy1) / ry)
    dt = ang((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    n = max(1, math.ceil(abs(dt) / (math.pi / 2) - 1e-9))
    step = dt / n
    k = 4 / 3 * math.tan(step / 4)

    def point(t: float, d: float = 0.0) -> Point:
        if d:
            ex, ey = -rx * math.sin(t), ry * math.cos(t)
        else:
            ex, ey = rx * math.cos(t), ry * math.sin(t)
        return cos * ex - sin * ey + (0 if d else cx), sin * ex + cos * ey + (
            0 if d else cy
        )

    curves = []
    for i in range(n):
        a, b = t1 + i * step, t1 + (i + 1) * step
        pa, pb = point(a), point(b)
        da, db = point(a, 1), point(b, 1)
        c1 = (pa[0] + k * da[0], pa[1] + k * da[1])
        c2 = (pb[0] - k * db[0], pb[1] - k * db[1])
        curves.append([c1, c2, pb])
    curves[-1][2] = p1
    return curves


def parse_path(d: str) -> list[tuple[str, list[Point]]]:
    """path の d を、絶対座標の "M" "L" "C" "Q" "Z" の並びにする"""
    tokens = SVG_PATH_TOKEN_RE.findall(d)
    out: list[tuple[str, list[Point]]] = []
    i = 0
    cmd = ""
    cur: Point = (0.0, 0.0)
    start: Point = (0.0, 0.0)
    last_ctrl: Point | None = None
    last_kind = ""

    def nums(n: int) -> list[float]:
        nonlocal i
        values = []
        for _ in range(n):
            if i >= len(tokens) or not tokens[i][1]:
                raise SvgError("path の書き方")
            values.append(float(tokens[i][1]))
            i += 1
        return values

    while i < len(tokens):
        if tokens[i][0]:
            cmd = tokens[i][0]
            i += 1
        elif not cmd:
            raise SvgError("path の書き方")
        rel = cmd.islower()
        c = cmd.upper()
        ox, oy = cur if rel else (0.0, 0.0)
        if c == "Z":
            out.append(("Z", []))
            cur = start
            last_ctrl, last_kind = None, "Z"
            continue
        if c == "M":
            x, y = nums(2)
            cur = start = (ox + x, oy + y)
            out.append(("M", [cur]))
            cmd = "l" if rel else "L"  # M の後に続く数は L
            last_ctrl, last_kind = None, "M"
        elif c in ("L", "H", "V"):
            if c == "L":
                x, y = nums(2)
                cur = (ox + x, oy + y)
            elif c == "H":
                (x,) = nums(1)
                cur = (ox + x if rel else x, cur[1])
            else:
                (y,) = nums(1)
                cur = (cur[0], oy + y if rel else y)
            out.append(("L", [cur]))
            last_ctrl, last_kind = None, "L"
        elif c in ("C", "S"):
            if c == "C":
                x1, y1, x2, y2, x, y = nums(6)
                c1 = (ox + x1, oy + y1)
            else:
                x2, y2, x, y = nums(4)
                c1 = (
                    (2 * cur[0] - last_ctrl[0], 2 * cur[1] - last_ctrl[1])
                    if last_ctrl and last_kind == "C"
                    else cur
                )
            c2 = (ox + x2, oy + y2)
            cur = (ox + x, oy + y)
            out.append(("C", [c1, c2, cur]))
            last_ctrl, last_kind = c2, "C"
        elif c in ("Q", "T"):
            if c == "Q":
                x1, y1, x, y = nums(4)
                q = (ox + x1, oy + y1)
            else:
                x, y = nums(2)
                q = (
                    (2 * cur[0] - last_ctrl[0], 2 * cur[1] - last_ctrl[1])
                    if last_ctrl and last_kind == "Q"
                    else cur
                )
            cur = (ox + x, oy + y)
            out.append(("Q", [q, cur]))
            last_ctrl, last_kind = q, "Q"
        elif c == "A":
            rx, ry, angle, large, sweep, x, y = nums(7)
            end = (ox + x, oy + y)
            for curve in arc_to_cubics(
                cur, rx, ry, angle, bool(large), bool(sweep), end
            ):
                out.append(("C", curve))
            cur = end
            last_ctrl, last_kind = None, "A"
        else:
            raise SvgError(f"path の {cmd}")
    return out


def arrow_size(ratio: float) -> str:
    """矢じりの大きさ (線の太さの何倍か) を PowerPoint の大きさにする"""
    if ratio < 2.5:
        return "sm"
    if ratio < 4:
        return "med"
    return "lg"


class SvgConverter:
    """SVG を、スライドの (x, y, w, h) に置いた図形の一覧にする"""

    def __init__(
        self, root: ElementTree.Element, box: tuple[float, float, float, float]
    ):
        if svg_tag(root) != "svg":
            raise SvgError("<svg> ではない")
        x, y, w, h = box
        vb = svg_numbers(root.get("viewBox"))
        if len(vb) == 4 and vb[2] > 0 and vb[3] > 0:
            minx, miny, vw, vh = vb
        else:
            minx, miny = 0.0, 0.0
            vw, vh = svg_size(ElementTree.tostring(root))
        scale = min(w / vw, h / vh)  # preserveAspectRatio は既定 (xMidYMid meet)
        ox = x + (w - vw * scale) / 2 - minx * scale
        oy = y + (h - vh * scale) / 2 - miny * scale
        self.root = root
        self.base: Transform = (scale, scale, ox, oy)
        self.canvas = (x, y, w, h)
        self.markers: dict[str, tuple[float, bool]] = {}  # id -> (幅, 線の太さが単位か)
        self.items: list[Geom | SvgText] = []
        self.texts: dict[int, list[SvgText]] = {}  # 図形 (id) -> 中の文字

    # -- 読む --

    def convert(self) -> list[Geom | TextBox]:
        for marker in self.root.iter():
            if svg_tag(marker) == "marker" and marker.get("id"):
                width = svg_length(marker.get("markerWidth"), 3.0)
                stroke_units = marker.get("markerUnits") != "userSpaceOnUse"
                self.markers[marker.get("id", "")] = (width, stroke_units)
        self.walk(self.root, {}, self.base)
        self.merge_arrowheads()
        self.place_texts()
        result: list[Geom | TextBox] = []
        for item in self.items:
            if isinstance(item, SvgText):
                result.append(self.free_text(item))
            else:
                self.finish(item)
                result.append(item)
        for item in result:
            if isinstance(item, Geom) and item.kind == "line":
                self.glue(item, result)
        return result

    def walk(
        self, el: ElementTree.Element, inherited: dict[str, str], tf: Transform
    ) -> None:
        tag = svg_tag(el)
        if tag in ("title", "desc", "metadata", "defs", "marker", ""):
            return
        attrs = dict(inherited)
        own = svg_attrs(el)
        opacity = float(attrs.get("_opacity", "1")) * float(own.pop("opacity", "1"))
        attrs.update(own)
        attrs["_opacity"] = str(opacity)
        if attrs.get("display") == "none" or attrs.get("visibility") == "hidden":
            return
        if el is not self.root:
            tf = compose(tf, svg_transform(own.get("transform")))
        if tag in ("svg", "g", "a") and (tag != "svg" or el is self.root):
            inherit = {
                k: v for k, v in attrs.items() if k in SVG_INHERITED or k == "_opacity"
            }
            for child in el:
                self.walk(child, inherit, tf)
        elif tag in ("rect", "circle", "ellipse"):
            self.box(tag, attrs, tf)
        elif tag in ("line", "polyline", "polygon", "path"):
            self.lines(tag, attrs, tf)
        elif tag == "text":
            self.text(el, attrs, tf)
        else:
            raise SvgError(f"<{tag}>")

    def style(self, attrs: dict[str, str], tf: Transform, fill_default: str) -> Geom:
        current = attrs.get("color")
        opacity = float(attrs.get("_opacity", "1"))
        stroke = svg_color(attrs.get("stroke", "none"), current)
        dash = attrs.get("stroke-dasharray", "none").strip()
        return Geom(
            "rect",
            0,
            0,
            0,
            0,
            fill=svg_color(attrs.get("fill", fill_default), current),
            stroke=stroke,
            stroke_w=svg_length(attrs.get("stroke-width"), 1.0) * (tf[0] + tf[1]) / 2,
            dash=dash not in ("none", "") and any(svg_numbers(dash)),
            fill_alpha=opacity * float(attrs.get("fill-opacity", "1")),
            stroke_alpha=opacity * float(attrs.get("stroke-opacity", "1")),
        )

    def box(self, tag: str, attrs: dict[str, str], tf: Transform) -> None:
        g = self.style(attrs, tf, "black")
        if tag == "rect":
            x, y = svg_length(attrs.get("x")), svg_length(attrs.get("y"))
            w, h = svg_length(attrs.get("width")), svg_length(attrs.get("height"))
            rx = attrs.get("rx") or attrs.get("ry")
            radius = svg_length(rx) if rx else 0.0
            g.kind = "roundRect" if radius > 0 else "rect"
            g.name = "四角形"
        else:
            cx, cy = svg_length(attrs.get("cx")), svg_length(attrs.get("cy"))
            if tag == "circle":
                rx = ry = svg_length(attrs.get("r"))
            else:
                rx, ry = svg_length(attrs.get("rx")), svg_length(attrs.get("ry"))
            x, y, w, h = cx - rx, cy - ry, 2 * rx, 2 * ry
            radius = 0.0
            g.kind = "ellipse"
            g.name = "円"
        if w <= 0 or h <= 0:
            return
        g.x, g.y = apply(tf, (x, y))
        g.w, g.h = w * tf[0], h * tf[1]
        g.radius = min(radius * (tf[0] + tf[1]) / 2, g.w / 2, g.h / 2)
        self.items.append(g)

    def lines(self, tag: str, attrs: dict[str, str], tf: Transform) -> None:
        if tag == "line":
            pts = [
                (svg_length(attrs.get("x1")), svg_length(attrs.get("y1"))),
                (svg_length(attrs.get("x2")), svg_length(attrs.get("y2"))),
            ]
            cmds = [("M", [pts[0]]), ("L", [pts[1]])]
        elif tag in ("polyline", "polygon"):
            values = svg_numbers(attrs.get("points"))
            pts = list(zip(values[0::2], values[1::2]))
            if len(pts) < 2:
                return
            cmds = [("M", [pts[0]])] + [("L", [p]) for p in pts[1:]]
            if tag == "polygon":
                cmds.append(("Z", []))
        else:
            cmds = parse_path(attrs.get("d", ""))
            if not cmds:
                return
        closed = any(c == "Z" for c, _ in cmds)
        g = self.style(attrs, tf, "none" if tag == "line" else "black")
        g.kind = "line" if tag == "line" else "path"
        g.name = "線" if tag in ("line", "polyline") or not closed else "図形"
        g.path = [(c, [apply(tf, p) for p in ps]) for c, ps in cmds]
        if tag == "line":
            g.fill = None
        sw_svg = svg_length(attrs.get("stroke-width"), 1.0)
        for key, end in (("marker-start", "head"), ("marker-end", "tail")):
            m = re.match(r"\s*url\(\s*['\"]?#([^'\")\s]+)", attrs.get(key, ""))
            if m and m.group(1) in self.markers and g.stroke:
                width, stroke_units = self.markers[m.group(1)]
                ratio = width if stroke_units else width / max(sw_svg, 0.1)
                setattr(g, end, arrow_size(ratio))
        self.items.append(g)

    def text(
        self, el: ElementTree.Element, attrs: dict[str, str], tf: Transform
    ) -> None:
        scale = (tf[0] + tf[1]) / 2
        lines: list[SvgText] = []

        def size_of(a: dict[str, str]) -> float:
            return svg_length(a.get("font-size"), 16.0)

        def new_line(a: dict[str, str], x: float, y: float) -> SvgText:
            size = size_of(a)
            baseline = a.get("dominant-baseline", "").strip()
            shift = {"middle": 0.35, "central": 0.35, "hanging": 0.8}.get(baseline, 0.0)
            px, py = apply(tf, (x, y + shift * size))
            color = svg_color(a.get("fill", "black"), a.get("color")) or TEXT
            line = SvgText(
                px, py, a.get("text-anchor", "start"), size * scale, color, []
            )
            lines.append(line)
            return line

        def add(s: str | None, a: dict[str, str]) -> None:
            if not s:
                return
            s = re.sub(r"\s+", " ", s)
            weight = a.get("font-weight", "normal").strip()
            bold = weight in ("bold", "bolder") or (
                weight.isdigit() and int(weight) >= 600
            )
            color = svg_color(a.get("fill", "black"), a.get("color"))
            line = lines[-1]
            line.runs.append(
                Run(
                    s,
                    bold=bold,
                    italic=a.get("font-style") == "italic",
                    color=None if color == line.color else color,
                )
            )

        def visit(node: ElementTree.Element, a: dict[str, str]) -> None:
            add(node.text, a)
            for child in node:
                tag = svg_tag(child)
                if tag in ("title", "desc", ""):
                    pass
                elif tag == "tspan":
                    ca = dict(a)
                    ca.update(svg_attrs(child))
                    if any(k in child.attrib for k in ("x", "y", "dy")):
                        last = lines[-1]
                        x0 = (last.x - tf[2]) / tf[0]
                        y0 = (last.y - tf[3]) / tf[1]
                        x = svg_numbers(child.get("x"))[:1] or [x0]
                        y = svg_numbers(child.get("y"))[:1] or [y0]
                        dy = svg_length(child.get("dy"), 0.0, size_of(ca))
                        new_line(ca, x[0], y[0] + dy)
                        lines[-1].anchor = ca.get(
                            "text-anchor", a.get("text-anchor", "start")
                        )
                    visit(child, ca)
                else:
                    raise SvgError(f"<text> の中の <{tag}>")
                add(child.tail, a)

        x = (svg_numbers(attrs.get("x")) or [0.0])[0]
        y = (svg_numbers(attrs.get("y")) or [0.0])[0]
        new_line(attrs, x, y)
        visit(el, attrs)
        for line in lines:
            while line.runs and not line.runs[0].text.strip():
                line.runs.pop(0)
            while line.runs and not line.runs[-1].text.strip():
                line.runs.pop()
            if line.runs:
                line.runs[0].text = line.runs[0].text.lstrip()
                line.runs[-1].text = line.runs[-1].text.rstrip()
                self.items.append(line)

    # -- 整える --

    def merge_arrowheads(self) -> None:
        """線の端に置いた三角形 (polygon) を、線の矢じりにする"""
        lines = [
            g
            for g in self.items
            if isinstance(g, Geom)
            and g.stroke
            and g.path
            and not any(c == "Z" for c, _ in g.path)
        ]
        for tri in list(self.items):
            if not (isinstance(tri, Geom) and tri.kind == "path" and tri.fill):
                continue
            pts = [ps[0] for c, ps in tri.path if c in ("M", "L")]
            if len(pts) == 4 and pts[0] == pts[3]:
                pts = pts[:3]
            if len(pts) != 3 or [c for c, _ in tri.path][-1] != "Z":
                continue
            if any(c not in ("M", "L", "Z") for c, _ in tri.path):
                continue
            # 先端は、いちばん短い辺の向かいの頂点
            edges = [
                (math.dist(pts[(i + 1) % 3], pts[(i + 2) % 3]), i) for i in range(3)
            ]
            base_len, tip_i = min(edges)
            tip = pts[tip_i]
            a, b = pts[(tip_i + 1) % 3], pts[(tip_i + 2) % 3]
            base = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            length = math.dist(tip, base)
            if length == 0:
                continue
            ux, uy = (tip[0] - base[0]) / length, (tip[1] - base[1]) / length
            for line in lines:
                if line.stroke != tri.fill:
                    continue
                for end in ("tail", "head"):
                    if getattr(line, end):
                        continue
                    i_end, i_prev = (-1, -2) if end == "tail" else (0, 1)
                    if len(line.path) < 2 or line.path[i_end][0] not in ("M", "L"):
                        continue
                    if end == "head" and line.path[1][0] not in ("L",):
                        continue
                    p = line.path[i_end][1][-1]
                    q = line.path[i_prev][1][-1]
                    seg = math.dist(p, q)
                    if seg == 0 or math.dist(p, base) > 0.6 * length + line.stroke_w:
                        continue
                    if ((p[0] - q[0]) * ux + (p[1] - q[1]) * uy) / seg < 0.95:
                        continue
                    line.path[i_end] = (line.path[i_end][0], [tip])
                    setattr(line, end, arrow_size(base_len / max(line.stroke_w, 0.1)))
                    self.items.remove(tri)
                    break
                else:
                    continue
                break

    def place_texts(self) -> None:
        """箱 (四角・円・閉じた形) の中にある文字を、その図形の文字にする"""
        cx, cy, cw, ch = self.canvas
        for item in list(self.items):
            if not isinstance(item, SvgText):
                continue
            mid_x = item.left + item.width / 2
            mid_y = item.y - 0.35 * item.size
            best: Geom | None = None
            for g in self.items[: self.items.index(item)]:
                if not isinstance(g, Geom) or g.kind == "line":
                    continue
                if g.kind == "path" and not any(c == "Z" for c, _ in g.path):
                    continue
                if not (g.fill or g.stroke):
                    continue
                gx, gy, gw, gh = self.bbox(g)
                if gw * gh >= 0.9 * cw * ch:  # 図全体の背景には付けない
                    continue
                if not (gx <= mid_x <= gx + gw and gy <= mid_y <= gy + gh):
                    continue
                if item.width > gw + 1:
                    continue
                others = self.texts.get(id(g), [])
                if others and (
                    others[0].anchor != item.anchor or abs(others[0].x - item.x) > 1
                ):
                    continue
                if best is None or gw * gh < self.bbox(best)[2] * self.bbox(best)[3]:
                    best = g
            if best is not None:
                self.texts.setdefault(id(best), []).append(item)
                self.items.remove(item)

    @staticmethod
    def bbox(g: Geom) -> tuple[float, float, float, float]:
        if g.kind in ("line", "path"):
            pts = [p for _, ps in g.path for p in ps]
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
        return g.x, g.y, g.w, g.h

    def finish(self, g: Geom) -> None:
        """図形の位置を決め、中の文字を段落にする"""
        if g.kind in ("line", "path"):
            g.x, g.y, g.w, g.h = self.bbox(g)
            if g.kind == "line":
                (x1, y1), (x2, y2) = g.path[0][1][0], g.path[-1][1][-1]
                g.flip_h, g.flip_v = x2 < x1, y2 < y1
            g.path = [(c, [(p[0] - g.x, p[1] - g.y) for p in ps]) for c, ps in g.path]
        lines = sorted(self.texts.get(id(g), []), key=lambda t: t.y)
        if not lines:
            return
        first = lines[0]
        g.align = {"middle": "ctr", "end": "r"}.get(first.anchor, "l")
        if g.align == "ctr":
            d = first.x - (g.x + g.w / 2)
            g.inset_l, g.inset_r = max(2 * d, 0.0), max(-2 * d, 0.0)
        elif g.align == "l":
            g.inset_l = first.x - g.x
        else:
            g.inset_r = g.x + g.w - first.x
        g.inset_t = first.top - g.y
        bottom: float | None = None  # 前の行の下端
        for line in lines:
            para = line.para(g.align)
            top = line.top
            if bottom is not None:
                para.space_before = max(top - bottom, 0.0)
                top = max(top, bottom)
            bottom = top + para.line
            g.paras.append(para)
        inner = g.w - g.inset_l - g.inset_r
        g.wrap = all(t.width <= inner for t in lines)

    def free_text(self, t: SvgText) -> TextBox:
        align = {"middle": "ctr", "end": "r"}.get(t.anchor, "l")
        return TextBox(
            t.left,
            t.top,
            t.width,
            t.size * SVG_TEXT_LINE,
            [t.para(align)],
            wrap=False,
            name="テキスト",
        )

    @staticmethod
    def glue(line: Geom, items: list[Geom | TextBox]) -> None:
        """直線の端が箱の辺の真ん中にあれば、その箱につなぐ"""
        start = (
            line.x + (line.w if line.flip_h else 0),
            line.y + (line.h if line.flip_v else 0),
        )
        end = (
            line.x + (0 if line.flip_h else line.w),
            line.y + (0 if line.flip_v else line.h),
        )
        for attr, p in (("glue_start", start), ("glue_end", end)):
            best = None
            for g in items:
                if not isinstance(g, Geom) or g.kind not in ("rect", "roundRect"):
                    continue
                sites = [
                    (g.x + g.w / 2, g.y),  # 0: 上
                    (g.x, g.y + g.h / 2),  # 1: 左
                    (g.x + g.w / 2, g.y + g.h),  # 2: 下
                    (g.x + g.w, g.y + g.h / 2),  # 3: 右
                ]
                for idx, site in enumerate(sites):
                    dist = math.dist(p, site)
                    if dist <= SVG_GLUE_DISTANCE and (best is None or dist < best[0]):
                        best = (dist, g, idx)
            if best:
                setattr(line, attr, (best[1], best[2]))


def svg_drawing(
    data: bytes, x: float, y: float, w: float, h: float, alt: str = ""
) -> Drawing:
    """SVG を、PowerPoint の図形のグループにする。できなければ SvgError"""
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as e:
        raise SvgError("SVG として読めない") from e
    try:
        items = SvgConverter(root, (x, y, w, h)).convert()
    except (ValueError, ZeroDivisionError) as e:
        raise SvgError(f"数の書き方 ({e})") from e
    if not items:
        raise SvgError("図形が無い")
    return Drawing(x, y, w, h, items, alt)


# ---- レイアウト ----


class Layout:
    """1 枚のスライドを図形に並べる"""

    def __init__(self, base_dir: Path, warn: list[str]) -> None:
        self.base_dir = base_dir
        self.warn = warn

    def resolve(self, src: str) -> Path | None:
        if re.match(r"^[a-z][a-z0-9+.-]*://", src, re.I):
            self.warn.append(f"Web 上の画像は使えません (省きました): {src}")
            return None
        path = Path(unescape(src))
        if not path.is_absolute():
            path = self.base_dir / path
        if not path.is_file():
            self.warn.append(f"画像がありません (省きました): {src}")
            return None
        if path.suffix.lower() not in ACCEPTED_IMAGES:
            self.warn.append(f"この形式の画像は使えません (省きました): {src}")
            return None
        return path

    def figure(
        self, path: Path, x: float, y: float, w: float, h: float, alt: str
    ) -> Shape:
        """本文の画像。SVG の図は PowerPoint の図形にし、できなければ画像のまま入れる"""
        # 仮の画像 (placeholder.svg) は差し替えるものなので、画像のまま (「図の変更」で替えられる)
        if path.suffix.lower() == ".svg" and path.name != "placeholder.svg":
            try:
                return svg_drawing(path.read_bytes(), x, y, w, h, alt)
            except SvgError as e:
                self.warn.append(
                    f"SVG の図を PowerPoint の図形にできないので、画像のまま入れました"
                    f" ({e}): {path.name}"
                )
        return Picture(x, y, w, h, path, alt)

    # -- 本文の流し込み --

    def flow(
        self,
        blocks: list[Block],
        x: float,
        y: float,
        w: float,
        ctx: Context,
        shapes: list[Shape],
        first_margin: bool = True,
    ) -> float:
        """ブロックを上から順に並べ (余白は重ねる)、下端の y を返す"""
        box: TextBox | None = None
        prev_bottom: float | None = None
        for index, block in enumerate(blocks):
            top, bottom = block_margins(block, ctx)
            if index == 0 and not first_margin:
                top = 0.0
            gap = top if prev_bottom is None else max(prev_bottom, top)
            block_y = y + gap
            if is_text(block):
                paras, h = text_paras(block, ctx, w)
                if box is None:
                    box = TextBox(x, block_y, w, 0.0, [])
                    shapes.append(box)
                else:
                    paras[0].space_before += gap
                box.paras.extend(paras)
                y = block_y + h
                box.h = y - box.y
            else:
                box = None
                y = block_y + self.place_block(block, x, block_y, w, ctx, shapes)
            prev_bottom = bottom
        return y

    def place_block(
        self,
        block: Block,
        x: float,
        y: float,
        w: float,
        ctx: Context,
        shapes: list[Shape],
    ) -> float:
        """文字以外のブロック (表・画像・引用・コード) を置き、高さを返す"""
        if isinstance(block, Table):
            table = self.table(block, x, y, w, ctx)
            shapes.append(table)
            return sum(table.row_heights) + 1
        if isinstance(block, Image):
            path = self.resolve(block.src)
            if not path:
                return 0.0
            iw, ih = image_size(path)
            scale = min(1.0, w / iw)
            pw, ph = iw * scale, ih * scale
            px = x + (w - pw) / 2 if ctx.center else x
            shapes.append(self.figure(path, px, y, pw, ph, block.alt))
            return ph + 0.335 * ctx.size  # 画像は文字の行に乗るので、下に少しすき間
        if isinstance(block, Quote):
            size, line = ctx.size, ctx.size * ctx.line
            bar, pad = 0.25 * size, size
            h = count_lines(block.runs, size, w - bar - pad) * line
            shapes.append(Rect(x, y, round(bar), h, BORDER, "引用の線"))
            para = Para(block.runs, size, line, QUOTE_COLOR)
            shapes.append(
                TextBox(x + bar + pad, y, w - bar - pad, h, [para], name="引用")
            )
            return h
        if isinstance(block, Code):
            size = ctx.size * 0.85
            line = size * 1.15
            runs = []
            for n, text in enumerate(block.text.split("\n")):
                if n:
                    runs.append(Run("\n"))
                runs.append(Run(text or " ", code=True))
            lines = block.text.count("\n") + 1
            h = lines * line + 32 + 2
            para = Para(runs, size, line, CODE_TEXT)
            shapes.append(
                TextBox(
                    x,
                    y,
                    w,
                    h,
                    [para],
                    inset_t=17,
                    inset_b=17,
                    inset_l=17,
                    inset_r=17,
                    fill=ZEBRA,
                    border=BORDER,
                    name="コード",
                )
            )
            return h
        raise TypeError(block)

    # -- 表 --

    def table(
        self, tbl: Table, x: float, y: float, avail: float, ctx: Context
    ) -> TableShape:
        full = ctx.layout == "table"
        size = 24.0 if full else 22.0
        line = size * 1.5
        pad_x, pad_y = 32.0, (12.0 if full else 8.0)
        rows = [tbl.header, *tbl.rows]
        ncol = len(tbl.header)
        max_w = [0.0] * ncol
        min_w = [0.0] * ncol
        for r, row in enumerate(rows):
            for c, runs in enumerate(row):
                runs = header_runs(runs) if r == 0 else runs
                text_w = max_content_width(runs, size) * WIDTH_SLACK
                max_w[c] = max(max_w[c], text_w + 2 * pad_x + 1)
                min_w[c] = max(min_w[c], min_content_width(runs, size) + 2 * pad_x + 1)
        widths = table_widths(min_w, max_w, avail, full)
        heights = []
        shape_rows = []
        for r, row in enumerate(rows):
            lines = 1
            cells = []
            for c, runs in enumerate(row):
                header = r == 0
                align = tbl.aligns[c] or ("ctr" if header else "l")
                para = Para(
                    runs,
                    size,
                    line,
                    WHITE if header else TEXT,
                    bold=header,
                    align=align,
                )
                measured = header_runs(runs) if header else runs
                inner = widths[c] - 2 * pad_x - 1
                lines = max(lines, count_lines(measured, size, inner))
                fill = ACCENT if header else (ZEBRA if r % 2 == 0 else WHITE)
                cells.append(Cell([para], fill, pad_x, pad_y))
            heights.append(lines * line + 2 * pad_y + 1)
            shape_rows.append(cells)
        return TableShape(x + 0.5, y + 0.5, widths, heights, shape_rows)

    # -- スライド --

    def slide(self, slide: Slide, number: int, total: int) -> PageShapes:
        if slide.cls.split() and "cover" in slide.cls.split():
            return self.cover(slide)
        shapes: list[Shape] = []
        for bg in slide.backgrounds:
            self.background(bg, shapes)
        line_w = SLIDE_W - 2 * LINE_INSET
        shapes.append(
            Rect(LINE_INSET, HEADER_H - LINE_W, line_w, LINE_W, LINE, "ヘッダーの線")
        )
        shapes.append(
            Rect(LINE_INSET, SLIDE_H - FOOTER_H, line_w, LINE_W, LINE, "フッターの線")
        )
        blocks = list(slide.blocks)
        title_index = next(
            (
                i
                for i, b in enumerate(blocks)
                if isinstance(b, Heading) and b.level == 2
            ),
            None,
        )
        after_title = False
        if title_index is not None:
            title = blocks.pop(title_index)
            assert isinstance(title, Heading)
            after_title = title_index == 0
            para = Para(title.runs, 36, 45, TEXT, bold=True)
            shapes.append(
                TextBox(
                    SIDE, 0, BODY_W, HEADER_H, [para], anchor="ctr", name="タイトル"
                )
            )
        layout = next(
            (
                c
                for c in slide.cls.split()
                if c
                in ("cols", "image-right", "image-left", "table", "image", "center")
            ),
            "",
        )
        # 小見出しがヘッダーのすぐ下 (または本文の最初) なら上の余白を付けない
        first_margin = not (
            blocks and isinstance(blocks[0], Heading) and blocks[0].level == 3
        )
        del after_title
        if layout == "cols":
            self.cols(blocks, shapes, first_margin)
        elif layout in ("image-right", "image-left"):
            self.side_image(blocks, layout, shapes, first_margin)
        elif layout == "center":
            self.center(blocks, shapes)
        elif layout in ("table", "image"):
            self.centered_column(blocks, layout, shapes)
        else:
            self.flow(blocks, BODY_LEFT, BODY_TOP, BODY_W, NORMAL, shapes, first_margin)
        self.footer(slide, number, total, shapes)
        return PageShapes(WHITE, shapes)

    def background(self, bg: Image, shapes: list[Shape]) -> None:
        path = self.resolve(bg.src)
        if not path:
            return
        iw, ih = image_size(path)
        words = bg.alt.split()
        if "contain" in words or "fit" in words:
            x, y, w, h = contain(0, 0, SLIDE_W, SLIDE_H, iw, ih, upscale=True)
            shapes.append(Picture(x, y, w, h, path, name="背景"))
        else:
            crop = cover_crop(iw, ih, SLIDE_W, SLIDE_H)
            shapes.append(Picture(0, 0, SLIDE_W, SLIDE_H, path, crop=crop, name="背景"))

    def cover(self, slide: Slide) -> PageShapes:
        shapes: list[Shape] = []
        for bg in slide.backgrounds:
            self.background(bg, shapes)
        blocks = list(slide.blocks)
        width = SLIDE_W - 2 * COVER_SIDE
        title_index = next(
            (
                i
                for i, b in enumerate(blocks)
                if isinstance(b, Heading) and b.level == 1
            ),
            None,
        )
        if title_index is not None:
            title = blocks.pop(title_index)
            assert isinstance(title, Heading)
            para = Para(title.runs, 56, 72.8, TEXT, bold=True)
            bottom = COVER_TITLE_H - COVER_TITLE_PAD - COVER_LINE
            shapes.append(
                TextBox(
                    COVER_SIDE, 0, width, bottom, [para], anchor="b", name="タイトル"
                )
            )
        shapes.append(
            Rect(
                COVER_SIDE,
                COVER_TITLE_H - COVER_LINE,
                width,
                COVER_LINE,
                TEXT,
                "表紙の線",
            )
        )
        y = COVER_TITLE_H + 28
        paras: list[Para] = []
        for n, block in enumerate(blocks):
            if isinstance(block, Paragraph):
                para = Para(block.runs, 28, 47.6, TEXT)
                paras.append(para)
            elif is_text(block):
                ctx = Context(28, 1.7, TEXT)
                sub, _ = text_paras(block, ctx, width)
                for p in sub:
                    p.color = TEXT
                paras.extend(sub)
        if paras:
            height = SLIDE_H - y
            shapes.append(
                TextBox(COVER_SIDE, y, width, height, paras, name="部署名と日付")
            )
        return PageShapes(WHITE, shapes)

    def footer(
        self, slide: Slide, number: int, total: int, shapes: list[Shape]
    ) -> None:
        top = SLIDE_H - FOOTER_H
        if slide.paginate:
            para = Para(
                [Run(str(number)), Run(f" / {total}")],
                PAGE_NUMBER_SIZE,
                PAGE_NUMBER_SIZE * 1.5,
                MUTED,
                field_slidenum=True,
            )
            shapes.append(
                TextBox(
                    SIDE, top, 400, FOOTER_H, [para], anchor="ctr", name="ページ番号"
                )
            )
        if not slide.footer:
            return
        images = re.findall(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?\s*\)", slide.footer)
        if images:
            right = SLIDE_W - SIDE
            for alt, src in reversed(images):
                path = self.resolve(src)
                if not path:
                    continue
                iw, ih = image_size(path)
                w = LOGO_H * iw / ih
                right -= w
                shapes.append(
                    Picture(
                        right,
                        top + (FOOTER_H - LOGO_H) / 2,
                        w,
                        LOGO_H,
                        path,
                        alt,
                        name="ロゴ",
                    )
                )
            return
        para = Para(parse_inline(slide.footer), 18, 27, MUTED, align="r")
        shapes.append(
            TextBox(SIDE, top, BODY_W, FOOTER_H, [para], anchor="ctr", name="フッター")
        )

    # -- 本文のレイアウト --

    def cols(
        self, blocks: list[Block], shapes: list[Shape], first_margin: bool
    ) -> None:
        h3 = [
            i for i, b in enumerate(blocks) if isinstance(b, Heading) and b.level == 3
        ]
        split = h3[1] if len(h3) >= 2 else len(blocks)
        col_w = (BODY_W - COLS_GAP) / 2
        self.flow(
            blocks[:split], BODY_LEFT, BODY_TOP, col_w, NORMAL, shapes, first_margin
        )
        if blocks[split:]:
            x = BODY_LEFT + col_w + COLS_GAP
            self.flow(blocks[split:], x, BODY_TOP, col_w, NORMAL, shapes, False)

    def side_image(
        self, blocks: list[Block], layout: str, shapes: list[Shape], first_margin: bool
    ) -> None:
        images = [i for i, b in enumerate(blocks) if isinstance(b, Image)]
        text_w = SLIDE_W - 2 * SIDE - IMAGE_W - IMAGE_GAP
        if layout == "image-right":
            text_x, image_x = BODY_LEFT, SLIDE_W - SIDE - IMAGE_W
        else:
            text_x, image_x = SIDE + IMAGE_W + IMAGE_GAP, SIDE
        if images:
            image = blocks.pop(images[-1])
            assert isinstance(image, Image)
            path = self.resolve(image.src)
            if path:
                iw, ih = image_size(path)
                box = contain(
                    image_x, BODY_TOP, IMAGE_W, BODY_BOTTOM - BODY_TOP, iw, ih
                )
                shapes.append(self.figure(path, *box, image.alt))
        self.flow(blocks, text_x, BODY_TOP, text_w, NORMAL, shapes, first_margin)

    def center(self, blocks: list[Block], shapes: list[Shape]) -> None:
        """文字を大きく、上下左右の真ん中に置く (1 つのテキストボックスで、上下の中央ぞろえ)"""
        ctx = Context(34, 1.6, TEXT, center=True, flex=True, layout="center")
        texts = [b for b in blocks if is_text(b)]
        others = [b for b in blocks if not is_text(b)]
        paras: list[Para] = []
        prev_bottom = 0.0
        first_top = 0.0
        for n, block in enumerate(texts):
            top, bottom = block_margins(block, ctx)
            sub, _ = text_paras(block, ctx, BODY_W)
            if n == 0:
                first_top = top
            else:
                sub[0].space_before += prev_bottom + top
            paras.extend(sub)
            prev_bottom = bottom
        if paras:
            shapes.append(
                TextBox(
                    BODY_LEFT,
                    BODY_TOP,
                    BODY_W,
                    BODY_BOTTOM - BODY_TOP,
                    paras,
                    anchor="ctr",
                    inset_t=first_top,
                    name="本文",
                )
            )
        if others:  # 表や画像は、文字の下に並べる (このレイアウトでは使わない想定)
            self.flow(others, BODY_LEFT, BODY_TOP, BODY_W, NORMAL, shapes)

    def centered_column(
        self, blocks: list[Block], layout: str, shapes: list[Shape]
    ) -> None:
        """table / image: 本文を縦に並べ、全体を上下の真ん中に置く (余白は重ねない)"""
        ctx = Context(26, 1.5, TEXT, center=True, flex=True, layout=layout)
        avail = BODY_BOTTOM - BODY_TOP
        items: list[tuple[Block, float, float, float]] = []  # (ブロック, 上, 高さ, 下)
        image_index = None
        for n, block in enumerate(blocks):
            top, bottom = block_margins(block, ctx)
            if n == len(blocks) - 1:
                bottom = 0.0  # 最後の要素の下の余白は無し
            if isinstance(block, Image) and layout == "image" and image_index is None:
                image_index = n
                top = bottom = 0.0
                h = 0.0
            elif is_text(block):
                _, h = text_paras(block, ctx, BODY_W)
            elif isinstance(block, Table):
                tbl = self.table(block, 0, 0, BODY_W, ctx)
                h = sum(tbl.row_heights) + 1
            else:
                h = self.place_block(block, 0, 0, BODY_W, ctx, [])
            items.append((block, top, h, bottom))
        used = sum(t + h + b for _, t, h, b in items)
        if image_index is not None:
            block, t, _, b = items[image_index]
            items[image_index] = (block, t, max(avail - used, 0.0), b)
            used = avail
        y = BODY_TOP + (avail - used) / 2
        for block, top, h, bottom in items:
            y += top
            if isinstance(block, Image) and layout == "image":
                path = self.resolve(block.src)
                if path:
                    iw, ih = image_size(path)
                    box = contain(BODY_LEFT, y, BODY_W, h, iw, ih)
                    shapes.append(self.figure(path, *box, block.alt))
            elif is_text(block):
                paras, _ = text_paras(block, ctx, BODY_W)
                shapes.append(TextBox(BODY_LEFT, y, BODY_W, h, paras))
            elif isinstance(block, Table):
                shapes.append(self.table(block, BODY_LEFT, y, BODY_W, ctx))
            else:
                self.place_block(block, BODY_LEFT, y, BODY_W, ctx, shapes)
            y += h + bottom


def header_runs(runs: list[Run]) -> list[Run]:
    """見出しの行 (th) は太字"""
    return [replace(r, bold=True) for r in runs]


def table_widths(
    min_w: list[float], max_w: list[float], avail: float, full: bool
) -> list[float]:
    """表の列の幅 (ブラウザの table-layout: auto と同じ考え方)

    - 全部の列が最大の幅で収まるとき: そのまま (full なら幅いっぱいまで比例して広げる)
    - 収まらないとき: 最小の幅から、残りを (最大 - 最小) に比例して配る
    """
    total_max, total_min = sum(max_w), sum(min_w)
    if total_max <= avail:
        if full and total_max > 0:
            return [w * avail / total_max for w in max_w]
        return list(max_w)
    if total_min >= avail:
        return list(min_w)
    extra = (avail - total_min) / (total_max - total_min)
    return [lo + (hi - lo) * extra for lo, hi in zip(min_w, max_w)]


# ---- PPTX (Office Open XML) を書く ----

NS = (
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
)
XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
SVG_EXT_URI = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"
SVG_NS = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"
SLIDENUM_FIELD_ID = "{B6F15528-21DE-4FAA-801E-634DDDAF4B2B}"
INVALID_XML_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def emu(px: float) -> int:
    return round(px * EMU_PER_PX)


def pt100(px: float) -> int:
    """px を 1/100 pt にする (文字の大きさ・行の高さ・段落の間隔)"""
    return round(px * 75)


def esc(text: str) -> str:
    text = INVALID_XML_RE.sub("", text)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def png_1x1() -> bytes:
    """SVG を表示できないソフト向けの代わりの画像 (透明な 1x1 の PNG)"""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00\x00\x00\x00")
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


class Package:
    """PPTX の中のファイル (部品) を集めて zip に書く"""

    def __init__(self) -> None:
        self.parts: dict[str, bytes] = {}
        self.overrides: dict[str, str] = {}
        self.media: dict[Path, str] = {}  # 画像のパス -> 部品名
        self.fallback: str | None = None

    def add(
        self, name: str, data: str | bytes, content_type: str | None = None
    ) -> None:
        self.parts[name] = data.encode("utf-8") if isinstance(data, str) else data
        if content_type:
            self.overrides[name] = content_type

    def add_media(self, path: Path) -> str:
        if path not in self.media:
            ext = path.suffix.lower()
            ext = ".jpeg" if ext == ".jpg" else ext
            name = f"ppt/media/image{len(self.media) + 1}{ext}"
            self.add(name, path.read_bytes())
            self.media[path] = name
        return self.media[path]

    def fallback_png(self) -> str:
        if not self.fallback:
            self.fallback = "ppt/media/fallback.png"
            self.add(self.fallback, png_1x1())
        return self.fallback

    def content_types(self) -> str:
        defaults = {
            "rels": "application/vnd.openxmlformats-package.relationships+xml",
            "xml": "application/xml",
        }
        for name in self.parts:
            ext = name.rsplit(".", 1)[-1]
            if ext in ("svg", "png", "jpeg", "gif"):
                defaults[ext] = ACCEPTED_IMAGES["." + ext]
        items = [
            f'<Default Extension="{e}" ContentType="{t}"/>' for e, t in defaults.items()
        ]
        items += [
            f'<Override PartName="/{n}" ContentType="{t}"/>'
            for n, t in self.overrides.items()
        ]
        return (
            XML_HEAD
            + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            + "".join(items)
            + "</Types>"
        )

    def write(self, path: Path) -> None:
        tmp = path.with_name(path.name + ".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", self.content_types())
            for name, data in self.parts.items():
                zf.writestr(name, data)
        tmp.replace(path)


def rels_xml(rels: list[tuple[str, str, str]]) -> str:
    """(Id, 種類, 行き先) の一覧を .rels の XML にする"""
    items = []
    for rid, kind, target in rels:
        mode = ' TargetMode="External"' if kind == "hyperlink" else ""
        kind_uri = kind if kind.startswith("http") else f"{DOC_REL}/{kind}"
        items.append(
            f'<Relationship Id="{rid}" Type="{kind_uri}" Target="{esc(target)}"{mode}/>'
        )
    return (
        XML_HEAD
        + f'<Relationships xmlns="{REL_NS}">'
        + "".join(items)
        + "</Relationships>"
    )


class SlideWriter:
    """1 枚のスライドの XML を作る"""

    def __init__(self, package: Package) -> None:
        self.package = package
        self.rels: list[tuple[str, str, str]] = [
            ("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml")
        ]
        self.next_id = 2

    def rel(self, kind: str, target: str) -> str:
        for rid, k, t in self.rels:
            if k == kind and t == target:
                return rid
        rid = f"rId{len(self.rels) + 1}"
        self.rels.append((rid, kind, target))
        return rid

    def shape_id(self) -> int:
        self.next_id += 1
        return self.next_id - 1

    def xml(self, page: PageShapes) -> str:
        body = "".join(self.shape(s) for s in page.shapes)
        return (
            XML_HEAD
            + f"<p:sld {NS}><p:cSld>"
            + f'<p:bg><p:bgPr><a:solidFill><a:srgbClr val="{page.background}"/></a:solidFill>'
            + "<a:effectLst/></p:bgPr></p:bg>"
            + '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            + '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
            + '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            + body
            + "</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"
        )

    def shape(self, s: Shape) -> str:
        if isinstance(s, TextBox):
            return self.textbox(s)
        if isinstance(s, Picture):
            return self.picture(s)
        if isinstance(s, Rect):
            return self.rect(s)
        if isinstance(s, Drawing):
            return self.drawing(s)
        return self.table(s)

    @staticmethod
    def xfrm(x: float, y: float, w: float, h: float, tag: str = "a:xfrm") -> str:
        return (
            f'<{tag}><a:off x="{emu(x)}" y="{emu(y)}"/>'
            f'<a:ext cx="{max(emu(w), 0)}" cy="{max(emu(h), 0)}"/></{tag}>'
        )

    def rect(self, s: Rect) -> str:
        sid = self.shape_id()
        return (
            f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="{esc(s.name)} {sid}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            f"<p:spPr>{self.xfrm(s.x, s.y, s.w, s.h)}"
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
            f'<a:solidFill><a:srgbClr val="{s.color}"/></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr>'
            "</p:sp>"
        )

    def picture(self, s: Picture) -> str:
        sid = self.shape_id()
        media = self.package.add_media(s.path)
        target = "../" + media.removeprefix("ppt/")
        if media.endswith(".svg"):
            png = self.rel(
                "image", "../" + self.package.fallback_png().removeprefix("ppt/")
            )
            svg = self.rel("image", target)
            blip = (
                f'<a:blip r:embed="{png}"><a:extLst><a:ext uri="{SVG_EXT_URI}">'
                f'<asvg:svgBlip xmlns:asvg="{SVG_NS}" r:embed="{svg}"/></a:ext></a:extLst></a:blip>'
            )
        else:
            blip = f'<a:blip r:embed="{self.rel("image", target)}"/>'
        left, top, right, bottom = (round(v * 100000) for v in s.crop)
        crop = (
            f'<a:srcRect l="{left}" t="{top}" r="{right}" b="{bottom}"/>'
            if any((left, top, right, bottom))
            else ""
        )
        return (
            f'<p:pic><p:nvPicPr><p:cNvPr id="{sid}" name="{esc(s.name)} {sid}" descr="{esc(s.alt)}"/>'
            '<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
            f"<p:blipFill>{blip}{crop}<a:stretch><a:fillRect/></a:stretch></p:blipFill>"
            f"<p:spPr>{self.xfrm(s.x, s.y, s.w, s.h)}"
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
        )

    def textbox(self, s: TextBox) -> str:
        sid = self.shape_id()
        fill = (
            f'<a:solidFill><a:srgbClr val="{s.fill}"/></a:solidFill>'
            if s.fill
            else "<a:noFill/>"
        )
        line = (
            f'<a:ln w="{EMU_PER_PX}"><a:solidFill><a:srgbClr val="{s.border}"/></a:solidFill></a:ln>'
            if s.border
            else ""
        )
        body = self.body_pr(
            s.wrap, s.inset_l, s.inset_t, s.inset_r, s.inset_b, s.anchor
        )
        return (
            f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="{esc(s.name)} {sid}"/>'
            '<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f"<p:spPr>{self.xfrm(s.x, s.y, s.w, s.h)}"
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>{fill}{line}</p:spPr>'
            f"<p:txBody>{body}{''.join(self.paragraph(p) for p in s.paras)}</p:txBody></p:sp>"
        )

    @staticmethod
    def body_pr(
        wrap: bool, left: float, top: float, right: float, bottom: float, anchor: str
    ) -> str:
        return (
            f'<a:bodyPr wrap="{"square" if wrap else "none"}" lIns="{emu(left)}" '
            f'tIns="{emu(top)}" rIns="{emu(right)}" bIns="{emu(bottom)}" '
            f'anchor="{anchor}" rtlCol="0"><a:noAutofit/></a:bodyPr><a:lstStyle/>'
        )

    # -- SVG の図 (図形のグループ) --

    def drawing(self, d: Drawing) -> str:
        sid = self.shape_id()
        ids = {id(g): self.shape_id() for g in d.items if isinstance(g, Geom)}
        children = "".join(
            self.geom(g, ids) if isinstance(g, Geom) else self.textbox(g)
            for g in d.items
        )
        boxes = [(g.x, g.y, g.x + g.w, g.y + g.h) for g in d.items]
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
        off = f'<a:off x="{emu(x0)}" y="{emu(y0)}"/>'
        ext = f'<a:ext cx="{emu(x1 - x0)}" cy="{emu(y1 - y0)}"/>'
        ch = off.replace("a:off", "a:chOff") + ext.replace("a:ext", "a:chExt")
        return (
            f'<p:grpSp><p:nvGrpSpPr><p:cNvPr id="{sid}" name="{esc(d.name)} {sid}" '
            f'descr="{esc(d.alt)}"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            f"<p:grpSpPr><a:xfrm>{off}{ext}{ch}</a:xfrm></p:grpSpPr>"
            f"{children}</p:grpSp>"
        )

    @staticmethod
    def color(value: str, alpha: float = 1.0) -> str:
        inner = f'<a:alpha val="{round(alpha * 100000)}"/>' if alpha < 1 else ""
        return (
            f'<a:solidFill><a:srgbClr val="{value}">{inner}</a:srgbClr></a:solidFill>'
        )

    def line_props(self, g: Geom) -> str:
        if not g.stroke:
            return "<a:ln><a:noFill/></a:ln>"
        dash = "dash" if g.dash else "solid"
        ends = "".join(
            f'<a:{tag} type="triangle" w="{size}" len="{size}"/>'
            for tag, size in (("headEnd", g.head), ("tailEnd", g.tail))
            if size
        )
        return (
            f'<a:ln w="{emu(g.stroke_w)}" cap="flat">'
            f"{self.color(g.stroke, g.stroke_alpha)}"
            f'<a:prstDash val="{dash}"/><a:miter lim="800000"/>{ends}</a:ln>'
        )

    def geom(self, g: Geom, ids: dict[int, int]) -> str:
        sid = ids[id(g)]
        name = f'<p:cNvPr id="{sid}" name="{esc(g.name)} {sid}"/>'
        line = self.line_props(g)
        if g.kind == "line":
            glue = "".join(
                f'<a:{tag} id="{ids[id(target[0])]}" idx="{target[1]}"/>'
                for tag, target in (("stCxn", g.glue_start), ("endCxn", g.glue_end))
                if target and id(target[0]) in ids
            )
            flips = (' flipH="1"' if g.flip_h else "") + (
                ' flipV="1"' if g.flip_v else ""
            )
            xfrm = self.xfrm(g.x, g.y, g.w, g.h).replace("<a:xfrm>", f"<a:xfrm{flips}>")
            return (
                f"<p:cxnSp><p:nvCxnSpPr>{name}<p:cNvCxnSpPr>{glue}</p:cNvCxnSpPr><p:nvPr/>"
                f"</p:nvCxnSpPr><p:spPr>{xfrm}"
                '<a:prstGeom prst="straightConnector1"><a:avLst/></a:prstGeom>'
                f"<a:noFill/>{line}</p:spPr></p:cxnSp>"
            )
        if g.kind == "path":
            geometry = self.cust_geom(g)
        elif g.kind == "roundRect":
            adj = min(round(g.radius / max(min(g.w, g.h), 0.01) * 100000), 50000)
            geometry = (
                '<a:prstGeom prst="roundRect"><a:avLst>'
                f'<a:gd name="adj" fmla="val {adj}"/></a:avLst></a:prstGeom>'
            )
        else:
            geometry = f'<a:prstGeom prst="{g.kind}"><a:avLst/></a:prstGeom>'
        fill = self.color(g.fill, g.fill_alpha) if g.fill else "<a:noFill/>"
        if g.paras:
            body = self.body_pr(g.wrap, g.inset_l, g.inset_t, g.inset_r, 0, "t")
            paras = "".join(self.paragraph(p) for p in g.paras)
        else:  # 文字を入力したときは、真ん中に図の文字と同じ書式で入る
            body = self.body_pr(True, 0, 0, 0, 0, "ctr")
            empty = Para([], 20, 24, TEXT, align="ctr")
            end = self.run_props(empty, Run(""), tag="a:endParaRPr")
            paras = f'<a:p><a:pPr algn="ctr"/>{end}</a:p>'
        return (
            f"<p:sp><p:nvSpPr>{name}<p:cNvSpPr/><p:nvPr/></p:nvSpPr>"
            f"<p:spPr>{self.xfrm(g.x, g.y, g.w, g.h)}{geometry}{fill}{line}</p:spPr>"
            f"<p:txBody>{body}{paras}</p:txBody></p:sp>"
        )

    @staticmethod
    def cust_geom(g: Geom) -> str:
        tags = {"M": "a:moveTo", "L": "a:lnTo", "C": "a:cubicBezTo", "Q": "a:quadBezTo"}
        cmds = []
        for c, pts in g.path:
            if c == "Z":
                cmds.append("<a:close/>")
                continue
            inner = "".join(f'<a:pt x="{emu(x)}" y="{emu(y)}"/>' for x, y in pts)
            cmds.append(f"<{tags[c]}>{inner}</{tags[c]}>")
        fill = "" if g.fill else ' fill="none"'
        return (
            "<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/>"
            '<a:rect l="l" t="t" r="r" b="b"/><a:pathLst>'
            f'<a:path w="{max(emu(g.w), 1)}" h="{max(emu(g.h), 1)}"{fill}>'
            f"{''.join(cmds)}</a:path></a:pathLst></a:custGeom>"
        )

    def table(self, s: TableShape) -> str:
        sid = self.shape_id()
        grid = "".join(f'<a:gridCol w="{emu(w)}"/>' for w in s.col_widths)
        rows = []
        for cells, h in zip(s.rows, s.row_heights):
            tcs = []
            for cell in cells:
                border = "".join(
                    f'<a:{side} w="{EMU_PER_PX}" cap="flat" cmpd="sng" algn="ctr">'
                    f'<a:solidFill><a:srgbClr val="{BORDER}"/></a:solidFill>'
                    '<a:prstDash val="solid"/></a:' + side + ">"
                    for side in ("lnL", "lnR", "lnT", "lnB")
                )
                fill = (
                    f'<a:solidFill><a:srgbClr val="{cell.fill}"/></a:solidFill>'
                    if cell.fill
                    else "<a:noFill/>"
                )
                paras = "".join(self.paragraph(p) for p in cell.paras)
                tcs.append(
                    f"<a:tc><a:txBody><a:bodyPr/><a:lstStyle/>{paras}</a:txBody>"
                    f'<a:tcPr marL="{emu(cell.pad_x)}" marR="{emu(cell.pad_x)}" '
                    f'marT="{emu(cell.pad_y)}" marB="{emu(cell.pad_y)}" anchor="ctr">'
                    f"{border}{fill}</a:tcPr></a:tc>"
                )
            rows.append(f'<a:tr h="{emu(h)}">{"".join(tcs)}</a:tr>')
        w, h = sum(s.col_widths), sum(s.row_heights)
        return (
            f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{sid}" name="{esc(s.name)} {sid}"/>'
            '<p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr><p:nvPr/>'
            f"</p:nvGraphicFramePr>{self.xfrm(s.x, s.y, w, h, 'p:xfrm')}"
            '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table">'
            f'<a:tbl><a:tblPr firstRow="1" bandRow="1"/><a:tblGrid>{grid}</a:tblGrid>'
            f"{''.join(rows)}</a:tbl></a:graphicData></a:graphic></p:graphicFrame>"
        )

    def paragraph(self, p: Para) -> str:
        attrs = f' algn="{p.align}"'
        if p.level:
            attrs = f' lvl="{p.level}"' + attrs
        if p.mar_l or p.indent:
            attrs = f' marL="{emu(p.mar_l)}" indent="{emu(p.indent)}"' + attrs
        props = (
            f'<a:lnSpc><a:spcPts val="{pt100(p.line)}"/></a:lnSpc>'
            f'<a:spcBef><a:spcPts val="{pt100(p.space_before)}"/></a:spcBef>'
            f'<a:spcAft><a:spcPts val="{pt100(p.space_after)}"/></a:spcAft>'
        )
        if p.autonum:
            props += f'<a:buFont typeface="+mj-lt"/><a:buAutoNum type="{p.autonum}"'
            props += f' startAt="{p.start}"/>' if p.start != 1 else "/>"
        elif p.bullet:
            props += f'<a:buFont typeface="{esc(p.bullet_font)}"/><a:buChar char="{esc(p.bullet)}"/>'
        else:
            props += "<a:buNone/>"
        runs = []
        for n, run in enumerate(p.runs):
            if run.text == "\n":
                runs.append(f"<a:br>{self.run_props(p, run)}</a:br>")
            elif n == 0 and p.field_slidenum:
                runs.append(
                    f'<a:fld id="{SLIDENUM_FIELD_ID}" type="slidenum">'
                    f"{self.run_props(p, run)}<a:t>{esc(run.text)}</a:t></a:fld>"
                )
            else:
                runs.append(
                    f"<a:r>{self.run_props(p, run)}<a:t>{esc(run.text)}</a:t></a:r>"
                )
        end = self.run_props(p, Run(""), tag="a:endParaRPr")
        return f"<a:p><a:pPr{attrs}>{props}</a:pPr>{''.join(runs)}{end}</a:p>"

    def run_props(self, p: Para, run: Run, tag: str = "a:rPr") -> str:
        size = p.size * (0.85 if run.code else 1)
        attrs = f'lang="ja-JP" altLang="en-US" sz="{pt100(size)}"'
        if p.bold or run.bold:
            attrs += ' b="1"'
        if p.italic or run.italic:
            attrs += ' i="1"'
        if run.underline:
            attrs += ' u="sng"'
        if run.strike:
            attrs += ' strike="sngStrike"'
        attrs += ' dirty="0"'
        color = run.color or p.color  # <span class="red"> などの色
        inner = f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
        if run.code:
            inner += f'<a:highlight><a:srgbClr val="{INLINE_CODE_BG}"/></a:highlight>'
            fonts = (MONO_FONT, EA_FONT, MONO_FONT)
        else:
            fonts = (LATIN_FONT, EA_FONT, LATIN_FONT)
        inner += (
            f'<a:latin typeface="{fonts[0]}"/><a:ea typeface="{fonts[1]}"/>'
            f'<a:cs typeface="{fonts[2]}"/>'
        )
        if run.link and tag == "a:rPr":
            rid = self.rel("hyperlink", run.link)
            inner += f'<a:hlinkClick r:id="{rid}"/>'
        return f"<{tag} {attrs}>{inner}</{tag}>"


def theme_xml() -> str:
    colors = [
        ("dk1", '<a:sysClr val="windowText" lastClr="000000"/>'),
        ("lt1", f'<a:sysClr val="window" lastClr="{WHITE}"/>'),
        ("dk2", f'<a:srgbClr val="{TEXT}"/>'),
        ("lt2", '<a:srgbClr val="E7E6E6"/>'),
        ("accent1", f'<a:srgbClr val="{ACCENT}"/>'),
        ("accent2", '<a:srgbClr val="2C6CB0"/>'),
        ("accent3", '<a:srgbClr val="A5A5A5"/>'),
        ("accent4", '<a:srgbClr val="FFC000"/>'),
        ("accent5", '<a:srgbClr val="5B9BD5"/>'),
        ("accent6", '<a:srgbClr val="70AD47"/>'),
        ("hlink", '<a:srgbClr val="0563C1"/>'),
        ("folHlink", '<a:srgbClr val="954F72"/>'),
    ]
    clr = "".join(f"<a:{n}>{v}</a:{n}>" for n, v in colors)
    font = (
        f'<a:latin typeface="{LATIN_FONT}"/><a:ea typeface="{EA_FONT}"/><a:cs typeface="{LATIN_FONT}"/>'
        f'<a:font script="Jpan" typeface="{EA_FONT}"/>'
    )
    solid = '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    lines = "".join(
        f'<a:ln w="{w}" cap="flat" cmpd="sng" algn="ctr">{solid}<a:prstDash val="solid"/></a:ln>'
        for w in (6350, 12700, 19050)
    )
    return (
        XML_HEAD
        + '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="kit-slides">'
        + f'<a:themeElements><a:clrScheme name="kit-slides">{clr}</a:clrScheme>'
        + f'<a:fontScheme name="kit-slides"><a:majorFont>{font}</a:majorFont>'
        + f"<a:minorFont>{font}</a:minorFont></a:fontScheme>"
        + '<a:fmtScheme name="kit-slides">'
        + f"<a:fillStyleLst>{solid * 3}</a:fillStyleLst>"
        + f"<a:lnStyleLst>{lines}</a:lnStyleLst>"
        + "<a:effectStyleLst>"
        + "<a:effectStyle><a:effectLst/></a:effectStyle>" * 3
        + "</a:effectStyleLst>"
        + f"<a:bgFillStyleLst>{solid * 3}</a:bgFillStyleLst>"
        + "</a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>"
    )


def text_levels() -> str:
    """既定の文字の書式 (PowerPoint で新しく打った文字に使われる)"""
    return "".join(
        f'<a:lvl{n}pPr marL="{(n - 1) * 457200}" algn="l"><a:defRPr sz="1950">'
        f'<a:solidFill><a:srgbClr val="{TEXT}"/></a:solidFill>'
        '<a:latin typeface="+mn-lt"/><a:ea typeface="+mn-ea"/><a:cs typeface="+mn-cs"/>'
        f"</a:defRPr></a:lvl{n}pPr>"
        for n in range(1, 4)
    )


def text_style(tag: str) -> str:
    return f"<p:{tag}>{text_levels()}</p:{tag}>"


EMPTY_TREE = (
    '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/>'
    '<a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree>'
)
CLR_MAP = (
    'bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
    'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" '
    'hlink="hlink" folHlink="folHlink"'
)
CT = "application/vnd.openxmlformats-officedocument.presentationml"


def build_package(pages: list[PageShapes], title: str) -> Package:
    package = Package()
    package.add(
        "_rels/.rels",
        rels_xml(
            [
                ("rId1", "officeDocument", "ppt/presentation.xml"),
                (
                    "rId2",
                    "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties",
                    "docProps/core.xml",
                ),
                ("rId3", "extended-properties", "docProps/app.xml"),
            ]
        ),
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    package.add(
        "docProps/core.xml",
        XML_HEAD
        + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{esc(title)}</dc:title>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
        "</cp:coreProperties>",
        "application/vnd.openxmlformats-package.core-properties+xml",
    )
    package.add(
        "docProps/app.xml",
        XML_HEAD
        + '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        f"<Application>llm-assist-kit marp-slides</Application><Slides>{len(pages)}</Slides>"
        "</Properties>",
        "application/vnd.openxmlformats-officedocument.extended-properties+xml",
    )
    package.add(
        "ppt/theme/theme1.xml",
        theme_xml(),
        "application/vnd.openxmlformats-officedocument.theme+xml",
    )
    package.add(
        "ppt/slideMasters/slideMaster1.xml",
        XML_HEAD + f"<p:sldMaster {NS}><p:cSld>"
        '<p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>'
        f"{EMPTY_TREE}</p:cSld><p:clrMap {CLR_MAP}/>"
        '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
        f"<p:txStyles>{text_style('titleStyle')}{text_style('bodyStyle')}{text_style('otherStyle')}</p:txStyles>"
        "</p:sldMaster>",
        f"{CT}.slideMaster+xml",
    )
    package.add(
        "ppt/slideMasters/_rels/slideMaster1.xml.rels",
        rels_xml(
            [
                ("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml"),
                ("rId2", "theme", "../theme/theme1.xml"),
            ]
        ),
    )
    package.add(
        "ppt/slideLayouts/slideLayout1.xml",
        XML_HEAD
        + f'<p:sldLayout {NS} type="blank" preserve="1"><p:cSld name="白紙">{EMPTY_TREE}</p:cSld>'
        "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>",
        f"{CT}.slideLayout+xml",
    )
    package.add(
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels",
        rels_xml([("rId1", "slideMaster", "../slideMasters/slideMaster1.xml")]),
    )
    pres_rels = [("rId1", "slideMaster", "slideMasters/slideMaster1.xml")]
    slide_ids = []
    for n, page in enumerate(pages, start=1):
        writer = SlideWriter(package)
        xml = writer.xml(page)
        package.add(f"ppt/slides/slide{n}.xml", xml, f"{CT}.slide+xml")
        package.add(f"ppt/slides/_rels/slide{n}.xml.rels", rels_xml(writer.rels))
        rid = f"rId{n + 1}"
        pres_rels.append((rid, "slide", f"slides/slide{n}.xml"))
        slide_ids.append(f'<p:sldId id="{255 + n}" r:id="{rid}"/>')
    k = len(pages) + 2
    pres_rels += [
        (f"rId{k}", "presProps", "presProps.xml"),
        (f"rId{k + 1}", "viewProps", "viewProps.xml"),
        (f"rId{k + 2}", "theme", "theme/theme1.xml"),
        (f"rId{k + 3}", "tableStyles", "tableStyles.xml"),
    ]
    package.add(
        "ppt/presentation.xml",
        XML_HEAD + f'<p:presentation {NS} saveSubsetFonts="1">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        f"<p:sldIdLst>{''.join(slide_ids)}</p:sldIdLst>"
        f'<p:sldSz cx="{emu(SLIDE_W)}" cy="{emu(SLIDE_H)}"/><p:notesSz cx="6858000" cy="9144000"/>'
        f"<p:defaultTextStyle>{text_levels()}</p:defaultTextStyle>"
        "</p:presentation>",
        f"{CT}.presentation.main+xml",
    )
    package.add("ppt/_rels/presentation.xml.rels", rels_xml(pres_rels))
    package.add(
        "ppt/presProps.xml",
        XML_HEAD + f"<p:presentationPr {NS}/>",
        f"{CT}.presProps+xml",
    )
    package.add(
        "ppt/viewProps.xml",
        XML_HEAD
        + f'<p:viewPr {NS}><p:normalViewPr><p:restoredLeft sz="15620"/><p:restoredTop sz="94660"/>'
        '</p:normalViewPr><p:gridSpacing cx="76200" cy="76200"/></p:viewPr>',
        f"{CT}.viewProps+xml",
    )
    package.add(
        "ppt/tableStyles.xml",
        XML_HEAD
        + '<a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>',
        "application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml",
    )
    return package


def convert(source: Path, output: Path) -> list[str]:
    """Markdown のファイルを、編集できる PPTX にする。警告の一覧を返す"""
    slides = parse_markdown(source.read_text(encoding="utf-8"))
    warnings: list[str] = []
    layout = Layout(source.parent, warnings)
    total = len(slides)
    pages = [layout.slide(slide, n, total) for n, slide in enumerate(slides, start=1)]
    title = next(
        (
            plain_text(b.runs)
            for s in slides
            for b in s.blocks
            if isinstance(b, Heading) and b.level in (1, 2)
        ),
        source.stem,
    )
    build_package(pages, title).write(output)
    return list(dict.fromkeys(warnings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Marp のスライドを、編集できる PPTX にする"
    )
    parser.add_argument("slides", type=Path, help="スライドの Markdown ファイル")
    parser.add_argument("-o", "--output", type=Path, help="出力ファイル (.pptx)")
    args = parser.parse_args(argv)
    source: Path = args.slides
    if not source.is_file():
        print(f"スライドのファイルがありません: {source}", file=sys.stderr)
        return 1
    output: Path = args.output or source.with_suffix(".pptx")
    for message in convert(source, output):
        print(f"警告: {message}", file=sys.stderr)
    print(f"作成しました: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
