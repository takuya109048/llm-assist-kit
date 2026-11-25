"""install.py (PowerShell のプロファイルに関数を登録する初期設定) のテスト"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import install

PYTHON = "C:\\Python\\python.exe"
KIT = Path("C:/tools/llm-assist-kit")


def block() -> str:
    return install.render_block(install.FUNCTIONS, PYTHON, KIT)


def run_install(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    capsys.readouterr()
    code = install.main(list(argv))
    return code, capsys.readouterr().out


# ---------------------------------------------------------------------------
# 書き込む内容
# ---------------------------------------------------------------------------


def test_functions_registry():
    names = [f.name for f in install.FUNCTIONS]
    assert "ctx" in names
    assert len(names) == len(set(names))
    for f in install.FUNCTIONS:
        assert (install.KIT / f.script).is_file(), f.script
        assert f.description


def test_render_block():
    text = block()
    lines = text.splitlines()
    assert lines[0].startswith(install.BEGIN_MARK)
    assert lines[-1] == install.END_MARK
    ctx_py = str(KIT / "ctx.py")
    assert f"function ctx {{ & '{PYTHON}' '{ctx_py}' @args }}" in lines


def test_ps_quote_escapes_single_quote():
    assert install.ps_quote("C:\\O'Brien\\x") == "'C:\\O''Brien\\x'"


# ---------------------------------------------------------------------------
# 管理範囲の差し替え
# ---------------------------------------------------------------------------


def test_replace_block_into_empty_and_existing():
    assert install.replace_block("", block()) == block()
    original = "Set-Alias ll Get-ChildItem\n"
    assert install.replace_block(original, block()) == original + "\n" + block()
    # 末尾に改行が無いプロファイル
    assert install.replace_block("x", block()) == "x\n\n" + block()


def test_replace_block_is_idempotent_and_updates_in_place():
    original = "# before\n" + "\n" + block() + "# after\n"
    assert install.replace_block(original, block()) == original
    new_block = install.render_block(install.FUNCTIONS, "python", Path("D:/kit"))
    updated = install.replace_block(original, new_block)
    assert updated == "# before\n\n" + new_block + "# after\n"
    assert updated.count(install.BEGIN_MARK) == 1


def test_replace_block_remove_restores_original():
    original = "Set-Alias ll Get-ChildItem\n"
    installed = install.replace_block(original, block())
    assert install.replace_block(installed, None) == original
    assert install.replace_block(block(), None) == ""
    # 前後に内容がある場合
    middle = "# a\n\n" + block() + "# b\n"
    assert install.replace_block(middle, None) == "# a\n# b\n"


def test_replace_block_without_end_mark_appends():
    broken = "# x\n" + install.BEGIN_MARK + "\n"
    assert install.replace_block(broken, block()).endswith(block())


# ---------------------------------------------------------------------------
# 文字コード
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "encoding"),
    [
        ("\ufeff# 日本語\r\n".encode(), "utf-8-sig"),
        ("# 日本語\r\n".encode("utf-16"), "utf-16"),
        ("# 日本語\r\n".encode("cp932"), "cp932"),
        (b"# ascii\n", "utf-8"),
    ],
)
def test_read_profile_detects_encoding(tmp_path: Path, raw: bytes, encoding: str):
    p = tmp_path / "profile.ps1"
    p.write_bytes(raw)
    text, enc, _ = install.read_profile(p)
    assert enc == encoding
    assert "\r" not in text


def test_write_keeps_encoding_and_newlines(tmp_path: Path):
    p = tmp_path / "profile.ps1"
    p.write_bytes("# 日本語\r\n".encode("cp932"))
    text, enc, nl = install.read_profile(p)
    install.write_profile(p, install.replace_block(text, block()), enc, nl)
    data = p.read_bytes()
    assert b"\r\n" in data and b"\n\n" not in data.replace(b"\r\n", b"")
    assert data.decode("cp932").startswith("# 日本語\r\n")


def test_utf8_without_bom_gets_bom(tmp_path: Path):
    """Windows PowerShell 5.1 は BOM の無いファイルを ANSI として読むので BOM を付ける"""
    p = tmp_path / "profile.ps1"
    p.write_bytes(b"# ascii\n")
    text, enc, nl = install.read_profile(p)
    install.write_profile(p, install.replace_block(text, block()), enc, nl)
    assert p.read_bytes().startswith(b"\xef\xbb\xbf")


def test_cp932_falls_back_to_utf8_for_unencodable(tmp_path: Path):
    p = tmp_path / "profile.ps1"
    install.write_profile(p, "# \U0001f389\n", "cp932", "\n")
    assert p.read_bytes() == "\ufeff# \U0001f389\n".encode()


def test_new_profile_is_utf8_with_bom(tmp_path: Path):
    p = tmp_path / "sub" / "profile.ps1"
    text, enc, nl = install.read_profile(p)
    assert (text, enc) == ("", "utf-8-sig")
    install.write_profile(p, block(), enc, nl)
    assert p.read_bytes().startswith(b"\xef\xbb\xbf")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def test_install_and_uninstall(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    p = tmp_path / "profile.ps1"
    p.write_text("Set-Alias ll Get-ChildItem\n", encoding="utf-8-sig")

    code, out = run_install(capsys, "--profile", str(p), "--python", PYTHON)
    assert code == 0
    assert "登録しました" in out
    assert "ctx" in out
    text = p.read_text(encoding="utf-8-sig")
    assert text.startswith("Set-Alias ll Get-ChildItem\n")
    assert f"& '{PYTHON}' '{install.KIT / 'ctx.py'}' @args" in text

    code, out = run_install(capsys, "--profile", str(p), "--python", PYTHON)
    assert "変更なし" in out
    assert p.read_text(encoding="utf-8-sig") == text

    code, out = run_install(capsys, "--uninstall", "--profile", str(p))
    assert code == 0
    assert "外しました" in out
    assert p.read_text(encoding="utf-8-sig") == "Set-Alias ll Get-ChildItem\n"


def test_print_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    code, out = run_install(capsys, "--print", "--python", PYTHON)
    assert code == 0
    assert out == install.render_block(install.FUNCTIONS, PYTHON, install.KIT)


def test_no_powershell(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(install.shutil, "which", lambda _: None)
    code, out = run_install(capsys)
    assert code == 1
    assert "PowerShell (powershell / pwsh) が見つかりません" in out


@pytest.fixture
def fake_powershell(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> list[tuple[str, str]]:
    """PowerShell への問い合わせを差し替える。呼ばれたコマンドを記録する"""
    calls: list[tuple[str, str]] = []
    profiles = {
        "powershell": tmp_path / "WindowsPowerShell" / "profile.ps1",
        "pwsh": tmp_path / "PowerShell" / "profile.ps1",
    }

    def fake_run(exe: str, command: str) -> str | None:
        calls.append((exe, command))
        if "$PROFILE" in command:
            return str(profiles[exe])
        if command == "Get-ExecutionPolicy":
            return "Restricted" if exe == "powershell" else "RemoteSigned"
        return ""

    monkeypatch.setattr(install.shutil, "which", lambda exe: exe)
    monkeypatch.setattr(install, "run_powershell", fake_run)
    return calls


def test_installs_into_both_powershells_and_warns_policy(
    fake_powershell: list[tuple[str, str]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    code, out = run_install(capsys)
    assert code == 0
    for d in ("WindowsPowerShell", "PowerShell"):
        assert install.BEGIN_MARK in (tmp_path / d / "profile.ps1").read_text(
            encoding="utf-8-sig"
        )
    assert "注意 [powershell]: 実行ポリシーが Restricted" in out
    assert "Set-ExecutionPolicy -Scope CurrentUser" in out
    assert "注意 [pwsh]" not in out
    # 頼まれていないのに実行ポリシーは変えない
    assert not any("Set-ExecutionPolicy" in c for _, c in fake_powershell)


def test_set_execution_policy_only_when_asked(
    fake_powershell: list[tuple[str, str]], capsys: pytest.CaptureFixture[str]
):
    code, out = run_install(capsys, "--set-execution-policy")
    assert code == 0
    changed = [(e, c) for e, c in fake_powershell if "Set-ExecutionPolicy" in c]
    assert changed == [
        (
            "powershell",
            "Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force",
        )
    ]
    assert "RemoteSigned (現在のユーザー) にしました" in out


# ---------------------------------------------------------------------------
# 実際の PowerShell で、登録した関数が使える
# ---------------------------------------------------------------------------


def available_powershells() -> list[str]:
    return [ps for ps in install.POWERSHELLS if shutil.which(ps)]


@pytest.mark.parametrize("shell", available_powershells() or ["(none)"])
def test_ctx_function_works_in_powershell(shell: str, tmp_path: Path):
    if shell == "(none)":
        pytest.skip("PowerShell が無い")
    profile = tmp_path / "profile.ps1"
    assert install.main(["--profile", str(profile), "--python", sys.executable]) == 0
    project = tmp_path / "proj"
    project.mkdir()
    (project / "a.py").write_text("print('hi')\n", encoding="utf-8")
    command = (
        f". {install.ps_quote(str(profile))}; "
        f"Set-Location {install.ps_quote(str(project))}; "
        "ctx --stdout --no-git --no-prompt --no-skills"
    )
    r = subprocess.run(
        [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
    )
    out = r.stdout.decode("utf-8", errors="replace")
    assert r.returncode == 0, out + r.stderr.decode("utf-8", errors="replace")
    assert "### a.py" in out
    assert "print('hi')" in out


@pytest.mark.parametrize("shell", available_powershells() or ["(none)"])
def test_find_profiles_with_real_powershell(shell: str):
    if shell == "(none)":
        pytest.skip("PowerShell が無い")
    found = dict(install.find_profiles())
    assert found[shell].name == "profile.ps1"
