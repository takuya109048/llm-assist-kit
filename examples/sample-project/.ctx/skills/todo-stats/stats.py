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
