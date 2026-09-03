"""Administration of organisation-specific workflow definitions."""
from __future__ import annotations

from fastdps.database import Database, get_database
from fastdps.rbac.service import ALL_KEYS
from fastdps.security import Actor
from fastdps.services.common import audit, now, uid


class WorkflowService:
    def __init__(self, db: Database | None = None):
        self.db = db or get_database()

    def list(self, actor: Actor) -> list[dict]:
        actor.require("org.manage")
        records = self.db.rows("SELECT * FROM workflow_definitions WHERE organisation_id=? ORDER BY name", (actor.organisation_id,))
        for record in records:
            record["steps"] = self.db.rows("SELECT * FROM workflow_steps WHERE workflow_id=? ORDER BY sort_order", (record["id"],))
            record["transitions"] = self.db.rows("SELECT * FROM workflow_transitions WHERE workflow_id=? ORDER BY from_step,to_step", (record["id"],))
        return records

    def create(self, actor: Actor, name: str, entity_type: str) -> dict:
        actor.require("org.manage")
        workflow_id = uid()
        with self.db.transaction() as tx:
            tx.execute("INSERT INTO workflow_definitions(id,organisation_id,name,entity_type,is_default,created_at) VALUES (?,?,?,?,0,?)",
                       (workflow_id, actor.organisation_id, name.strip(), entity_type.strip(), now()))
            audit(tx, actor.organisation_id, actor.user_id, "workflow.created", "workflow", workflow_id)
        return next(item for item in self.list(actor) if item["id"] == workflow_id)

    def add_step(self, actor: Actor, workflow_id: str, key: str, name: str, permission: str, order: int) -> dict:
        actor.require("org.manage")
        if permission not in ALL_KEYS:
            raise ValueError("Unknown permission")
        workflow = self.db.one("SELECT id FROM workflow_definitions WHERE id=? AND organisation_id=?", (workflow_id, actor.organisation_id))
        if not workflow:
            raise LookupError("Workflow not found")
        step_id = uid()
        with self.db.transaction() as tx:
            tx.execute("INSERT INTO workflow_steps(id,workflow_id,step_key,name,required_permission,sort_order) VALUES (?,?,?,?,?,?)",
                       (step_id, workflow_id, key.strip(), name.strip(), permission, int(order)))
            audit(tx, actor.organisation_id, actor.user_id, "workflow.step_added", "workflow", workflow_id, {"step": key})
        return self.db.one("SELECT * FROM workflow_steps WHERE id=?", (step_id,))

    def add_transition(self, actor: Actor, workflow_id: str, from_step: str, to_step: str,
                       action_name: str, permission: str) -> dict:
        actor.require("org.manage")
        if permission not in ALL_KEYS:
            raise ValueError("Unknown permission")
        workflow = self.db.one(
            "SELECT id FROM workflow_definitions WHERE id=? AND organisation_id=?",
            (workflow_id, actor.organisation_id),
        )
        if not workflow:
            raise LookupError("Workflow not found")
        step_keys = {
            row["step_key"] for row in self.db.rows(
                "SELECT step_key FROM workflow_steps WHERE workflow_id=?", (workflow_id,)
            )
        }
        if from_step not in step_keys or to_step not in step_keys:
            raise ValueError("Both transition steps must belong to this workflow")
        if from_step == to_step:
            raise ValueError("A transition must change the workflow step")
        if self.db.one(
            "SELECT id FROM workflow_transitions WHERE workflow_id=? AND from_step=? AND to_step=?",
            (workflow_id, from_step, to_step),
        ):
            raise ValueError("This workflow transition already exists")
        transition_id = uid()
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO workflow_transitions(id,workflow_id,from_step,to_step,action_name,required_permission) "
                "VALUES (?,?,?,?,?,?)",
                (transition_id, workflow_id, from_step, to_step, action_name.strip(), permission),
            )
            audit(
                tx, actor.organisation_id, actor.user_id, "workflow.transition_added", "workflow", workflow_id,
                {"from": from_step, "to": to_step},
            )
        return self.db.one("SELECT * FROM workflow_transitions WHERE id=?", (transition_id,))
