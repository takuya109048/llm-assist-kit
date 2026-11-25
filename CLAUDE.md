# Python プロジェクトのルール

## パッケージ管理

このプロジェクトは pip と標準ライブラリの `venv` を使います。uv、pip-tools、
poetry、conda は使わないでください。ロックファイルはありません。

- 環境を作る: `python -m venv .venv`
- 有効化する: `source .venv/bin/activate` (Windows: `.venv\Scripts\activate`)
- プロジェクトと開発ツールを (editable で) インストールする: `pip install -e ".[dev]"`
- 実行時の依存関係は `pyproject.toml` の `[project] dependencies` に書く
- 開発ツール (pytest、ruff、pyrefly) は `[project.optional-dependencies] dev` に書く
- `pyproject.toml` の依存関係を変えたら、`pip install -e ".[dev]"` を再実行する
- `ctx.py` は標準ライブラリだけを使う単一ファイルのままにすること。ユーザーは
  何もインストールせずに他のプロジェクトで実行します。実行時の依存関係を追加しないこと。
- スキルは対象プロジェクトではなく `skills/<name>/` (`SKILL.md` と任意のスクリプト) に
  置く。スキルのスクリプトも標準ライブラリだけを使う。`SKILL.md` では、パスを
  `${SKILL_DIR}/...`、実行コマンドを `python ${CTX} run -- ...` と書く。
- `skills/apply-patch/apply_patch.zip` にはビルド済みの codex-rs `apply_patch` バイナリが
  入っている。手で編集せず、`python tools/build_apply_patch.py` で再ビルドすること
  (rustup、git、mingw-w64 が必要)。`.build/` と `skills/apply-patch/.bin/` はコミットしない。

## コードの実行

すべて有効化した `.venv` の中で実行するか、`.venv/bin/` 経由でツールを呼ぶ
(例: `.venv/bin/pytest`)。パッケージをグローバルにインストールしないこと。

- スクリプトを実行する: `python script.py`
- モジュールを実行する: `python -m module_name`
- ツールを実行する: `python ctx.py --list` (プレビュー) または `python ctx.py --stdout`
- コマンドを実行し、その結果を LLM 用にコピーする: `python ctx.py run -- <command>`
- PowerShell 関数 (`ctx` など) をユーザーのプロファイルに登録する:
  `python install.py` (`--print` でブロックを表示、`--uninstall` で削除)。
  関数を追加するには、`install.py` の `FUNCTIONS` に `PSFunction` を追加する。
  関数はこのキット内の標準ライブラリのみの Python スクリプトを指すこと。新しい
  関数用スクリプトは `commands/` に置く (例: `commands/addcommit.py`)。

## 新規プロジェクトの作成

- メタデータには必ず `pyproject.toml` を使う (PEP 621)。`setup.py`、
  `setup.cfg`、`requirements.txt` は決して作らない。
- ビルドバックエンド: setuptools (`setuptools.build_meta`)

## テスト

- フレームワーク: pytest
- テストを実行する: `pytest`
- テストファイルはプロジェクトルートの `tests/` に置く
- テストファイル名: `test_*.py`
- テスト関数名: `test_*`
- `tests/` に `__init__.py` は不要
- 意図した出力の変更後は、`examples/sample-context.md` と `examples/sample-run-result.md`
  を再生成する:
  `CTX_UPDATE_EXAMPLE=1 pytest tests/test_example.py`
- Windows 固有の動作 (クリップボード) は `windows-latest` の CI ジョブでテストする。
  このジョブはマトリクスから外さないこと

## 継続的インテグレーションの設定

GitHub Actions では `actions/setup-python` を使い、その後 `pip install -e ".[dev]"` を実行する。

## リントとフォーマット

- ツール: ruff (リントとフォーマットの両方を担当)
- リント: `ruff check .`
- リントと自動修正: `ruff check --fix .`
- フォーマット: `ruff format .`
- フォーマットの確認: `ruff format --check .`
- 設定は `pyproject.toml` の `[tool.ruff]` に書く

## 型チェック

- ツール: pyrefly
- 実行: `pyrefly check`
- 設定は `pyproject.toml` の `[tool.pyrefly]` に書く

## コードスタイル

- フォーマットは ruff のデフォルトに従う (1 行 88 文字、ダブルクォート、スペース)
- import の並び替えは ruff が行う (`select = ["I"]` で `isort` ルールを有効化)
- エラーコードなしの `# type: ignore` コメントを追加しない

## 避けること

- uv (`uv`、`uvx`、`uv.lock`、`uv_build`) を使わない。
- パッケージをグローバルや `.venv` の外にインストールしない。
- 依存関係の管理に `requirements.txt` を作らない。`pyproject.toml` を使う。
- `python setup.py` コマンドを実行しない。
