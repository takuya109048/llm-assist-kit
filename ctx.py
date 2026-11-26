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
import locale
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

# 冒頭プロンプトとして読み込むファイル (ルート直下、先に見つかったもの)
PROMPT_FILES = ["AGENTS.md", ".ctxprompt.md", ".ctxprompt"]

# 追加の除外パターンファイル (.gitignore 形式)
IGNORE_FILE = ".ctxignore"

# スキル: プロジェクトの外 (この ctx.py と同じ場所の skills/) に置き、どのプロジェクトでも使う。
# 各サブフォルダの SKILL.md を読む。環境変数 CTX_SKILLS_DIR か --skills-dir で変更できる
SKILLS_DIR_NAME = "skills"
SKILLS_ENV = "CTX_SKILLS_DIR"
SKILL_FILE = "SKILL.md"

SKILLS_PREAMBLE = """\
# スキル

以下のスキル (作業手順と補助スクリプト) が使えます。
依頼内容に合うスキルがあれば、その手順に従ってください。

- あなたはスクリプトやコマンドを直接実行できません。実行が必要なときは、
  ユーザーが PowerShell で実行するコマンドを powershell のコードブロックで示し、実行を依頼してください。
- 実行結果を見る必要があるときは、コマンドの前に `python {runner} run --` を付けてください。
  ユーザーが実行すると、コマンド・終了コード・出力が「## 実行結果」の形でクリップボードにコピーされ、
  このチャットに貼り付けられます。例:

  ```powershell
  python {runner} run -- python -m pytest -q
  ```
- テスト結果や検索結果など、実行結果の中身を見て判断する必要があるときは、結果が貼られるまで推測で決めつけないでください。
  ただし、各スキルに別の決まりがあれば、そちらに従ってください。
"""

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
# スキル
# ---------------------------------------------------------------------------


@dataclass
class Skill:
    name: str
    description: str
    dir: str  # プロジェクト内なら相対、外なら絶対パス (/ 区切り)
    body: str
    files: list[str]  # SKILL.md 以外のファイル (スキルフォルダからの相対パス)

    @property
    def skill_file(self) -> str:
        return f"{self.dir}/{SKILL_FILE}"


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """先頭の --- で囲まれた `key: value` を読み、(メタデータ, 本文) を返す"""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            break
    else:
        return {}, text
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if sep and key.strip() and not line.startswith((" ", "\t", "#")):
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            meta[key.strip()] = value
    return meta, "\n".join(lines[end + 1 :]).strip("\n")


def display_path(path: Path, root: Path) -> str:
    """root の中ならルートからの相対パス、外なら絶対パス (どちらも / 区切り)"""
    path = path.resolve()
    try:
        return path.relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def default_skill_dirs(script: Path) -> list[Path]:
    """環境変数 CTX_SKILLS_DIR (複数は ; や : で区切る) → ctx.py と同じ場所の skills/"""
    env = os.environ.get(SKILLS_ENV, "")
    if env.strip():
        return [Path(d).expanduser() for d in env.split(os.pathsep) if d.strip()]
    return [script.parent / SKILLS_DIR_NAME]


def load_skills(dirs: list[Path], only: list[str] | None, root: Path) -> list[Skill]:
    """dirs 以下の <name>/SKILL.md を読み込む。同名のスキルは先に見つかった方を使う

    パスは root (対象プロジェクト) の中なら相対、外なら絶対で表す
    """
    skills: dict[str, Skill] = {}
    for base in dirs:
        if not base.is_dir():
            continue
        for sub in sorted(base.iterdir(), key=lambda p: p.name.lower()):
            skill_md = sub / SKILL_FILE
            if not skill_md.is_file():
                continue
            meta, body = parse_frontmatter(read_text(skill_md))
            name = meta.get("name") or sub.name
            if name in skills:
                continue
            rel_dir = display_path(sub, root)
            files = sorted(
                (
                    f.relative_to(sub).as_posix()
                    for f in sub.rglob("*")
                    if f.is_file()
                    and f.name != SKILL_FILE
                    and not any(
                        p in DEFAULT_EXCLUDE_DIRS or p.startswith(".")
                        for p in f.relative_to(sub).parts
                    )
                ),
                key=str.lower,
            )
            skills[name] = Skill(
                name=name,
                description=meta.get("description", ""),
                dir=rel_dir,
                body=body.replace("${SKILL_DIR}", rel_dir),
                files=files,
            )
    if only:
        missing = [n for n in only if n not in skills]
        if missing:
            raise ValueError(
                f"スキルが見つかりません: {', '.join(missing)} "
                f"(あるもの: {', '.join(skills) or 'なし'})"
            )
        return [skills[n] for n in only]
    return list(skills.values())


def build_skills_section(skills: list[Skill], runner: str) -> str:
    out = [SKILLS_PREAMBLE.format(runner=runner)]
    for sk in skills:
        out.append(f"## スキル: {sk.name}\n")
        info = []
        if sk.description:
            info.append(f"- 説明: {sk.description}")
        info.append(f"- フォルダ: `{sk.dir}/`")
        if sk.files:
            info.append("- ファイル: " + ", ".join(f"`{sk.dir}/{f}`" for f in sk.files))
        out.append("\n".join(info) + "\n")
        body = sk.body.replace("${CTX}", runner)  # ctx.py の実際のパス
        if body.strip():
            out.append(body.strip() + "\n")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# ファイル収集
# ---------------------------------------------------------------------------


def git_list_files(root: Path) -> list[str] | None:
    """git 管理下なら .gitignore を尊重したファイル一覧を返す。使えなければ None。"""
    if not shutil.which("git"):
        return None
    try:
        # git の出力は UTF-8。text=True だと Windows では cp932 で読もうとして、
        # 日本語のパスを含むエラーメッセージで UnicodeDecodeError になる
        r = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
        )
        if r.returncode != 0:
            err = r.stderr.decode("utf-8", errors="replace")
            if "dubious ownership" in err:
                print(
                    "[ctx] 注意: git が「dubious ownership」(フォルダの所有者が自分ではない) "
                    "と言って、このフォルダのリポジトリを使えません。\n"
                    "      .gitignore は簡易的に解釈します。llm-assist-kit の `init` を"
                    "このフォルダで実行すると直ります。",
                    file=sys.stderr,
                )
            return None
        top = r.stdout.decode("utf-8", errors="replace").strip()
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
    skip_paths: list[Path],
) -> tuple[list[str], list[tuple[str, str]]]:
    """(採用ファイル一覧, [(除外ファイル, 理由)]) を返す"""
    files = None if args.no_git else git_list_files(root)
    if files is None:
        files = walk_files(root)

    ctxignore = IgnoreRules()
    if (root / IGNORE_FILE).is_file():
        ctxignore.add_file(root / IGNORE_FILE)

    skip_rel = {IGNORE_FILE}
    for p in skip_paths:
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
    root: Path,
    files: list[str],
    prompt: str,
    show_tree: bool,
    line_numbers: bool,
    skills_section: str = "",
) -> str:
    out: list[str] = []
    if prompt.strip():
        out.append(prompt.rstrip() + "\n")
    if skills_section:
        out.append(skills_section.rstrip() + "\n")
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
# run: コマンドを実行し、結果を LLM に貼れる形でクリップボードへ
# ---------------------------------------------------------------------------

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")


def decode_output(data: bytes) -> str:
    """UTF-8 → cp932 → OS の既定エンコーディングの順に試す

    cp1252 のような 1 バイト文字コードはどんなバイト列でもエラーなく読めてしまうので、
    OS の既定は最後に試す (英語版 Windows で cp932 の出力が化けるのを防ぐ)
    """
    for enc in ("utf-8", "cp932", locale.getpreferredencoding(False)):
        try:
            text = data.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        text = data.decode("utf-8", errors="replace")
    text = ANSI_RE.sub("", text.replace("\r\n", "\n"))
    # 進捗表示などの \r による上書きは最後の内容だけ残す
    return "\n".join(line.rsplit("\r", 1)[-1] for line in text.split("\n"))


def shell_command(command: str) -> list[str]:
    """1 つの文字列で渡されたコマンドをシェル経由で実行する引数にする"""
    if sys.platform == "win32":
        ps = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
        # PowerShell の出力を UTF-8 にしてから実行する
        prefix = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
        return [ps, "-NoProfile", "-Command", prefix + command]
    return ["/bin/sh", "-c", command]


def format_run_result(display: str, code: int, output: str, tail: int) -> str:
    lines = output.rstrip("\n").split("\n") if output.strip() else []
    total = len(lines)
    note = ""
    if tail and total > tail:
        note = f"(先頭 {total - tail} 行を省略。全 {total} 行のうち最後の {tail} 行)\n"
        lines = lines[-tail:]
    body = note + ("\n".join(lines) if lines else "(出力なし)")
    status = "成功" if code == 0 else "失敗"
    cmd_block = f"PS> {display}"
    out_fence = fence_for(body)
    cmd_fence = fence_for(cmd_block)
    return (
        "## 実行結果\n\n"
        f"{cmd_fence}powershell\n{cmd_block}\n{cmd_fence}\n\n"
        f"- 終了コード: {code} ({status})\n\n"
        f"{out_fence}text\n{body}\n{out_fence}\n"
    )


def execute(cmd: list[str]) -> tuple[int, str]:
    """コマンドを実行し、出力を画面に流しながら集める。(終了コード, 出力)"""
    # PYTHONUNBUFFERED: パイプ越しだと Python は標準出力だけをバッファするため、
    # 標準エラーとの順番が入れ替わるのを防ぐ
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env
        )
    except FileNotFoundError:
        return 127, f"コマンドが見つかりません: {cmd[0]}"
    except OSError as e:
        return 126, f"コマンドを実行できません: {e}"
    assert proc.stdout is not None
    chunks: list[bytes] = []
    for line in iter(proc.stdout.readline, b""):
        chunks.append(line)
        sys.stderr.write(decode_output(line).rstrip("\n") + "\n")
        sys.stderr.flush()
    return proc.wait(), decode_output(b"".join(chunks))


def run_main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="ctx.py run",
        description=(
            "コマンドを実行し、コマンド・終了コード・出力を LLM に貼れる形で"
            "クリップボードへコピーします。"
        ),
        epilog=(
            "例: python ctx.py run -- python -m pytest -q   /   "
            'python ctx.py run "Get-ChildItem src | Select-Object Name"'
        ),
    )
    ap.add_argument(
        "--tail",
        type=int,
        default=200,
        metavar="N",
        help="出力の最後の N 行だけ残す (0 で全部。既定: 200)",
    )
    ap.add_argument(
        "-o", "--output", metavar="FILE", help="クリップボードの代わりにファイルへ出力"
    )
    ap.add_argument(
        "--stdout", action="store_true", help="クリップボードの代わりに標準出力へ"
    )
    ap.add_argument(
        "command",
        nargs="*",
        help="実行するコマンド。-- の後に書く。1 つの文字列ならシェル (Windows は PowerShell) で実行",
    )
    if "--" in argv:
        i = argv.index("--")
        args = ap.parse_args(argv[:i])
        command = argv[i + 1 :]
    else:
        args = ap.parse_args(argv)
        command = args.command
    if not command:
        ap.error("実行するコマンドを指定してください")

    if len(command) == 1:
        display, cmd = command[0], shell_command(command[0])
    else:
        join = subprocess.list2cmdline if sys.platform == "win32" else shlex.join
        display, cmd = join(command), command

    code, output = execute(cmd)
    text = format_run_result(display, code, output, args.tail)
    n_lines = len(output.rstrip("\n").split("\n")) if output.strip() else 0
    summary = f"終了コード {code} / {n_lines} 行"

    if args.stdout:
        sys.stdout.write(text)
        print(f"[ctx] {summary}", file=sys.stderr)
        return code
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"[ctx] {args.output} に出力しました: {summary}", file=sys.stderr)
        return code
    try:
        how = copy_to_clipboard(text)
    except (OSError, subprocess.CalledProcessError) as e:
        print(
            f"エラー: クリップボードへのコピーに失敗しました ({e})\n"
            f"  --stdout か -o FILE を使ってください。",
            file=sys.stderr,
        )
        return code or 1
    print(
        f"[ctx] 実行結果をクリップボードにコピーしました ({how}): {summary}",
        file=sys.stderr,
    )
    return code


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def strip_html_comments(text: str) -> str:
    """冒頭プロンプトから <!-- --> のコメントを取り除く (コードブロックの中は残す)

    Claude Code が CLAUDE.md を読むときと同じく、人向けのメモを LLM に渡さないため。
    コメントだけだった行は行ごと消し、続いた空行は 1 行にまとめる。
    """
    parts: list[str] = []  # コードブロックの外と中を交互に
    outside: list[str] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        m = _FENCE.match(line)
        if fence is None:
            if m:
                parts.append("".join(outside))
                outside = [line]
                fence = m.group(1)
                continue
            outside.append(line)
        else:
            outside.append(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                parts.append("".join(outside))
                outside = []
                fence = None
    parts.append("".join(outside))
    if fence is not None:  # 閉じていないコードブロックは最後まで中として扱う
        parts.append("")
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 0 and "<!--" in part:
            removed = _HTML_COMMENT.sub("\0", part)
            lines = removed.splitlines(keepends=True)
            kept = [
                ln.replace("\0", "")
                for ln in lines
                if "\0" not in ln or ln.replace("\0", "").strip()
            ]
            part = re.sub(r"\n{3,}", "\n\n", "".join(kept))
        result.append(part)
    return "".join(result).lstrip("\n")


def load_prompt(root: Path, args: argparse.Namespace) -> tuple[str, Path | None]:
    if args.no_prompt:
        return "", None
    if args.prompt:
        p = Path(args.prompt)
        if not p.is_absolute():
            p = root / p
        return strip_html_comments(read_text(p)), p
    for name in PROMPT_FILES:
        p = root / name
        if p.is_file():
            return strip_html_comments(read_text(p)), p
    return DEFAULT_PROMPT, None


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            try:
                stream.reconfigure(encoding="utf-8")  # PowerShell での文字化け対策
            except ValueError:
                pass

    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["run"]:
        return run_main(argv[1:])

    script = Path(__file__).resolve()
    ap = argparse.ArgumentParser(
        description="プロジェクトを LLM 用の 1 コンテキストにまとめてクリップボードへコピーします。",
        epilog=(
            "コマンドの実行結果をコピーする: python ctx.py run -- <コマンド>"
            " (詳しくは python ctx.py run -h)"
        ),
    )
    ap.add_argument(
        "root",
        nargs="?",
        default=None,
        help="対象ディレクトリ (既定: 今いるフォルダ)",
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
        "-s",
        "--skill",
        action="append",
        metavar="NAME",
        help="入れるスキルを指定 (複数可。既定: 見つかったスキルすべて)",
    )
    ap.add_argument(
        "--skills-dir",
        action="append",
        metavar="DIR",
        help=(
            f"スキルを探すフォルダ (複数可。既定: 環境変数 {SKILLS_ENV}、"
            f"無ければ ctx.py と同じ場所の {SKILLS_DIR_NAME}/)"
        ),
    )
    ap.add_argument("--no-skills", action="store_true", help="スキルを入れない")
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

    root = Path(args.root or ".").resolve()
    if not root.is_dir():
        print(f"エラー: ディレクトリではありません: {root}", file=sys.stderr)
        return 1

    prompt, prompt_path = load_prompt(root, args)
    skill_dirs = (
        [Path(d) for d in args.skills_dir]
        if args.skills_dir
        else default_skill_dirs(script)
    )
    try:
        skills = [] if args.no_skills else load_skills(skill_dirs, args.skill, root)
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    runner = display_path(script, root)
    skills_section = build_skills_section(skills, runner) if skills else ""

    skip_paths = [script] + ([prompt_path] if prompt_path else [])
    skip_paths += [
        root / sk.skill_file for sk in skills
    ]  # プロジェクト内にある場合だけ効く
    files, skipped = collect(root, args, skip_paths)

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
        for sk in skills:
            print(f"{'skill':>12}  {sk.name}  ({sk.skill_file})")
        extra = estimate_tokens(prompt) + estimate_tokens(skills_section)
        print(
            f"\n{len(files)} ファイル"
            + (f" / スキル {len(skills)}" if skills else "")
            + f" / 推定 {total + extra:,} トークン",
            file=sys.stderr,
        )
        return 0

    text = build_context(
        root, files, prompt, not args.no_tree, args.line_numbers, skills_section
    )
    summary = (
        f"{len(files)} ファイル"
        + (f" / スキル {len(skills)}" if skills else "")
        + f" / {len(text):,} 文字 / 推定 {estimate_tokens(text):,} トークン"
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
