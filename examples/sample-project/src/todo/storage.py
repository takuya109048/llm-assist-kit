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
