---
name: todo-stats
description: todo.json の中身を集計する (件数・完了率・古い未完了タスク)
---
ToDo データについて質問されたら、推測せずに集計スクリプトの実行をユーザーに依頼してください。

```powershell
python ctx.py run -- python ${SKILL_DIR}/stats.py todo.json
```

- 引数はデータファイルのパスです (既定の保存先は `todo.json`)。
- 7 日以上前に作られた未完了タスクを「古いタスク」として表示します。
