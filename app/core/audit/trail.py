from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from time import time
from uuid import uuid4


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    timestamp: float
    event_type: str
    task_id: str
    execution_id: str | None = None
    state: str | None = None
    provider: str | None = None
    outcome: str | None = None
    reason: str | None = None
    metadata: dict | None = None
    previous_hash: str = ""
    event_hash: str = ""

    def payload(self) -> dict:
        data = asdict(self)
        data.pop("event_hash", None)
        return data


class AuditTrail:
    """Append-only, hash-chained audit trail.

    Audit records are observational only: they never determine execution state.
    With a filesystem root, each event is one JSON line and writes are flushed
    and fsynced before the append call returns.
    """

    def __init__(self, root: str | os.PathLike[str] | None = None):
        configured = root if root is not None else os.getenv("SANOVA_AUDIT_DIR")
        self.root = Path(configured) if configured else None
        self._events: list[dict] = []
        self._lock = RLock()
        self._last_hash = ""
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path | None:
        return self.root / "audit.jsonl" if self.root is not None else None

    def append(
        self,
        event_type: str,
        task_id: str,
        *,
        execution_id: str | None = None,
        state: str | None = None,
        provider: str | None = None,
        outcome: str | None = None,
        reason: str | None = None,
        metadata: dict | None = None,
    ) -> AuditEvent:
        with self._lock:
            event = AuditEvent(
                event_id=str(uuid4()),
                timestamp=time(),
                event_type=event_type,
                task_id=str(task_id),
                execution_id=execution_id,
                state=state,
                provider=provider,
                outcome=outcome,
                reason=reason,
                metadata=dict(metadata) if metadata else None,
                previous_hash=self._last_hash,
            )
            digest = hashlib.sha256(
                json.dumps(event.payload(), sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            event = AuditEvent(**{**asdict(event), "event_hash": digest})
            record = asdict(event)
            if self.root is None:
                self._events.append(record)
            else:
                self._append_file(record)
            self._last_hash = digest
            return event

    def events(self, task_id: str | None = None) -> list[AuditEvent]:
        with self._lock:
            records = list(self._events)
            if self.root is not None and self.path and self.path.exists():
                with self.path.open("r", encoding="utf-8") as handle:
                    records = [json.loads(line) for line in handle if line.strip()]
            if task_id is not None:
                records = [r for r in records if r["task_id"] == str(task_id)]
            return [AuditEvent(**r) for r in records]

    def verify(self) -> bool:
        events = self.events()
        previous = ""
        for event in events:
            if event.previous_hash != previous:
                return False
            expected = hashlib.sha256(
                json.dumps(event.payload(), sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if event.event_hash != expected:
                return False
            previous = event.event_hash
        return True

    def _append_file(self, record: dict) -> None:
        assert self.path is not None
        # JSONL append is deliberately the only filesystem operation exposed.
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def default_audit_trail() -> AuditTrail:
    return AuditTrail()
