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

このプロジェクトには、以下のスキル (作業手順と補助スクリプト) があります。
依頼内容に合うスキルがあれば、その手順に従ってください。

- あなたはスクリプトやコマンドを直接実行できません。実行が必要なときは、
  ユーザーが PowerShell で実行するコマンドを powershell のコードブロックで示し、実行を依頼してください。
- 実行結果を見る必要があるときは、コマンドの前に `python ctx.py run --` を付けてください。
  ユーザーが実行すると、コマンド・終了コード・出力が「## 実行結果」の形でクリップボードにコピーされ、
  このチャットに貼り付けられます。例:

  ```powershell
  python ctx.py run -- python -m pytest -q
  ```
- 結果が貼られるまで、実行結果を推測で決めつけないでください。

## スキル: run-tests

- 説明: コードを変更したら、ユーザーにテストを実行してもらい結果を確認する
- フォルダ: `.ctx/skills/run-tests/`

コードの変更を提案したら、最後に必ず次のコマンドの実行をユーザーに依頼してください。

```powershell
python ctx.py run -- python -m pytest -q
```

貼られた結果を見て:

1. 終了コードが 0 なら完了です。
2. 失敗したテストがあれば、エラーメッセージから原因を説明し、修正案を出してください。
   修正後はもう一度同じコマンドの実行を依頼してください。

## スキル: todo-stats

- 説明: todo.json の中身を集計する (件数・完了率・古い未完了タスク)
- フォルダ: `.ctx/skills/todo-stats/`
- ファイル: `.ctx/skills/todo-stats/stats.py`

ToDo データについて質問されたら、推測せずに集計スクリプトの実行をユーザーに依頼してください。

```powershell
python ctx.py run -- python .ctx/skills/todo-stats/stats.py todo.json
```

- 引数はデータファイルのパスです (既定の保存先は `todo.json`)。
- 7 日以上前に作られた未完了タスクを「古いタスク」として表示します。

# プロジェクト: sample-project

## ディレクトリツリー

```text
sample-project/
├── .ctx/
│   └── skills/
│       └── todo-stats/
│           └── stats.py
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
│   │   ├── sample-todo.json
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

## ソースコード (18 ファイル)

### .ctx/skills/todo-stats/stats.py

```python
"""todo.json を集計して表示する (todo-stats スキル用)

使い方: python stats.py [todo.json] [--today YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="todo.json")
    parser.add_argument("--today", help="基準日 (既定: 今日)")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"ファイルがありません: {path}")
        return 1
    tasks = json.loads(path.read_text(encoding="utf-8"))
    today = date.fromisoformat(args.today) if args.today else date.today()

    done = [t for t in tasks if t.get("done")]
    print(f"タスク数: {len(tasks)}")
    if tasks:
        print(f"完了: {len(done)} ({len(done) / len(tasks):.0%})")
    print("古い未完了タスク (7 日以上):")
    stale = 0
    for t in tasks:
        created = datetime.fromisoformat(t["created_at"]).date()
        age = (today - created).days
        if not t.get("done") and age >= 7:
            print(f"  #{t['id']} {t['title']} ({age} 日前)")
            stale += 1
    if stale == 0:
        print("  なし")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

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

### tests/fixtures/sample-todo.json

```json
[
  {"id": 1, "title": "牛乳を買う", "done": true, "created_at": "2026-11-01T09:00:00"},
  {"id": 2, "title": "本を返す", "done": false, "created_at": "2026-11-10T12:30:00"},
  {"id": 3, "title": "部屋の掃除", "done": false, "created_at": "2026-11-20T18:00:00"}
]
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
