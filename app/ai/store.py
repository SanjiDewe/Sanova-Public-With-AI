from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any


class AIConversationStore:
    def __init__(self, root: str | os.PathLike[str] | None = None):
        configured = root if root is not None else os.getenv("SANOVA_AI_STATE_DIR")
        self.root = Path(configured) if configured else None
        self._memory: dict[str, dict[str, Any]] = {}
        self._lock = RLock()
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)

    def get(self, conversation_id: str) -> dict[str, Any] | None:
        with self._lock:
            if self.root is None:
                value = self._memory.get(conversation_id)
                return json.loads(json.dumps(value)) if value else None
            path = self._path(conversation_id)
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))

    def put(self, conversation_id: str, value: dict[str, Any]) -> None:
        with self._lock:
            if self.root is None:
                self._memory[conversation_id] = json.loads(json.dumps(value))
                return
            path = self._path(conversation_id)
            fd, temp_name = tempfile.mkstemp(prefix=".sanova-ai-", suffix=".tmp", dir=path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(value, handle, separators=(",", ":"), sort_keys=True)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, path)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)

    def _path(self, conversation_id: str) -> Path:
        safe = "".join(char for char in str(conversation_id) if char.isalnum() or char in "-_" )
        if not safe:
            raise ValueError("conversation id is required")
        return self.root / f"{safe}.json"
