"""llm-assist-kit の初期設定: PowerShell のプロファイルに関数 (ctx など) を登録する

使い方 (キットのフォルダで):
    python install.py                        # 登録 (何度実行しても同じ。キットを移したら再実行)
    python install.py --uninstall            # 登録した関数を外す
    python install.py --print                # 書き込む内容を表示するだけ
    python install.py --set-execution-policy # プロファイルが読み込まれるよう実行ポリシーも設定

プロファイル (Windows PowerShell 5.1 と PowerShell 7 の両方) の中の
`# >>> llm-assist-kit >>>` 〜 `# <<< llm-assist-kit <<<` の範囲だけを書き換える。

関数を追加するときは、下の FUNCTIONS に 1 行足して、もう一度 `python install.py` を実行する。
"""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

KIT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class PSFunction:
    name: str  # PowerShell で打つ名前
    script: str  # キットのフォルダからの相対パス (Python スクリプト)
    description: str


# 登録する関数。追加するときはここに足す
FUNCTIONS = [
    PSFunction(
        "ctx",
        "ctx.py",
        "プロジェクトのコンテキストをクリップボードへ (ctx run -- ... も)",
    ),
    PSFunction(
        "addcommit",
        "commands/addcommit.py",
        "git add -A と git commit -m をまとめて行う (addcommit メッセージ)",
    ),
    PSFunction(
        "reset",
        "commands/reset.py",
        "git reset --hard HEAD と git clean -fd をまとめて行う (確認あり。reset -y で確認なし)",
    ),
]

BEGIN_MARK = "# >>> llm-assist-kit >>>"
END_MARK = "# <<< llm-assist-kit <<<"
POWERSHELLS = ["powershell", "pwsh"]  # Windows PowerShell 5.1 / PowerShell 7
# プロファイルを読み込まない実行ポリシー (スクリプトの実行が許可されていない)
BLOCKING_POLICIES = {"Restricted", "AllSigned"}


# ---------------------------------------------------------------------------
# プロファイルに書く内容
# ---------------------------------------------------------------------------


def ps_quote(text: str) -> str:
    """PowerShell の単一引用符の文字列にする (' は '' にする)"""
    return "'" + text.replace("'", "''") + "'"


def render_block(functions: list[PSFunction], python: str, kit: Path) -> str:
    lines = [f"{BEGIN_MARK} (install.py が管理。この範囲は手で編集しないでください)"]
    for f in functions:
        script = str(kit / f.script)
        lines.append(f"# {f.name}: {f.description}")
        lines.append(
            f"function {f.name} {{ & {ps_quote(python)} {ps_quote(script)} @args }}"
        )
    lines.append(END_MARK)
    return "\n".join(lines) + "\n"


def replace_block(text: str, block: str | None) -> str:
    """プロファイルの本文の、管理範囲を block に置き換える (None なら取り除く)"""
    lines = text.splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if ln.startswith(BEGIN_MARK)), None)
    end = next(
        (
            i
            for i, ln in enumerate(lines)
            if start is not None and i > start and ln.startswith(END_MARK)
        ),
        None,
    )
    if start is not None and end is not None:
        before, after = lines[:start], lines[end + 1 :]
    else:
        before, after = lines, []
    head = "".join(before)
    tail = "".join(after)
    if block is None:
        # 管理範囲の前後に入れた空行も片付ける
        return head.rstrip("\n") + ("\n" if head.strip() else "") + tail.lstrip("\n")
    if head and not head.endswith("\n"):
        head += "\n"
    if head.strip() and not head.endswith("\n\n"):
        head += "\n"
    return head + block + tail


# ---------------------------------------------------------------------------
# プロファイルの読み書き (文字コードを保つ)
# ---------------------------------------------------------------------------


def read_profile(path: Path) -> tuple[str, str, str]:
    """(本文, 文字コード, 改行) を返す。無ければ UTF-8 (BOM 付き) の新規扱い"""
    if not path.is_file():
        return "", "utf-8-sig", "\r\n" if sys.platform == "win32" else "\n"
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    elif data.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16"
    else:
        try:
            data.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            encoding = "cp932"  # BOM なしの ANSI (日本語 Windows)
    text = data.decode(encoding)
    newline = "\r\n" if "\r\n" in text else ("\n" if "\n" in text else os_newline())
    return text.replace("\r\n", "\n"), encoding, newline


def os_newline() -> str:
    return "\r\n" if sys.platform == "win32" else "\n"


def write_profile(path: Path, text: str, encoding: str, newline: str) -> None:
    """プロファイルを書く

    Windows PowerShell 5.1 は BOM の無いファイルを ANSI (cp932) として読むので、
    UTF-8 は BOM 付きで書く (日本語のパスやコメントが化けないように)。
    元の文字コード (cp932 など) で書けない文字があれば UTF-8 (BOM 付き) にする。
    """
    if encoding == "utf-8":
        encoding = "utf-8-sig"
    data = text.replace("\n", newline)
    try:
        raw = data.encode(encoding)
    except UnicodeEncodeError:
        raw = data.encode("utf-8-sig")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


# ---------------------------------------------------------------------------
# PowerShell への問い合わせ
# ---------------------------------------------------------------------------


def run_powershell(exe: str, command: str) -> str | None:
    try:
        r = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.decode("utf-8", errors="replace").strip() or None


def find_profiles() -> list[tuple[str, Path]]:
    """インストールされている PowerShell ごとの (名前, プロファイルのパス)"""
    found: list[tuple[str, Path]] = []
    for exe in POWERSHELLS:
        if not shutil.which(exe):
            continue
        # 日本語のユーザー名でも文字化けしないよう、出力を UTF-8 にしてから聞く
        # (切り替えができない環境でも、プロファイルの場所は聞けるように続ける)
        out = run_powershell(
            exe,
            "try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}; "
            "$PROFILE.CurrentUserAllHosts",
        )
        if out:
            path = Path(out.splitlines()[-1].strip())
            # powershell と pwsh が同じ PowerShell 7 を指す環境 (macOS など) では
            # 同じプロファイルになるので、1 回だけ書く
            if all(path != p for _, p in found):
                found.append((exe, path))
    return found


def execution_policy(exe: str) -> str | None:
    return run_powershell(exe, "Get-ExecutionPolicy")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def use_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            try:
                stream.reconfigure(encoding="utf-8")
            except ValueError:
                pass


def main(argv: list[str] | None = None) -> int:
    use_utf8_output()
    ap = argparse.ArgumentParser(
        prog="install.py",
        description="PowerShell のプロファイルに llm-assist-kit の関数を登録します。",
    )
    ap.add_argument("--uninstall", action="store_true", help="登録した関数を外す")
    ap.add_argument("--print", action="store_true", help="書き込む内容を表示するだけ")
    ap.add_argument(
        "--profile",
        action="append",
        type=Path,
        metavar="FILE",
        help="書き込むプロファイル (複数可。既定: 見つかった PowerShell すべての $PROFILE.CurrentUserAllHosts)",
    )
    ap.add_argument(
        "--python",
        default=sys.executable,
        help=f"関数から使う Python (既定: いま実行している {sys.executable})",
    )
    ap.add_argument(
        "--set-execution-policy",
        action="store_true",
        help="実行ポリシーが Restricted などでプロファイルが読み込まれないとき、"
        "現在のユーザーだけ RemoteSigned にする",
    )
    args = ap.parse_args(argv)

    block = render_block(FUNCTIONS, args.python, KIT)
    if args.print:
        sys.stdout.write(block)
        return 0

    if args.profile:
        targets = [("(指定)", p) for p in args.profile]
    else:
        targets = find_profiles()
        if not targets:
            print(
                "エラー: PowerShell (powershell / pwsh) が見つかりません。"
                "--profile でプロファイルのパスを指定してください。"
            )
            return 1

    for shell, path in targets:
        text, encoding, newline = read_profile(path)
        new_text = replace_block(text, None if args.uninstall else block)
        if new_text == text:
            state = "変更なし"
        else:
            write_profile(path, new_text, encoding, newline)
            state = "外しました" if args.uninstall else "登録しました"
        print(f"[{shell}] {path}: {state}")

    if args.uninstall:
        return 0

    print()
    for f in FUNCTIONS:
        print(f"  {f.name:<8} {f.description}")

    # 実行ポリシーの確認 (プロファイルを指定したときは確認しない)
    if not args.profile:
        for shell, _ in targets:
            policy = execution_policy(shell)
            if policy not in BLOCKING_POLICIES:
                continue
            command = "Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force"
            if args.set_execution_policy:
                run_powershell(shell, command)
                print(
                    f"\n[{shell}] 実行ポリシーを {policy} から RemoteSigned (現在のユーザー) にしました"
                )
            else:
                print(
                    f"\n注意 [{shell}]: 実行ポリシーが {policy} のため、プロファイルが読み込まれず関数を使えません。"
                    f"\n  次を PowerShell で実行するか、--set-execution-policy を付けて再実行してください:\n  {command}"
                )

    print(
        "\nPowerShell を開き直すと使えます (今のウィンドウでは `. $PROFILE` で読み込めます)。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
