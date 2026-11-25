## 実行結果

```powershell
PS> python C:/tools/llm-assist-kit/skills/apply-patch/apply.py -f ../sample-llm-answer.md --dry-run
```

- 終了コード: 0 (成功)

```text
パッチ (C:/tools/llm-assist-kit/examples/sample-project に適用):
  更新: src/todo/storage.py
  追加: tests/test_remove.py

--dry-run のため適用していません
```
