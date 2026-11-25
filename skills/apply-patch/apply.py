"""LLM が書いたパッチ (codex の apply_patch 形式) をプロジェクトに適用する

使い方 (プロジェクトのフォルダで):
    python apply.py              # クリップボードのパッチを適用
    python apply.py -f patch.txt # ファイルから
    ... | python apply.py -f -   # 標準入力から (PowerShell のヒアストリングを渡す)
    python apply.py --dry-run    # 変更されるファイルの一覧だけ表示

LLM の回答をまるごとコピーしてもよい: `*** Begin Patch` 〜 `*** End Patch` の部分だけを取り出す。
実際の適用は、同じフォルダの apply_patch.zip に入っている codex-rs の apply_patch で行う。
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import io
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

HERE = Path(__file__).resolve().parent
ZIP_PATH = HERE / "apply_patch.zip"
CACHE_DIR = HERE / ".bin"  # zip から取り出した実行ファイルの置き場 (git 管理外)

BEGIN = "*** Begin Patch"
END = "*** End Patch"
HEADER_RE = re.compile(r"^\*\*\* (Add File|Delete File|Update File|Move to): (.+)$")
# 前後の空白を取ってよい行 (パッチの構造を表す行)。本文の行には触らない
CONTROL_RE = re.compile(
    r"^\s*(\*\*\* (Add File|Delete File|Update File|Move to): .*|\*\*\* End of File)\s*$"
)


# ---------------------------------------------------------------------------
# パッチの取り出しと確認
# ---------------------------------------------------------------------------


def extract_patches(text: str) -> list[str]:
    """テキストから `*** Begin Patch` 〜 `*** End Patch` をすべて取り出す"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    patches: list[str] = []
    current: list[str] | None = None
    for line in lines:
        stripped = line.strip()
        if current is None:
            if stripped == BEGIN:
                current = [BEGIN]
        elif stripped == END:
            current.append(END)
            patches.append("\n".join(current) + "\n")
            current = None
        elif stripped == BEGIN:
            current = [BEGIN]  # 閉じていないパッチは捨てて、新しいパッチから始める
        else:
            # 構造を表す行は前後の空白を取る。本文の行 (+ - 空白で始まる) は変えない
            current.append(stripped if CONTROL_RE.match(line) else line)
    if current is not None:
        raise ValueError(f"`{END}` が見つかりません (パッチが途中で切れています)")
    return patches


def summarize(patch: str) -> list[tuple[str, str]]:
    """パッチの (操作, パス) 一覧"""
    ops = []
    for line in patch.split("\n"):
        m = HEADER_RE.match(line)
        if m:
            ops.append((m.group(1), m.group(2).strip()))
    return ops


def unsafe_path(path: str) -> bool:
    """プロジェクトの外を指すパス (絶対パス・.. で上に出る) なら True"""
    if PurePosixPath(path).is_absolute() or PureWindowsPath(path).is_absolute():
        return True
    if PureWindowsPath(path).drive:
        return True
    depth = 0
    for part in re.split(r"[\\/]+", path):
        if part == "..":
            depth -= 1
            if depth < 0:
                return True
        elif part not in ("", "."):
            depth += 1
    return False


LABELS = {
    "Add File": "追加",
    "Update File": "更新",
    "Delete File": "削除",
    "Move to": "  → 移動先",
}


# ---------------------------------------------------------------------------
# 入力の読み取り
# ---------------------------------------------------------------------------


def decode_input(data: bytes) -> str:
    """標準入力のバイト列を文字列にする

    PowerShell からパイプで渡すと、$OutputEncoding に応じて UTF-8 (BOM 付きのことも) や
    cp932 で届く。OS の既定の文字コードに頼らず、UTF-8 → cp932 の順に試す
    """
    for enc in ("utf-8-sig", "cp932"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_clipboard() -> str:
    if sys.platform == "win32":
        return _read_clipboard_windows()
    if sys.platform == "darwin":
        commands = [["pbpaste"]]
    else:
        commands = []
        if os.environ.get("WAYLAND_DISPLAY"):
            commands.append(["wl-paste", "--no-newline"])
        commands += [
            ["xclip", "-selection", "clipboard", "-o"],
            ["xsel", "--clipboard", "--output"],
            ["powershell.exe", "-NoProfile", "-Command", "Get-Clipboard -Raw"],  # WSL
        ]
    for cmd in commands:
        if shutil.which(cmd[0]):
            r = subprocess.run(cmd, capture_output=True, check=True)
            return r.stdout.decode("utf-8", errors="replace")
    raise OSError(
        "クリップボードを読むコマンドが見つかりません (-f でファイルを指定してください)"
    )


def _win32_dlls() -> tuple[ctypes.CDLL, ctypes.CDLL]:
    """(user32, kernel32) を返す。Windows 以外では OSError"""
    if sys.platform == "win32":
        return (
            ctypes.WinDLL("user32", use_last_error=True),
            ctypes.WinDLL("kernel32", use_last_error=True),
        )
    raise OSError("Windows 専用です")


def _read_clipboard_windows() -> str:
    from ctypes import wintypes

    user32, kernel32 = _win32_dlls()
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    if not user32.OpenClipboard(None):
        raise OSError("クリップボードを開けませんでした")
    try:
        handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


# ---------------------------------------------------------------------------
# apply_patch 実行ファイル
# ---------------------------------------------------------------------------


def platform_key() -> str:
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "x64": "x86_64", "arm64": "aarch64"}.get(
        machine, machine
    )
    if sys.platform == "win32":
        return "windows-x86_64"  # ARM 版 Windows も x64 エミュレーションで動く
    if sys.platform == "darwin":
        return f"macos-{arch}"
    return f"linux-{arch}"


def find_binary() -> Path:
    """zip から今の OS 用の apply_patch を取り出して、そのパスを返す"""
    exe = "apply_patch.exe" if sys.platform == "win32" else "apply_patch"
    member = f"{platform_key()}/{exe}"
    with zipfile.ZipFile(ZIP_PATH) as zf:
        names = zf.namelist()
        if member not in names:
            have = sorted(
                {n.split("/")[0] for n in names if n.endswith(("apply_patch", ".exe"))}
            )
            raise OSError(
                f"この OS ({platform_key()}) 用の apply_patch は zip に入っていません "
                f"(入っているもの: {', '.join(have)})"
            )
        data = zf.read(member)
    target = CACHE_DIR / hashlib.sha256(data).hexdigest()[:16] / exe
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        tmp.replace(target)
    return target


# ---------------------------------------------------------------------------
# 失敗したときの巻き戻し
# ---------------------------------------------------------------------------


class Backup:
    """パッチが触るファイルの適用前の状態を覚えておき、失敗したら戻す

    apply_patch はファイル操作を順に書き込むので、途中で失敗すると
    それより前の変更が残る。中途半端な状態を残さないために使う。
    """

    def __init__(self, paths: list[str]) -> None:
        self.saved: dict[Path, bytes | None] = {}
        for p in paths:
            path = Path(p)
            if path in self.saved:
                continue
            self.saved[path] = path.read_bytes() if path.is_file() else None

    def restore(self) -> list[str]:
        """適用前の状態に戻し、戻したパスの一覧を返す"""
        restored = []
        for path, data in self.saved.items():
            if data is None:
                if path.is_file():
                    path.unlink()
                    restored.append(path.as_posix())
            elif not path.is_file() or path.read_bytes() != data:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                restored.append(path.as_posix())
        return restored


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def use_utf8_output() -> None:
    """出力を UTF-8 にする (英語版 Windows でパイプに出すと cp1252 になり、日本語で落ちるため)"""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            try:
                stream.reconfigure(encoding="utf-8")
            except ValueError:
                pass


def main(argv: list[str]) -> int:
    use_utf8_output()
    ap = argparse.ArgumentParser(prog="apply.py", description=__doc__.split("\n")[0])
    ap.add_argument(
        "-f", "--file", help="パッチを読むファイル (- で標準入力。既定: クリップボード)"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="変更されるファイルの一覧だけ表示"
    )
    args = ap.parse_args(argv)

    try:
        if args.file == "-":
            text = decode_input(sys.stdin.buffer.read())
        elif args.file:
            text = Path(args.file).read_text(encoding="utf-8-sig")
        else:
            text = read_clipboard()
        patches = extract_patches(text)
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        print(f"エラー: {e}")
        return 1
    if not patches:
        print(
            f"エラー: パッチが見つかりません (`{BEGIN}` 〜 `{END}` を含むテキストが必要です)"
        )
        return 1

    unsafe = [p for patch in patches for _, p in summarize(patch) if unsafe_path(p)]
    if unsafe:
        print("エラー: プロジェクトの外を指すパスがあるので適用しません:")
        for p in unsafe:
            print(f"  {p}")
        return 1

    for i, patch in enumerate(patches, 1):
        title = f"パッチ {i}/{len(patches)}" if len(patches) > 1 else "パッチ"
        print(f"{title} ({Path.cwd().as_posix()} に適用):")
        ops = summarize(patch)
        for op, path in ops:
            print(f"  {LABELS[op]}: {path}")
        if not ops:
            print("  (ファイル操作がありません)")
    if args.dry_run:
        print("\n--dry-run のため適用していません")
        return 0

    try:
        binary = find_binary()
    except (OSError, zipfile.BadZipFile) as e:
        print(f"エラー: {e}")
        return 1
    # すべてのパッチが触るファイルを覚えておき、どれかが失敗したら全部戻す
    backup = Backup([p for patch in patches for _, p in summarize(patch)])
    for patch in patches:
        print()
        r = subprocess.run(
            [str(binary)], input=patch.encode("utf-8"), capture_output=True
        )
        out = (r.stdout + r.stderr).decode("utf-8", errors="replace").strip()
        print(out or "(出力なし)")
        if r.returncode != 0:
            restored = backup.restore()
            print(
                f"\n失敗しました (終了コード {r.returncode})。"
                "すべての変更を元に戻しました。"
            )
            for p in restored:
                print(f"  元に戻した: {p}")
            return r.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
