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
