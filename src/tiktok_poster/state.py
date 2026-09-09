from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass(slots=True)
class PostRecord:
    key: str
    title: str
    publish_id: str
    posted_at: str
    status: str = "SENT"

    def to_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "title": self.title,
            "publish_id": self.publish_id,
            "posted_at": self.posted_at,
            "status": self.status,
        }


@dataclass(slots=True)
class State:
    records: list[PostRecord] = field(default_factory=list)

    @property
    def posted_keys(self) -> set[str]:
        return {record.key for record in self.records}

    def add(self, key: str, title: str, publish_id: str, status: str = "SENT") -> PostRecord:
        record = PostRecord(
            key=key,
            title=title,
            publish_id=publish_id,
            posted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            status=status,
        )
        self.records.append(record)
        return record


def load_state(path: Path) -> State:
    if not path.exists():
        return State()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return State()
    records = [
        PostRecord(
            key=str(item.get("key", "")),
            title=str(item.get("title", "")),
            publish_id=str(item.get("publish_id", "")),
            posted_at=str(item.get("posted_at", "")),
            status=str(item.get("status", "SENT")),
        )
        for item in payload.get("records", [])
        if isinstance(item, dict) and item.get("key")
    ]
    return State(records=records)


def save_state(path: Path, state: State) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"records": [record.to_dict() for record in state.records]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
