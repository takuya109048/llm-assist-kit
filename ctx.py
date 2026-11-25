#!/usr/bin/env python3
"""
ctx.py - プロジェクト全体を「1つのコンテキスト」にまとめてクリップボードへコピーするツール

チャット形式の LLM (ChatGPT / Claude.ai / Gemini など) に貼り付けるために、
    1. 冒頭プロンプト (CLAUDE.md のような指示文)
    2. プロジェクトのディレクトリツリー
    3. 各ファイルの生ソースコード
を 1 つのテキストに連結し、クリップボードへ送ります。

使い方 (プロジェクトフォルダ直下に置いて PowerShell から):
    PS> python ctx.py                 # クリップボードへコピー
    PS> python ctx.py --list          # 対象ファイルと推定トークン数だけ確認
    PS> python ctx.py -i "src/**"     # src 以下だけ
    PS> python ctx.py -x "*.test.ts"  # 除外パターン追加
    PS> python ctx.py -o out.md       # ファイルへ出力
    PS> python ctx.py --stdout        # 標準出力へ

標準ライブラリのみで動作 (Python 3.11+)。
"""

from __future__ import annotations

import argparse
import ctypes
import fnmatch
import functools
import io
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

# 冒頭プロンプトとして読み込むファイル (ルート直下、先に見つかったもの)
PROMPT_FILES = ["CONTEXT_PROMPT.md", ".ctxprompt.md", ".ctxprompt"]

# 追加の除外パターンファイル (.gitignore 形式)
IGNORE_FILE = ".ctxignore"

DEFAULT_PROMPT = """\
あなたは熟練したソフトウェアエンジニアです。
以下は私のプロジェクトの「ディレクトリツリー」と「全ソースコード」です。
内容をすべて読み込み、プロジェクトの構造と意図を理解したうえで、この後の私の質問・依頼に答えてください。

# ルール
- 回答は日本語で行うこと。
- コードを変更する場合は、対象ファイルのパスを明記し、変更箇所が分かる形で提示すること。
- 推測で存在しないファイルや関数を前提にしないこと。不明点があれば質問すること。
- このメッセージには「了解しました」とだけ返答し、次の指示を待つこと。
"""

# 常に除外するディレクトリ名
DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".vs",
    "node_modules",
    "bower_components",
    "vendor",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    "venv",
    ".venv",
    "env",
    ".env",
    "dist",
    "build",
    "out",
    "target",
    "bin",
    "obj",
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".turbo",
    ".parcel-cache",
    ".cache",
    "coverage",
    ".coverage",
    "htmlcov",
    ".terraform",
    ".gradle",
    "Pods",
    "DerivedData",
}

# 常に除外するファイルパターン
DEFAULT_EXCLUDE_FILES = [
    # ロックファイル (巨大でノイズになりやすい)
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "poetry.lock",
    "Pipfile.lock",
    "uv.lock",
    "Cargo.lock",
    "composer.lock",
    "Gemfile.lock",
    "go.sum",
    # 秘密情報
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "*.keystore",
    # 生成物・バイナリ系
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.pyc",
    "*.pyo",
    "*.class",
    "*.o",
    "*.so",
    "*.dll",
    "*.exe",
    "*.dylib",
    "*.a",
    "*.lib",
    "*.jar",
    "*.war",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.bmp",
    "*.ico",
    "*.webp",
    "*.svgz",
    "*.pdf",
    "*.zip",
    "*.tar",
    "*.gz",
    "*.7z",
    "*.rar",
    "*.xz",
    "*.mp3",
    "*.mp4",
    "*.wav",
    "*.mov",
    "*.avi",
    "*.ttf",
    "*.otf",
    "*.woff",
    "*.woff2",
    "*.sqlite",
    "*.sqlite3",
    "*.db",
    "*.xlsx",
    "*.xls",
    "*.docx",
    "*.pptx",
    ".DS_Store",
    "Thumbs.db",
]

# 拡張子 -> コードフェンスの言語名
LANG_MAP = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".vue": "vue",
    ".svelte": "svelte",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".json": "json",
    ".jsonc": "jsonc",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".xml": "xml",
    ".svg": "xml",
    ".md": "markdown",
    ".rst": "rst",
    ".txt": "text",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".ps1": "powershell",
    ".psm1": "powershell",
    ".bat": "bat",
    ".cmd": "bat",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".dart": "dart",
    ".scala": "scala",
    ".lua": "lua",
    ".r": "r",
    ".R": "r",
    ".sql": "sql",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".proto": "protobuf",
    ".tf": "hcl",
    ".hcl": "hcl",
    ".dockerfile": "dockerfile",
}
LANG_BY_NAME = {
    "Dockerfile": "dockerfile",
    "Makefile": "makefile",
    "CMakeLists.txt": "cmake",
    ".gitignore": "gitignore",
    ".ctxignore": "gitignore",
}


# ---------------------------------------------------------------------------
# .gitignore 風パターンマッチ (git が使えない場合のフォールバック用 / .ctxignore 用)
# ---------------------------------------------------------------------------


class IgnoreRules:
    """.gitignore 形式のパーサ

    コメント・否定(!)・ディレクトリ指定(末尾 /)・アンカー(先頭/途中の /)・
    `*` `?` `[...]` `**`・エスケープ(\\)に対応。
    """

    def __init__(self) -> None:
        # (base_dir, pattern, negate, dir_only, anchored)
        self.rules: list[tuple[str, str, bool, bool, bool]] = []

    def add_lines(self, lines: list[str], base: str = "") -> None:
        for raw in lines:
            line = raw.rstrip("\n").rstrip()
            if not line or line.startswith("#"):
                continue
            negate = line.startswith("!")
            if negate:
                line = line[1:]
            if line.startswith("\\"):
                line = line[1:]
            dir_only = line.endswith("/")
            line = line.rstrip("/")
            anchored = "/" in line
            line = line.lstrip("/")
            if line:
                self.rules.append((base, line, negate, dir_only, anchored))

    def add_file(self, path: Path, base: str = "") -> None:
        try:
            self.add_lines(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), base
            )
        except OSError:
            pass

    @staticmethod
    def _match(pattern: str, rel: str, anchored: bool) -> bool:
        if anchored:
            return _glob_regex(pattern).fullmatch(rel) is not None
        # アンカー無し: 任意階層のベース名にマッチ
        return _glob_regex(pattern).fullmatch(rel.rsplit("/", 1)[-1]) is not None

    def ignored(self, rel: str, is_dir: bool) -> bool:
        result = False
        for base, pattern, negate, dir_only, anchored in self.rules:
            if dir_only and not is_dir:
                continue
            target = rel
            if base:
                if not rel.startswith(base + "/"):
                    continue
                target = rel[len(base) + 1 :]
            if self._match(pattern, target, anchored):
                result = not negate
        return result


@functools.lru_cache(maxsize=1024)
def _glob_regex(pattern: str) -> re.Pattern[str]:
    """.gitignore のグロブを正規表現に変換する

    - `*` `?` `[...]` は `/` をまたがない
    - `**/` は 0 個以上のディレクトリ、末尾の `/**` は中身すべて、その他の `**` は何でも
    """
    out: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if pattern.startswith("**", i):
            if pattern.startswith("**/", i):
                out.append("(?:.*/)?")
                i += 3
            else:
                out.append(".*")
                i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            end = pattern.find("]", i + 2 if pattern[i + 1 : i + 2] in "!^" else i + 1)
            if end == -1:
                out.append(re.escape(c))
                i += 1
                continue
            body = pattern[i + 1 : end]
            if body[:1] in ("!", "^"):
                body = "^" + body[1:]
            out.append("[" + body.replace("\\", "\\\\") + "]")
            i = end + 1
        elif c == "\\" and i + 1 < n:
            out.append(re.escape(pattern[i + 1]))
            i += 2
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("".join(out), re.DOTALL)


# ---------------------------------------------------------------------------
# ファイル収集
# ---------------------------------------------------------------------------


def git_list_files(root: Path) -> list[str] | None:
    """git 管理下なら .gitignore を尊重したファイル一覧を返す。使えなければ None。"""
    if not shutil.which("git"):
        return None
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if not top:
            return None
        out = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
                "--",
                ".",
            ],
            capture_output=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, OSError):
        return None
    files = []
    for item in out.decode("utf-8", errors="replace").split("\0"):
        if item and (root / item).is_file():  # 削除済みファイルを除外
            files.append(item.replace("\\", "/"))
    return files


def walk_files(root: Path) -> list[str]:
    """git が使えない場合: 自前で走査し .gitignore を簡易適用する。"""
    rules = IgnoreRules()
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        rel_dir = d.relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        if (d / ".gitignore").is_file():
            rules.add_file(d / ".gitignore", rel_dir)
        keep = []
        for name in sorted(dirnames):
            rel = f"{rel_dir}/{name}" if rel_dir else name
            if name in DEFAULT_EXCLUDE_DIRS or rules.ignored(rel, True):
                continue
            keep.append(name)
        dirnames[:] = keep
        for name in filenames:
            rel = f"{rel_dir}/{name}" if rel_dir else name
            if not rules.ignored(rel, False):
                files.append(rel)
    return files


def matches_any(rel: str, patterns: list[str]) -> bool:
    name = rel.rsplit("/", 1)[-1]
    for p in patterns:
        p = p.replace("\\", "/")
        if p.startswith("./"):
            p = p[2:]
        if fnmatch.fnmatchcase(rel, p) or fnmatch.fnmatchcase(name, p):
            return True
        # "src/**" や "src/" のようなディレクトリ指定
        if p.endswith("/**") and rel.startswith(p[:-3] + "/"):
            return True
        if p.endswith("/") and rel.startswith(p):
            return True
        if "**/" in p and fnmatch.fnmatchcase(rel, p.replace("**/", "")):
            return True
    return False


def is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(8192)
    except OSError:
        return True
    if b"\0" in chunk:
        return True
    try:
        chunk.decode("utf-8")
        return False
    except UnicodeDecodeError as e:
        # チャンク境界でマルチバイト文字が切れただけなら OK
        if e.start >= len(chunk) - 4:
            return False
    # UTF-8 でなければ cp932 (Shift_JIS) を試す
    try:
        chunk.decode("cp932")
        return False
    except UnicodeDecodeError:
        return True


def read_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    for enc in ("utf-8", "cp932"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def collect(
    root: Path,
    args: argparse.Namespace,
    self_path: Path | None,
    prompt_path: Path | None,
) -> tuple[list[str], list[tuple[str, str]]]:
    """(採用ファイル一覧, [(除外ファイル, 理由)]) を返す"""
    files = None if args.no_git else git_list_files(root)
    if files is None:
        files = walk_files(root)

    ctxignore = IgnoreRules()
    if (root / IGNORE_FILE).is_file():
        ctxignore.add_file(root / IGNORE_FILE)

    skip_rel = {IGNORE_FILE}
    for p in (self_path, prompt_path):
        if p is not None:
            try:
                skip_rel.add(p.resolve().relative_to(root.resolve()).as_posix())
            except ValueError:
                pass
    if args.output:
        try:
            skip_rel.add(
                Path(args.output).resolve().relative_to(root.resolve()).as_posix()
            )
        except ValueError:
            pass

    selected: list[str] = []
    skipped: list[tuple[str, str]] = []
    max_bytes = int(args.max_size * 1024)

    for rel in sorted(set(files), key=lambda s: s.lower()):
        parts = rel.split("/")
        if rel in skip_rel:
            continue
        if any(p in DEFAULT_EXCLUDE_DIRS for p in parts[:-1]):
            continue
        if matches_any(rel, DEFAULT_EXCLUDE_FILES) and not matches_any(
            rel, args.include or []
        ):
            continue
        if ctxignore.ignored(rel, False) or any(
            ctxignore.ignored("/".join(parts[:i]), True) for i in range(1, len(parts))
        ):
            continue
        if args.include and not matches_any(rel, args.include):
            continue
        if args.exclude and matches_any(rel, args.exclude):
            continue
        path = root / rel
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > max_bytes:
            skipped.append((rel, f"サイズ超過 {size / 1024:.0f}KB"))
            continue
        if is_binary(path):
            skipped.append((rel, "バイナリ"))
            continue
        selected.append(rel)
    return selected, skipped


# ---------------------------------------------------------------------------
# 出力生成
# ---------------------------------------------------------------------------


def build_tree(root_name: str, files: list[str]) -> str:
    tree: dict = {}
    for rel in files:
        node = tree
        for part in rel.split("/"):
            node = node.setdefault(part, {})

    lines = [root_name + "/"]

    def walk(node: dict, prefix: str) -> None:
        # ディレクトリ優先 → 名前順
        items = sorted(node.items(), key=lambda kv: (not kv[1], kv[0].lower()))
        for i, (name, child) in enumerate(items):
            last = i == len(items) - 1
            lines.append(
                f"{prefix}{'└── ' if last else '├── '}{name}{'/' if child else ''}"
            )
            if child:
                walk(child, prefix + ("    " if last else "│   "))

    walk(tree, "")
    return "\n".join(lines)


def lang_of(rel: str) -> str:
    name = rel.rsplit("/", 1)[-1]
    if name in LANG_BY_NAME:
        return LANG_BY_NAME[name]
    if name.startswith("Dockerfile"):
        return "dockerfile"
    return LANG_MAP.get(
        PurePosixPath(name).suffix, LANG_MAP.get(PurePosixPath(name).suffix.lower(), "")
    )


def fence_for(text: str) -> str:
    """本文中のバッククォート連続より長いフェンスを選ぶ (Markdown 内の ``` 対策)"""
    longest, run = 0, 0
    for ch in text:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    return "`" * max(3, longest + 1)


def estimate_tokens(text: str) -> int:
    """ざっくり推定: ASCII は ~4 文字/トークン、非 ASCII (日本語等) は ~1 文字/トークン"""
    ascii_n = sum(1 for c in text if ord(c) < 128)
    return ascii_n // 4 + (len(text) - ascii_n)


def build_context(
    root: Path, files: list[str], prompt: str, show_tree: bool, line_numbers: bool
) -> str:
    out: list[str] = []
    if prompt.strip():
        out.append(prompt.rstrip() + "\n")
    out.append(f"# プロジェクト: {root.name}\n")
    if show_tree:
        out.append("## ディレクトリツリー\n")
        out.append("```text\n" + build_tree(root.name, files) + "\n```\n")
    out.append(f"## ソースコード ({len(files)} ファイル)\n")
    for rel in files:
        try:
            text = read_text(root / rel)
        except OSError as e:
            text = f"<読み込み失敗: {e}>"
        if line_numbers:
            width = len(str(text.count("\n") + 1))
            text = "\n".join(
                f"{i:>{width}}| {line}" for i, line in enumerate(text.split("\n"), 1)
            )
        fence = fence_for(text)
        out.append(f"### {rel}\n")
        out.append(f"{fence}{lang_of(rel)}\n{text.rstrip(chr(10))}\n{fence}\n")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# クリップボード
# ---------------------------------------------------------------------------


def win32_dlls() -> tuple[ctypes.CDLL, ctypes.CDLL]:
    """(user32, kernel32) を返す。Windows 以外では OSError"""
    if sys.platform == "win32":
        return (
            ctypes.WinDLL("user32", use_last_error=True),
            ctypes.WinDLL("kernel32", use_last_error=True),
        )
    raise OSError("Windows 専用です")


def _copy_windows(text: str) -> None:
    """Win32 API で CF_UNICODETEXT として直接書き込む (日本語も文字化けしない)"""
    from ctypes import wintypes

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    user32, kernel32 = win32_dlls()

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]

    data = text.replace("\n", "\r\n").encode("utf-16-le") + b"\0\0"

    for _ in range(10):  # 他プロセスが掴んでいる場合に備えてリトライ
        if user32.OpenClipboard(None):
            break
        time.sleep(0.1)
    else:
        raise OSError("クリップボードを開けませんでした")
    try:
        user32.EmptyClipboard()
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            raise OSError("GlobalAlloc に失敗しました")
        ptr = kernel32.GlobalLock(h)
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(h)
        if not user32.SetClipboardData(CF_UNICODETEXT, h):
            kernel32.GlobalFree(h)
            raise OSError("SetClipboardData に失敗しました")
    finally:
        user32.CloseClipboard()


def copy_to_clipboard(text: str) -> str:
    """コピーに使った手段の名前を返す。失敗時は例外。"""
    if sys.platform == "win32":
        _copy_windows(text)
        return "Win32 API"
    candidates = []
    if sys.platform == "darwin":
        candidates.append(["pbcopy"])
    if os.environ.get("WAYLAND_DISPLAY"):
        candidates.append(["wl-copy"])
    candidates += [
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["clip.exe"],  # WSL
    ]
    for cmd in candidates:
        if shutil.which(cmd[0]):
            enc = "utf-16-le" if cmd[0] == "clip.exe" else "utf-8"
            payload = text.encode(enc)
            if cmd[0] == "clip.exe":
                payload = b"\xff\xfe" + text.replace("\n", "\r\n").encode(enc)
            subprocess.run(cmd, input=payload, check=True)
            return cmd[0]
    raise OSError(
        "クリップボードコマンドが見つかりません (pbcopy / wl-copy / xclip / xsel)"
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def load_prompt(root: Path, args: argparse.Namespace) -> tuple[str, Path | None]:
    if args.no_prompt:
        return "", None
    if args.prompt:
        p = Path(args.prompt)
        if not p.is_absolute():
            p = root / p
        return read_text(p), p
    for name in PROMPT_FILES:
        p = root / name
        if p.is_file():
            return read_text(p), p
    return DEFAULT_PROMPT, None


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            try:
                stream.reconfigure(encoding="utf-8")  # PowerShell での文字化け対策
            except ValueError:
                pass

    script = Path(__file__).resolve()
    ap = argparse.ArgumentParser(
        description="プロジェクトを LLM 用の 1 コンテキストにまとめてクリップボードへコピーします。",
    )
    ap.add_argument(
        "root",
        nargs="?",
        default=None,
        help="対象ディレクトリ (既定: このスクリプトが置かれたフォルダ)",
    )
    ap.add_argument(
        "-i",
        "--include",
        action="append",
        metavar="GLOB",
        help='含めるパターン (複数可) 例: -i "src/**" -i "*.py"',
    )
    ap.add_argument(
        "-x",
        "--exclude",
        action="append",
        metavar="GLOB",
        help='除外するパターン (複数可) 例: -x "tests/**"',
    )
    ap.add_argument(
        "-p",
        "--prompt",
        metavar="FILE",
        help=f"冒頭プロンプトのファイル (既定: {' / '.join(PROMPT_FILES)} → 内蔵プロンプト)",
    )
    ap.add_argument("--no-prompt", action="store_true", help="冒頭プロンプトを付けない")
    ap.add_argument(
        "--no-tree", action="store_true", help="ディレクトリツリーを付けない"
    )
    ap.add_argument("-n", "--line-numbers", action="store_true", help="行番号を付ける")
    ap.add_argument(
        "--max-size",
        type=float,
        default=200,
        metavar="KB",
        help="これより大きいファイルはスキップ (既定: 200KB)",
    )
    ap.add_argument(
        "--no-git",
        action="store_true",
        help="git ls-files を使わず自前走査する (.gitignore は簡易解釈)",
    )
    ap.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="コピーせず対象ファイルとサイズ/推定トークンを表示",
    )
    ap.add_argument(
        "-o", "--output", metavar="FILE", help="クリップボードの代わりにファイルへ出力"
    )
    ap.add_argument(
        "--stdout", action="store_true", help="クリップボードの代わりに標準出力へ"
    )
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else script.parent
    if not root.is_dir():
        print(f"エラー: ディレクトリではありません: {root}", file=sys.stderr)
        return 1

    prompt, prompt_path = load_prompt(root, args)
    files, skipped = collect(root, args, script, prompt_path)

    if not files:
        print("対象ファイルがありません。", file=sys.stderr)
        return 1

    if args.list:
        total = 0
        for rel in files:
            t = estimate_tokens(read_text(root / rel))
            total += t
            print(f"{t:>8,} tok  {rel}")
        for rel, why in skipped:
            print(f"{'skip':>12}  {rel}  ({why})")
        print(
            f"\n{len(files)} ファイル / 推定 {total + estimate_tokens(prompt):,} トークン",
            file=sys.stderr,
        )
        return 0

    text = build_context(root, files, prompt, not args.no_tree, args.line_numbers)
    summary = (
        f"{len(files)} ファイル / {len(text):,} 文字 / 推定 {estimate_tokens(text):,} トークン"
        + (f" (スキップ {len(skipped)})" if skipped else "")
    )

    if args.stdout:
        sys.stdout.write(text)
        print(f"\n[ctx] {summary}", file=sys.stderr)
        return 0
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"[ctx] {args.output} に出力しました: {summary}", file=sys.stderr)
        return 0
    try:
        how = copy_to_clipboard(text)
    except (OSError, subprocess.CalledProcessError) as e:
        print(
            f"エラー: クリップボードへのコピーに失敗しました ({e})\n"
            f"  --stdout か -o FILE を使ってください。",
            file=sys.stderr,
        )
        return 1
    print(f"[ctx] クリップボードにコピーしました ({how}): {summary}", file=sys.stderr)
    for rel, why in skipped:
        print(f"  skip: {rel} ({why})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
