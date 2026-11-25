## 実行結果

```powershell
PS> python C:/tools/llm-assist-kit/skills/search/search.py TaskStore
```

- 終了コード: 0 (成功)

```text
src/todo/cli.py:7: from todo.storage import TaskStore
src/todo/cli.py:20:     store = TaskStore(Path(os.environ.get("TODO_FILE", "todo.json")))
src/todo/storage.py:9: class TaskStore:
tests/test_storage.py:4: from todo.storage import TaskStore
tests/test_storage.py:8:     store = TaskStore(tmp_path / "todo.json")
tests/test_storage.py:16:     store = TaskStore(tmp_path / "todo.json")
tests/test_storage.py:24:         TaskStore(tmp_path / "todo.json").complete(99)

7 件 / 3 ファイル
```
