from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class AuditLogger:
    def __init__(self, log_path: str = "logs/audit.jsonl") -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, payload: Dict[str, Any]) -> str:
        audit_id = str(uuid.uuid4())
        record = {
            "audit_id": audit_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        with self.log_path.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")
        return audit_id
