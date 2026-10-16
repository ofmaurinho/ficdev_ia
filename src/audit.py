"""Registro de auditoria e rastreabilidade das execuções."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            lowered = str(key).lower()
            safe_usage_fields = {
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "cached_tokens",
                "reasoning_tokens",
                "cache_write_tokens",
            }
            sensitive_field = any(
                marker in lowered
                for marker in ("api_key", "secret", "password", "authorization", "header")
            ) or ("token" in lowered and lowered not in safe_usage_fields)
            if sensitive_field:
                continue
            sanitized[key] = _safe_value(item)
        return sanitized
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_safe_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class AuditLogger:
    def __init__(self, log_dir: str = "resultados/logs"):
        self.log_dir = log_dir
        self.log_path = Path(log_dir) / "audit.jsonl"
        self.log_dir_path = Path(log_dir)
        self.log_dir_path.mkdir(parents=True, exist_ok=True)

    def log_event(self, event_type: str, status: str, payload: Optional[Dict[str, Any]] = None, *, execution_id: Optional[str] = None) -> str:
        safe_payload = _safe_value(payload or {})
        entry = {
            "execution_id": execution_id or str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "status": status,
            "payload": safe_payload,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry["execution_id"]


class ExecutionAudit:
    def __init__(self, log_dir: str = "resultados/logs"):
        self.logger = AuditLogger(log_dir=log_dir)
        self.execution_id = str(uuid.uuid4())

    def start(self, **kwargs):
        return self.logger.log_event("iniciado", "iniciado", kwargs, execution_id=self.execution_id)

    def success(self, **kwargs):
        return self.logger.log_event("resultado", "sucesso", kwargs, execution_id=self.execution_id)

    def fail(self, **kwargs):
        return self.logger.log_event("resultado", "falha", kwargs, execution_id=self.execution_id)

    def revise(self, **kwargs):
        return self.logger.log_event("revisao", "revisao_pendente", kwargs, execution_id=self.execution_id)
