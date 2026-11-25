`TaskStore` にタスクを削除する `remove` を追加し、そのテストを追加します。

- `src/todo/storage.py`: `remove(task_id)` を追加 (存在しない ID はエラー)
- `tests/test_remove.py`: 新規作成

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
@'
*** Begin Patch
*** Update File: src/todo/storage.py
@@ def complete(self, task_id: int) -> Task:
                 self.save(tasks)
                 return task
         raise KeyError(f"タスク {task_id} は存在しません")
+
+    def remove(self, task_id: int) -> None:
+        tasks = self.load()
+        remaining = [t for t in tasks if t.id != task_id]
+        if len(remaining) == len(tasks):
+            raise KeyError(f"タスク {task_id} は存在しません")
+        self.save(remaining)
*** Add File: tests/test_remove.py
+from pathlib import Path
+
+import pytest
+from todo.storage import TaskStore
+
+
+def test_remove(tmp_path: Path) -> None:
+    store = TaskStore(tmp_path / "todo.json")
+    store.add("牛乳を買う")
+    store.add("本を返す")
+    store.remove(1)
+    assert [t.title for t in store.load()] == ["本を返す"]
+
+
+def test_remove_missing(tmp_path: Path) -> None:
+    with pytest.raises(KeyError):
+        TaskStore(tmp_path / "todo.json").remove(99)
*** End Patch
'@ | python C:/tools/llm-assist-kit/ctx.py run -- python C:/tools/llm-assist-kit/skills/apply-patch/apply.py -f -
```
