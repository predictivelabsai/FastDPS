"""Chat orchestration with permission-checked, confirm-before-write tools."""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import httpx

from fastdps.config import settings
from fastdps.database import Database, get_database
from fastdps.security import Actor
from fastdps.services.common import audit, json_dump, json_load, now, uid
from fastdps.services.ocds import OcdsService
from fastdps.services.procurement import ProcurementService


HELP = """I can help you run the full DPS lifecycle. Try:

- `create a DPS for cloud services`
- `list DPS`
- `publish DPS <id>`
- `add category <dps-id> | <code> | <name>`
- `add qualification criterion <dps-id> | <name>`
- `create competition <dps-id> | Laptop call-off`
- `add evaluation criterion <competition-id> | Quality | 60`
- `publish competition <id>`
- `show supplier applications`
- `admit application <id>`
- `create award <competition-id> | <submission-id> | rationale`
- `search notices cloud hosting`
- `show audit activity`

Changes are always previewed and require confirmation."""


class ChatService:
    def __init__(self, db: Database | None = None):
        self.db = db or get_database()
        self.procurement = ProcurementService(self.db)
        self.ocds = OcdsService(self.db)

    def sessions(self, actor: Actor) -> list[dict]:
        actor.require("chat.use")
        return self.db.rows(
            "SELECT * FROM chat_sessions WHERE organisation_id=? AND user_id=? ORDER BY updated_at DESC LIMIT 40",
            (actor.organisation_id, actor.user_id),
        )

    def ensure_session(self, actor: Actor, session_id: str | None = None, title: str = "New conversation") -> dict:
        actor.require("chat.use")
        if session_id:
            existing = self.db.one(
                "SELECT * FROM chat_sessions WHERE id=? AND organisation_id=? AND user_id=?",
                (session_id, actor.organisation_id, actor.user_id),
            )
            if existing:
                return existing
        session_id, timestamp = uid(), now()
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO chat_sessions(id,organisation_id,user_id,title,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                (session_id, actor.organisation_id, actor.user_id, title[:100], timestamp, timestamp),
            )
        return self.db.one("SELECT * FROM chat_sessions WHERE id=?", (session_id,))

    def messages(self, actor: Actor, session_id: str) -> list[dict]:
        self.ensure_session(actor, session_id)
        return self.db.rows("SELECT * FROM chat_messages WHERE session_id=? ORDER BY created_at,id", (session_id,))

    def _message(self, session_id: str, role: str, content: str, event=None) -> None:
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO chat_messages(id,session_id,role,content,event_json,created_at) VALUES (?,?,?,?,?,?)",
                (uid(), session_id, role, content, json_dump(event or {}), now()),
            )
            tx.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (now(), session_id))

    def _pending(self, actor: Actor, session_id: str, action_key: str, payload: dict,
                 permission: str, summary: str) -> tuple[str, dict]:
        actor.require(permission)
        action_id = uid()
        expires = (datetime.now(UTC) + timedelta(minutes=20)).isoformat()
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO chat_pending_actions(id,session_id,organisation_id,requested_by,action_key,payload_json,"
                "required_permission,status,expires_at,created_at) VALUES (?,?,?,?,?,?,?,'pending',?,?)",
                (action_id, session_id, actor.organisation_id, actor.user_id, action_key, json_dump(payload), permission, expires, now()),
            )
            audit(tx, actor.organisation_id, actor.user_id, "chat.action_proposed", "chat_action", action_id, {"action": action_key})
        artifact = {"kind": "confirmation", "title": "Review proposed action", "summary": summary,
                    "action_id": action_id, "confirm_url": f"/api/chat/actions/{action_id}/confirm"}
        return "I prepared this action for review. Nothing has changed yet. Confirm it from the results panel when ready.", artifact

    def respond(self, actor: Actor, message: str, session_id: str | None = None) -> tuple[str, list[tuple[str, dict]]]:
        actor.require("chat.use")
        text = message.strip()
        if not text:
            raise ValueError("Message is required")
        session = self.ensure_session(actor, session_id, text)
        session_id = session["id"]
        self._message(session_id, "user", text)
        lower = text.lower()
        events: list[tuple[str, dict]] = [("session", {"id": session_id}), ("status", {"step": "understanding"})]
        answer: str
        artifact: dict | None = None

        record_id = r"([0-9a-f-]{8,})"
        create = re.search(r"(?:create|start|set up)\s+(?:a\s+)?dps(?:\s+for|\s+called|:)?\s+(.+)", text, re.I)
        publish = re.search(r"publish\s+dps\s+([0-9a-f-]{8,})", text, re.I)
        competition = re.search(r"create\s+competition\s+([0-9a-f-]{8,})\s*\|\s*(.+)", text, re.I)
        category = re.search(rf"add\s+category\s+{record_id}\s*\|\s*([^|]+)\s*\|\s*(.+)", text, re.I)
        qualification = re.search(rf"add\s+qualification\s+criterion\s+{record_id}\s*\|\s*([^|]+)(?:\s*\|\s*(.+))?", text, re.I)
        application_action = re.search(
            rf"(review|admit|reject|suspend|request\s+clarification(?:\s+for)?)\s+application\s+{record_id}(?:\s*\|\s*(.*))?",
            text, re.I,
        )
        evaluation_criterion = re.search(
            rf"add\s+evaluation\s+criterion\s+{record_id}\s*\|\s*([^|]+)\s*\|\s*([0-9]+(?:\.[0-9]+)?)(?:\s*\|\s*([0-9]+(?:\.[0-9]+)?))?",
            text, re.I,
        )
        competition_action = re.search(
            rf"(publish|close|cancel|start\s+evaluation\s+for)\s+competition\s+{record_id}", text, re.I
        )
        conflict = re.search(rf"declare\s+(no\s+)?conflict(?:\s+for)?\s+competition\s+{record_id}(?:\s*\|\s*(.*))?", text, re.I)
        score = re.search(
            rf"score\s+submission\s+{record_id}\s*\|\s*{record_id}\s*\|\s*([0-9]+(?:\.[0-9]+)?)(?:\s*\|\s*(.*))?",
            text, re.I,
        )
        award_create = re.search(
            rf"create\s+award\s+{record_id}\s*\|\s*{record_id}(?:\s*\|\s*(.*))?", text, re.I
        )
        award_action = re.search(rf"(approve|publish|withdraw)\s+award\s+{record_id}", text, re.I)
        contract = re.search(rf"create\s+contract\s+{record_id}\s*\|\s*(.+)", text, re.I)
        if create:
            title = create.group(1).strip().rstrip(".")
            answer, artifact = self._pending(actor, session_id, "dps.create", {"title": title}, "dps.create", f"Create a draft DPS named “{title}”.")
        elif publish:
            dps = self.procurement.get_dps(actor, publish.group(1))
            answer, artifact = self._pending(actor, session_id, "dps.publish", {"dps_id": dps["id"]}, "dps.publish", f"Publish {dps['reference']} — {dps['title']}.")
        elif competition:
            dps = self.procurement.get_dps(actor, competition.group(1))
            title = competition.group(2).strip()
            answer, artifact = self._pending(actor, session_id, "competition.create", {"dps_id": dps["id"], "title": title}, "competitions.manage", f"Create “{title}” under {dps['reference']}.")
        elif category:
            dps = self.procurement.get_dps(actor, category.group(1))
            payload = {"dps_id": dps["id"], "code": category.group(2).strip(), "name": category.group(3).strip()}
            answer, artifact = self._pending(actor, session_id, "dps.category.add", payload, "dps.edit", f"Add category {payload['code']} — {payload['name']} to {dps['reference']}.")
        elif qualification:
            dps = self.procurement.get_dps(actor, qualification.group(1))
            payload = {"dps_id": dps["id"], "name": qualification.group(2).strip(), "description": (qualification.group(3) or "").strip()}
            answer, artifact = self._pending(actor, session_id, "dps.criterion.add", payload, "dps.edit", f"Add qualification criterion “{payload['name']}” to {dps['reference']}.")
        elif application_action:
            verb = re.sub(r"\s+", " ", application_action.group(1).lower())
            targets = {"review": "under_review", "admit": "admitted", "reject": "rejected", "suspend": "suspended",
                       "request clarification": "needs_clarification", "request clarification for": "needs_clarification"}
            target = targets[verb]
            application = next((item for item in self.procurement.list_applications(actor) if item["id"] == application_action.group(2)), None)
            if not application:
                raise LookupError("Application not found")
            permission = "suppliers.admit" if target in {"admitted", "rejected", "suspended"} else "suppliers.review"
            payload = {"application_id": application["id"], "target": target, "reason": (application_action.group(3) or "").strip()}
            answer, artifact = self._pending(actor, session_id, "application.transition", payload, permission, f"Move {application['supplier_name']}’s application to {target.replace('_', ' ')}.")
        elif evaluation_criterion:
            competition_record = self.procurement.get_competition(actor, evaluation_criterion.group(1))
            payload = {"competition_id": competition_record["id"], "name": evaluation_criterion.group(2).strip(),
                       "weight": evaluation_criterion.group(3), "max_score": evaluation_criterion.group(4) or "10"}
            answer, artifact = self._pending(actor, session_id, "competition.criterion.add", payload, "competitions.manage", f"Add “{payload['name']}” at {payload['weight']}% to {competition_record['reference']}.")
        elif competition_action:
            targets = {"publish": "published", "close": "closed", "cancel": "cancelled", "start evaluation for": "evaluation"}
            verb = re.sub(r"\s+", " ", competition_action.group(1).lower())
            competition_record = self.procurement.get_competition(actor, competition_action.group(2))
            target = targets[verb]
            answer, artifact = self._pending(actor, session_id, "competition.transition", {"competition_id": competition_record["id"], "target": target}, "competitions.manage", f"Move {competition_record['reference']} to {target}.")
        elif conflict:
            competition_record = self.procurement.get_competition(actor, conflict.group(2))
            has_conflict = conflict.group(1) is None
            payload = {"competition_id": competition_record["id"], "has_conflict": has_conflict,
                       "declaration": (conflict.group(3) or ("Conflict declared" if has_conflict else "No conflict")).strip()}
            answer, artifact = self._pending(actor, session_id, "evaluation.conflict.declare", payload, "submissions.evaluate", f"Record your conflict declaration for {competition_record['reference']}.")
        elif score:
            payload = {"submission_id": score.group(1), "criterion_id": score.group(2), "score": score.group(3),
                       "comment": (score.group(4) or "").strip()}
            answer, artifact = self._pending(actor, session_id, "evaluation.score", payload, "submissions.evaluate", f"Record score {payload['score']} for the selected submission and criterion.")
        elif award_create:
            payload = {"competition_id": award_create.group(1), "submission_id": award_create.group(2),
                       "rationale": (award_create.group(3) or "").strip()}
            answer, artifact = self._pending(actor, session_id, "award.create", payload, "awards.approve", "Create a draft award for the selected submission.")
        elif award_action:
            targets = {"approve": "approved", "publish": "published", "withdraw": "withdrawn"}
            target = targets[award_action.group(1).lower()]
            answer, artifact = self._pending(actor, session_id, "award.transition", {"award_id": award_action.group(2), "target": target}, "awards.approve", f"Move the award to {target}.")
        elif contract:
            payload = {"award_id": contract.group(1), "reference": contract.group(2).strip()}
            answer, artifact = self._pending(actor, session_id, "contract.create", payload, "awards.approve", f"Create contract {payload['reference']} from the published award.")
        elif "list dps" in lower or "show dps" in lower or "my dps" in lower:
            records = self.procurement.list_dps(actor)
            answer = f"I found {len(records)} dynamic purchasing system{'s' if len(records) != 1 else ''} in this workspace."
            artifact = {"kind": "dps_list", "title": "Dynamic purchasing systems", "items": records}
        elif "supplier application" in lower:
            records = self.procurement.list_applications(actor)
            answer = f"There are {len(records)} supplier applications."
            artifact = {"kind": "application_list", "title": "Supplier applications", "items": records}
        elif "list competition" in lower or "show competition" in lower:
            records = self.procurement.list_competitions(actor)
            answer = f"I found {len(records)} competition{'s' if len(records) != 1 else ''}."
            artifact = {"kind": "competition_list", "title": "Call-off competitions", "items": records}
        elif lower.startswith("search notices") or lower in {"list notices", "show notices"}:
            query = re.sub(r"^search\s+notices\s*", "", text, flags=re.I).strip()
            records = self.ocds.notices(actor, query)
            answer = f"I found {len(records)} imported notice{'s' if len(records) != 1 else ''}{f' matching “{query}”' if query else ''}."
            artifact = {"kind": "notice_list", "title": "Imported notices", "items": records}
        elif "audit" in lower:
            actor.require("audit.view")
            records = self.db.rows(
                "SELECT action,entity_type,entity_id,created_at FROM audit_events WHERE organisation_id=? ORDER BY created_at DESC LIMIT 25",
                (actor.organisation_id,),
            )
            answer = f"Here are the latest {len(records)} governed actions."
            artifact = {"kind": "audit_list", "title": "Recent audit activity", "items": records}
        elif lower in {"help", "/help"} or "what can you do" in lower:
            answer = HELP
        else:
            answer = self._llm_answer(actor, text) or HELP

        events.append(("status", {"step": "preparing_result"}))
        if artifact:
            events.append(("artifact", artifact))
        events.append(("message", {"text": answer}))
        events.append(("done", {"session_id": session_id}))
        self._message(session_id, "assistant", answer, artifact or {})
        return session_id, events

    def _llm_answer(self, actor: Actor, message: str) -> str | None:
        if not settings.llm_api_key or not settings.llm_model:
            return None
        prompt = (
            "You are the FastDPS procurement assistant. Explain and draft, but never claim to execute, approve, publish, "
            "admit, reject, award, or change permissions. Tell the user to use an explicit FastDPS action for changes. "
            f"Workspace: {actor.organisation_name}. User message: {message}"
        )
        try:
            response = httpx.post(
                f"{settings.llm_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={"model": settings.llm_model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception:
            return None

    def confirm(self, actor: Actor, action_id: str) -> dict:
        action = self.db.one(
            "SELECT * FROM chat_pending_actions WHERE id=? AND organisation_id=? AND requested_by=?",
            (action_id, actor.organisation_id, actor.user_id),
        )
        if not action:
            raise LookupError("Action not found")
        if action["status"] != "pending":
            raise ValueError("Action is no longer pending")
        if action["expires_at"] < now():
            with self.db.transaction() as tx:
                tx.execute("UPDATE chat_pending_actions SET status='expired' WHERE id=?", (action_id,))
            raise ValueError("Action has expired")
        actor.require(action["required_permission"])
        payload = json_load(action["payload_json"], {})
        with self.db.transaction() as tx:
            claimed = tx.execute("UPDATE chat_pending_actions SET status='executing' WHERE id=? AND status='pending'", (action_id,))
            if claimed.rowcount != 1:
                raise ValueError("Action is already being processed")
        try:
            if action["action_key"] == "dps.create":
                result = self.procurement.create_dps(actor, **payload)
            elif action["action_key"] == "dps.publish":
                result = self.procurement.transition_dps(actor, payload["dps_id"], "published")
            elif action["action_key"] == "competition.create":
                result = self.procurement.create_competition(actor, **payload)
            elif action["action_key"] == "dps.category.add":
                result = self.procurement.add_category(actor, **payload)
            elif action["action_key"] == "dps.criterion.add":
                result = self.procurement.add_criterion(actor, **payload)
            elif action["action_key"] == "application.transition":
                result = self.procurement.decide_application(actor, **payload)
            elif action["action_key"] == "competition.criterion.add":
                result = self.procurement.add_evaluation_criterion(actor, **payload)
            elif action["action_key"] == "competition.transition":
                result = self.procurement.transition_competition(actor, **payload)
            elif action["action_key"] == "evaluation.conflict.declare":
                self.procurement.declare_conflict(actor, **payload)
                result = {"ok": True}
            elif action["action_key"] == "evaluation.score":
                result = self.procurement.evaluate(actor, **payload)
            elif action["action_key"] == "award.create":
                result = self.procurement.create_award(actor, **payload)
            elif action["action_key"] == "award.transition":
                result = self.procurement.transition_award(actor, **payload)
            elif action["action_key"] == "contract.create":
                result = self.procurement.create_contract(actor, **payload)
            else:
                raise ValueError("Unsupported action")
        except Exception:
            with self.db.transaction() as tx:
                tx.execute("UPDATE chat_pending_actions SET status='pending' WHERE id=? AND status='executing'", (action_id,))
            raise
        with self.db.transaction() as tx:
            tx.execute("UPDATE chat_pending_actions SET status='executed',executed_at=? WHERE id=? AND status='executing'", (now(), action_id))
            audit(tx, actor.organisation_id, actor.user_id, "chat.action_executed", "chat_action", action_id, {"action": action["action_key"]})
        return {"action": action["action_key"], "result": result}
