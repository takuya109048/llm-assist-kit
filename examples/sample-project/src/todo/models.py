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
