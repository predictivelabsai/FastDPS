"""Shared service helpers."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from uuid import uuid4

from fastdps.database import Transaction


def uid() -> str:
    return str(uuid4())


def now() -> str:
    return datetime.now(UTC).isoformat()


def json_dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def json_load(value, default=None):
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or f"organisation-{uuid4().hex[:8]}"


def audit(tx: Transaction, organisation_id: str | None, actor_user_id: str | None,
          action: str, entity_type: str, entity_id: str | None, detail=None) -> None:
    tx.execute(
        "INSERT INTO audit_events(id,organisation_id,actor_user_id,action,entity_type,entity_id,detail_json,created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (uid(), organisation_id, actor_user_id, action, entity_type, entity_id, json_dump(detail or {}), now()),
    )
