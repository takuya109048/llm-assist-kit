あなたはこの「todo-cli」プロジェクトの開発を手伝うシニア Python エンジニアです。
以下にディレクトリツリーと全ソースコードを貼ります。

# プロジェクト概要
- コマンドラインで使う ToDo 管理ツール。データは JSON ファイルに保存する
- `web/` は同じ JSON を表示するだけの簡易ビューア

# 開発ルール
- Python 3.11+、標準ライブラリのみ(外部依存を追加しない)
- テストは pytest。変更を提案するときはテストも一緒に書く
- 型ヒントを必ず付ける

# 回答のしかた
- 日本語で答える
- コードを変更するときは、ファイルパスと変更後のコード全体を示す
- このメッセージには「了解しました」とだけ返し、次の依頼を待つ

# スキル

以下のスキル (作業手順と補助スクリプト) が使えます。
依頼内容に合うスキルがあれば、その手順に従ってください。

- あなたはスクリプトやコマンドを直接実行できません。実行が必要なときは、
  ユーザーが PowerShell で実行するコマンドを powershell のコードブロックで示し、実行を依頼してください。
- 実行結果を見る必要があるときは、コマンドの前に `python C:/tools/llm-assist-kit/ctx.py run --` を付けてください。
  ユーザーが実行すると、コマンド・終了コード・出力が「## 実行結果」の形でクリップボードにコピーされ、
  このチャットに貼り付けられます。例:

  ```powershell
  python C:/tools/llm-assist-kit/ctx.py run -- python -m pytest -q
  ```
- 結果が貼られるまで、実行結果を推測で決めつけないでください。

## スキル: apply-patch

- 説明: ファイルの修正・新規作成・削除・移動をパッチ (codex の apply_patch 形式) で出し、ユーザーにまとめて適用してもらう
- フォルダ: `C:/tools/llm-assist-kit/skills/apply-patch/`
- ファイル: `C:/tools/llm-assist-kit/skills/apply-patch/apply.py`, `C:/tools/llm-assist-kit/skills/apply-patch/apply_patch.zip`

ファイルを変更するときは、変更後のファイル全体を貼るのではなく、下の形式のパッチを 1 つのコードブロックで出してください。
ユーザーはあなたの回答をコピーして次のコマンドを実行します。パッチ部分だけが取り出され、
codex-rs の `apply_patch` でプロジェクトに適用され、結果がクリップボード経由で貼り返されます。

```powershell
python C:/tools/llm-assist-kit/ctx.py run -- python C:/tools/llm-assist-kit/skills/apply-patch/apply.py
```

## パッチの形式

```text
*** Begin Patch
*** Add File: <パス>
+<新しいファイルの 1 行目>
+<2 行目>
*** Update File: <パス>
*** Move to: <新しいパス>      (名前を変えるときだけ)
@@ <変更箇所を特定する行 (関数名やクラス名など)。不要なら @@ だけ>
 <変更しない前後の行 (先頭は半角スペース)>
-<削除する行>
+<追加する行>
 <変更しない前後の行>
*** Delete File: <パス>
*** End Patch
```

- 1 つのパッチに、複数のファイルの操作をまとめて書けます。
- `*** Add File:` は新規作成。続く行はすべて `+` で始めます (空行も `+` だけの行にする)。
- `*** Update File:` は既存ファイルの修正。変更箇所ごとに `@@` で区切り、変更行の前後に
  変更しない行を 3 行ずつ (先頭は半角スペース) 入れて、場所を一意に特定できるようにします。
  3 行で一意にならなければ `@@ class Foo` や `@@ def bar():` のように、近くの定義行を `@@` の後ろに書きます。
- `-` と半角スペースで始まる行は、現在のファイルの内容と 1 文字も違わないように書きます (インデントも同じ)。
- ファイルの末尾を変更するときは、最後に `*** End of File` を書けます。
- `*** Delete File:` は削除。後ろには何も書きません。
- パスはプロジェクトのルートからの相対パスで書きます (絶対パスや `..` は使えません)。

## 適用結果の確認

- 成功すると `Success. Updated the following files:` と、変更したファイル (`A` 追加 / `M` 修正 / `D` 削除) が貼られます。
- 失敗した場合 (例: `Failed to find expected lines`) は、そのファイルの現在の内容が想定と違います。
  失敗したときは、そのパッチによる変更はすべて元に戻されています (途中まで適用された状態は残りません)。
  推測でパッチを出し直さず、search スキルなどで現在の内容を確認してから、正しいパッチを出してください。
- 適用後、必要に応じて git-diff スキルで差分を、run-tests スキルでテスト結果を確認してください。

## スキル: git-diff

- 説明: ユーザーが変更を反映した後、git の差分を見せてもらって提案どおりか確認する
- フォルダ: `C:/tools/llm-assist-kit/skills/git-diff/`
- ファイル: `C:/tools/llm-assist-kit/skills/git-diff/diff.py`

あなたが提案した変更をユーザーが反映したら、提案どおりに反映されたか確認するため、
差分の表示をユーザーに依頼してください。

```powershell
python C:/tools/llm-assist-kit/ctx.py run -- python C:/tools/llm-assist-kit/skills/git-diff/diff.py
```

- 特定のファイルだけ見たいときは、パスを後ろに付けます (例: `... diff.py src/app.py`)。
- 出力は「変更されたファイル一覧 (git status)」「変更量 (git diff --stat)」「差分本体」の順です。
- 差分が提案と違っていれば、どこが違うかを具体的に指摘してください。

## スキル: run-tests

- 説明: コードの変更を提案したら、ユーザーにテストを実行してもらい結果を確認する
- フォルダ: `C:/tools/llm-assist-kit/skills/run-tests/`

コードの変更を提案したら、最後にテストの実行をユーザーに依頼してください。
Python (pytest) のプロジェクトなら次のコマンドです。ほかの言語やツールのプロジェクトでは、
README や設定ファイル (package.json の scripts、Makefile など) から適切なテストコマンドを選んでください。

```powershell
python C:/tools/llm-assist-kit/ctx.py run -- python -m pytest -q
```

貼られた「## 実行結果」を見て:

1. 終了コードが 0 なら完了です。
2. 失敗したテストがあれば、エラーメッセージから原因を説明し、修正案を出してください。
   修正後はもう一度同じコマンドの実行を依頼してください。
3. テストの出力が途中で省略されていて原因が分からなければ、
   失敗したテストだけを実行するコマンド (例: `python -m pytest -q tests/test_x.py::test_y`) を依頼してください。

## スキル: search

- 説明: プロジェクト内を文字列や正規表現で検索して、該当箇所を見せてもらう
- フォルダ: `C:/tools/llm-assist-kit/skills/search/`
- ファイル: `C:/tools/llm-assist-kit/skills/search/search.py`

貼られたコンテキストだけでは分からない箇所 (コンテキストから外したファイル、
使われている場所の一覧、最新の内容など) を確認したいときは、検索の実行をユーザーに依頼してください。

```powershell
python C:/tools/llm-assist-kit/ctx.py run -- python C:/tools/llm-assist-kit/skills/search/search.py "検索する文字列"
```

- 既定は正規表現です。`-F` で文字列そのまま、`-i` で大文字小文字を区別しません。
- `-g "*.py"` で対象ファイルを絞り込めます (複数可)。検索するフォルダを最後に付けられます (既定: 今いるフォルダ)。
- `-C 2` で前後 2 行も表示します。
- git 管理下なら .gitignore を尊重します。結果は `パス:行番号: 内容` の形で、最大 200 件です。

# プロジェクト: sample-project

## ディレクトリツリー

```text
sample-project/
├── config/
│   └── stage/
│       └── prod.local.toml
├── docs/
│   ├── draft10.md
│   └── TODO.md
├── src/
│   └── todo/
│       ├── __init__.py
│       ├── cli.py
│       ├── models.py
│       ├── scratch_a.py
│       └── storage.py
├── tests/
│   ├── fixtures/
│   │   └── tmp
│   └── test_storage.py
├── web/
│   ├── app.js
│   └── index.html
├── .gitignore
├── keep.bak
├── pyproject.toml
└── README.md
```

## ソースコード (16 ファイル)

### .gitignore

```gitignore
__pycache__/
.venv/
*.log
todo.json
```

### config/stage/prod.local.toml

```toml
# 5. * は / をまたがないので config/stage/ 以下は出力に入る
```

### docs/draft10.md

```markdown
# 9. ? は 1 文字だけなので draft10.md は出力に入る
```

### docs/TODO.md

```markdown
# 4. ルート固定ではないので docs/TODO.md は出力に入る
```

### keep.bak

```
2. !keep.bak で含め直されたファイル(出力に入る)
```

### pyproject.toml

```toml
[project]
name = "todo-cli"
version = "0.1.0"
description = "JSON ファイルに保存するシンプルな ToDo 管理ツール"
requires-python = ">=3.11"
dependencies = []

[project.scripts]
todo = "todo.cli:main"

[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"
```

### README.md

````markdown
# todo-cli

JSON ファイルに保存するシンプルな ToDo 管理ツールです。

## 使い方

```bash
todo add "牛乳を買う"
todo list
todo done 1
```

保存先は環境変数 `TODO_FILE` で変更できます(既定: `./todo.json`)。
````

### src/todo/__init__.py

```python
"""シンプルな ToDo 管理ツール"""

__version__ = "0.1.0"
```

### src/todo/cli.py

```python
from __future__ import annotations

import argparse
import os
from pathlib import Path

from todo.storage import TaskStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="todo")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add", help="タスクを追加")
    add.add_argument("title")
    sub.add_parser("list", help="タスク一覧")
    done = sub.add_parser("done", help="タスクを完了にする")
    done.add_argument("id", type=int)
    args = parser.parse_args(argv)

    store = TaskStore(Path(os.environ.get("TODO_FILE", "todo.json")))
    if args.command == "add":
        task = store.add(args.title)
        print(f"追加しました: #{task.id} {task.title}")
    elif args.command == "list":
        for task in store.load():
            mark = "x" if task.done else " "
            print(f"[{mark}] #{task.id} {task.title}")
    elif args.command == "done":
        task = store.complete(args.id)
        print(f"完了しました: #{task.id} {task.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### src/todo/models.py

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class Task:
    id: int
    title: str
    done: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Task:
        return cls(
            id=int(str(data["id"])),
            title=str(data["title"]),
            done=bool(data.get("done", False)),
            created_at=str(data.get("created_at", "")),
        )
```

### src/todo/scratch_a.py

```python
"""10. [0-9] に a は含まれないので出力に入る"""
```

### src/todo/storage.py

```python
from __future__ import annotations

import json
from pathlib import Path

from todo.models import Task


class TaskStore:
    """タスクを JSON ファイルに保存・読み込みする"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[Task]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [Task.from_dict(d) for d in data]

    def save(self, tasks: list[Task]) -> None:
        text = json.dumps([t.to_dict() for t in tasks], ensure_ascii=False, indent=2)
        self.path.write_text(text, encoding="utf-8")

    def add(self, title: str) -> Task:
        tasks = self.load()
        task = Task(id=max((t.id for t in tasks), default=0) + 1, title=title)
        tasks.append(task)
        self.save(tasks)
        return task

    def complete(self, task_id: int) -> Task:
        tasks = self.load()
        for task in tasks:
            if task.id == task_id:
                task.done = True
                self.save(tasks)
                return task
        raise KeyError(f"タスク {task_id} は存在しません")
```

### tests/fixtures/tmp

```
3. tmp という名前の「ファイル」。tmp/ はディレクトリ専用なので出力に入る
```

### tests/test_storage.py

```python
from pathlib import Path

import pytest
from todo.storage import TaskStore


def test_add_and_load(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "todo.json")
    store.add("牛乳を買う")
    store.add("本を返す")
    assert [t.title for t in store.load()] == ["牛乳を買う", "本を返す"]
    assert [t.id for t in store.load()] == [1, 2]


def test_complete(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "todo.json")
    task = store.add("牛乳を買う")
    store.complete(task.id)
    assert store.load()[0].done


def test_complete_missing(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        TaskStore(tmp_path / "todo.json").complete(99)
```

### web/app.js

```javascript
// todo.json を読み込んで一覧表示する
async function render() {
  const res = await fetch("../todo.json");
  const tasks = await res.json();
  const list = document.getElementById("tasks");
  for (const task of tasks) {
    const li = document.createElement("li");
    li.textContent = `${task.done ? "✅" : "⬜"} ${task.title}`;
    list.appendChild(li);
  }
}

render();
```

### web/index.html

```html
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>todo viewer</title>
</head>
<body>
  <h1>ToDo</h1>
  <ul id="tasks"></ul>
  <script src="app.js"></script>
</body>
</html>
```
