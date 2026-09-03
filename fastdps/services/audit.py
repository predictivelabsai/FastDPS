"""Read-only audit trail queries."""
from __future__ import annotations

from fastdps.database import Database, get_database
from fastdps.security import Actor
from fastdps.services.common import json_load


class AuditService:
    def __init__(self, db: Database | None = None):
        self.db = db or get_database()

    def list(self, actor: Actor, limit: int = 200) -> list[dict]:
        actor.require("audit.view")
        rows = self.db.rows(
            "SELECT a.*,u.email actor_email,u.name actor_name FROM audit_events a LEFT JOIN users u ON u.id=a.actor_user_id "
            "WHERE a.organisation_id=? ORDER BY a.created_at DESC LIMIT ?",
            (actor.organisation_id, max(1, min(int(limit), 500))),
        )
        for row in rows:
            row["detail"] = json_load(row.pop("detail_json"), {})
        return rows
