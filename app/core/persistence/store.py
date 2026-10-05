
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from app.core.models.task import PhysicalTask, TaskState
from app.integrations.providers.base import ProviderError, ProviderErrorCode, ProviderResult, ProviderStatus


class ExecutionStore:
    """Small atomic JSON store for sandbox execution recovery.

    Records are written with os.replace so a crash cannot leave a partially
    written JSON document. An IN_FLIGHT record is a deliberate recovery fence:
    after a process restart it is never resubmitted automatically.
    """

    def __init__(self, root: str | os.PathLike[str] | None = None):
        configured = root if root is not None else os.getenv("SANOVA_STATE_DIR")
        self.root = Path(configured) if configured else None
        self._memory: dict[str, dict] = {}
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        if self.root is None:
            raise RuntimeError("filesystem path is unavailable for in-memory store")
        safe_id = str(task_id).replace("/", "_").replace("\\", "_")
        return self.root / f"{safe_id}.json"

    def get(self, task_id: str) -> dict | None:
        if self.root is None:
            record = self._memory.get(task_id)
            return json.loads(json.dumps(record)) if record is not None else None
        path = self._path(task_id)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def put(self, task: PhysicalTask, result: ProviderResult | None, phase: str) -> None:
        record = {
            "version": 1,
            "phase": phase,
            "task": {
                "id": task.id,
                "intent": task.intent,
                "provider": task.provider,
                "state": task.state.value,
                "external_id": task.external_id,
                "action": task.action,
                "product": task.product,
                "asset": task.asset,
                "destination": task.destination,
                "quantity": task.quantity,
                "owner_id": task.owner_id,
            },
            "result": self._result_to_dict(result) if result is not None else None,
        }
        if self.root is None:
            self._memory[task.id] = record
            return
        self._atomic_write(self._path(task.id), record)

    def _atomic_write(self, path: Path, record: dict) -> None:
        fd, tmp_name = tempfile.mkstemp(prefix=".sanova-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(record, handle, separators=(",", ":"), sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    @staticmethod
    def _result_to_dict(result: ProviderResult) -> dict:
        return {
            "accepted": result.accepted,
            "status": result.status.value if result.status else None,
            "external_id": result.external_id,
            "message": result.message,
            "error": (
                {
                    "code": result.error.code.value,
                    "message": result.error.message,
                    "retryable": result.error.retryable,
                }
                if result.error
                else None
            ),
        }

    @staticmethod
    def result_from_dict(data: dict | None) -> ProviderResult | None:
        if data is None:
            return None
        error_data = data.get("error")
        error = (
            ProviderError(
                ProviderErrorCode(error_data["code"]),
                error_data["message"],
                bool(error_data.get("retryable", False)),
            )
            if error_data
            else None
        )
        status = ProviderStatus(data["status"]) if data.get("status") else None
        return ProviderResult(
            bool(data["accepted"]),
            status=status,
            external_id=data.get("external_id"),
            message=data.get("message", ""),
            error=error,
        )

    @staticmethod
    def restore_task(task: PhysicalTask, data: dict) -> PhysicalTask:
        stored = data["task"]
        if stored["id"] != task.id:
            raise ValueError("persisted task id mismatch")
        task.state = TaskState(stored["state"])
        return task
