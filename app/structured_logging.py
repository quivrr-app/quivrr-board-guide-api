from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any


SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|secret|token|api[_-]?key|connection[_-]?string|authorization)",
    re.IGNORECASE,
)
DEFAULT_PROTECTED_FIELDS = {
    "message",
    "user_message",
    "prompt",
    "page_context",
    "conversation",
    "request_body",
    "content",
}


def utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _sanitize_value(value: Any, protected_fields: set[str] | None = None) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_field(key, item, protected_fields)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_value(item, protected_fields) for item in value]
    return value


def _sanitize_field(name: str, value: Any, protected_fields: set[str] | None = None) -> Any:
    protected = {field.lower() for field in (protected_fields or set())}
    field_name = str(name or "").lower()
    if field_name in protected or field_name in DEFAULT_PROTECTED_FIELDS:
        return "[REDACTED]"
    if SENSITIVE_KEY_PATTERN.search(field_name):
        return "[REDACTED]"
    return _sanitize_value(value, protected_fields)


def build_event(
    event: str,
    service: str,
    region: str | None = None,
    status: str | None = None,
    protected_fields: set[str] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event": event,
        "service": service,
        "timestamp_utc": utc_timestamp(),
    }
    if region:
        payload["region"] = region
    if status:
        payload["status"] = status
    for key, value in fields.items():
        if value is None:
            continue
        payload[key] = _sanitize_field(key, value, protected_fields)
    return payload


def emit_event(
    event: str,
    service: str,
    region: str | None = None,
    status: str | None = None,
    protected_fields: set[str] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    payload = build_event(
        event,
        service,
        region=region,
        status=status,
        protected_fields=protected_fields,
        **fields,
    )
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)
    return payload
