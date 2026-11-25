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
