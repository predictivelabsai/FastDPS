"""Transaction-safe DPS, supplier, competition, evaluation, and award services."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastdps.database import Database, get_database
from fastdps.domain import (
    APPLICATION_TRANSITIONS,
    AWARD_TRANSITIONS,
    COMPETITION_TRANSITIONS,
    DPS_TRANSITIONS,
    require_transition,
)
from fastdps.security import Actor
from fastdps.services.common import audit, json_dump, json_load, now, uid


def _money(value: str | int | float | Decimal | None) -> str | None:
    if value in (None, ""):
        return None
    try:
        return str(Decimal(str(value)).quantize(Decimal("0.01")))
    except InvalidOperation as exc:
        raise ValueError("Invalid monetary amount") from exc


class ProcurementService:
    def __init__(self, db: Database | None = None):
        self.db = db or get_database()

    def seed_workflows(self, organisation_id: str) -> None:
        definitions = {
            "DPS governance": ("dps", [
                ("draft", "Draft", "dps.edit"), ("published", "Published", "dps.publish"),
                ("closed", "Closed", "dps.publish"), ("archived", "Archived", "dps.publish"),
            ]),
            "Supplier admission": ("application", [
                ("submitted", "Submitted", "suppliers.view"), ("under_review", "Under review", "suppliers.review"),
                ("decision", "Admission decision", "suppliers.admit"),
            ]),
            "Call-off competition": ("competition", [
                ("draft", "Draft", "competitions.manage"), ("published", "Published", "competitions.manage"),
                ("evaluation", "Evaluation", "submissions.evaluate"), ("award", "Award", "awards.approve"),
            ]),
        }
        with self.db.transaction() as tx:
            for name, (entity_type, steps) in definitions.items():
                if tx.one("SELECT id FROM workflow_definitions WHERE organisation_id=? AND name=?", (organisation_id, name)):
                    continue
                workflow_id = uid()
                tx.execute(
                    "INSERT INTO workflow_definitions(id,organisation_id,name,entity_type,is_default,created_at) VALUES (?,?,?,?,1,?)",
                    (workflow_id, organisation_id, name, entity_type, now()),
                )
                for order, (key, label, permission) in enumerate(steps):
                    tx.execute(
                        "INSERT INTO workflow_steps(id,workflow_id,step_key,name,required_permission,sort_order) VALUES (?,?,?,?,?,?)",
                        (uid(), workflow_id, key, label, permission, order),
                    )
                for (from_key, _, _), (to_key, to_label, permission) in zip(steps, steps[1:]):
                    tx.execute(
                        "INSERT INTO workflow_transitions(id,workflow_id,from_step,to_step,action_name,required_permission) VALUES (?,?,?,?,?,?)",
                        (uid(), workflow_id, from_key, to_key, f"Move to {to_label}", permission),
                    )

    def create_dps(self, actor: Actor, title: str, description: str = "", reference: str = "",
                   currency: str = "EUR", estimated_value=None, opens_at: str | None = None,
                   closes_at: str | None = None) -> dict:
        actor.require("dps.create")
        title = title.strip()
        if not title:
            raise ValueError("Title is required")
        dps_id = uid()
        reference = reference.strip() or f"DPS-{now()[:4]}-{dps_id[:8].upper()}"
        timestamp = now()
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO dynamic_purchasing_systems(id,organisation_id,reference,title,description,status,"
                "jurisdiction_profile,currency,estimated_value,opens_at,closes_at,created_by,created_at,updated_at) "
                "VALUES (?,?,?,?,?,'draft','neutral',?,?,?,?,?,?,?)",
                (dps_id, actor.organisation_id, reference, title, description.strip(), currency.upper(),
                 _money(estimated_value), opens_at or None, closes_at or None, actor.user_id, timestamp, timestamp),
            )
            audit(tx, actor.organisation_id, actor.user_id, "dps.created", "dps", dps_id, {"reference": reference, "title": title})
        return self.get_dps(actor, dps_id)

    def list_dps(self, actor: Actor, published_only: bool = False) -> list[dict]:
        actor.require("dps.view")
        query = "SELECT * FROM dynamic_purchasing_systems WHERE organisation_id=?"
        params: list = [actor.organisation_id]
        if published_only:
            query += " AND status='published'"
        query += " ORDER BY updated_at DESC"
        return self.db.rows(query, params)

    def public_dps(self) -> list[dict]:
        return self.db.rows(
            "SELECT d.*,o.name buyer_name FROM dynamic_purchasing_systems d JOIN organisations o ON o.id=d.organisation_id "
            "WHERE d.status='published' ORDER BY d.updated_at DESC"
        )

    def get_dps(self, actor: Actor, dps_id: str) -> dict:
        actor.require("dps.view")
        item = self.db.one("SELECT * FROM dynamic_purchasing_systems WHERE id=? AND organisation_id=?", (dps_id, actor.organisation_id))
        if not item:
            raise LookupError("DPS not found")
        item["categories"] = self.db.rows("SELECT * FROM dps_categories WHERE dps_id=? ORDER BY code,name", (dps_id,))
        item["criteria"] = self.db.rows("SELECT * FROM qualification_criteria WHERE dps_id=? ORDER BY sort_order,name", (dps_id,))
        return item

    def update_dps(self, actor: Actor, dps_id: str, **fields) -> dict:
        actor.require("dps.edit")
        current = self.get_dps(actor, dps_id)
        allowed = ("title", "description", "currency", "estimated_value", "opens_at", "closes_at")
        values = {key: fields[key] for key in allowed if key in fields}
        if "estimated_value" in values:
            values["estimated_value"] = _money(values["estimated_value"])
        if not values:
            return current
        assignments = ",".join(f"{key}=?" for key in values)
        with self.db.transaction() as tx:
            tx.execute(
                f"UPDATE dynamic_purchasing_systems SET {assignments},updated_at=? WHERE id=? AND organisation_id=?",
                (*values.values(), now(), dps_id, actor.organisation_id),
            )
            audit(tx, actor.organisation_id, actor.user_id, "dps.updated", "dps", dps_id, {"fields": sorted(values)})
        return self.get_dps(actor, dps_id)

    def transition_dps(self, actor: Actor, dps_id: str, target: str) -> dict:
        actor.require("dps.publish")
        current = self.get_dps(actor, dps_id)
        require_transition(DPS_TRANSITIONS, current["status"], target)
        if target == "published" and not current["categories"]:
            raise ValueError("Add at least one category before publishing")
        with self.db.transaction() as tx:
            tx.execute("UPDATE dynamic_purchasing_systems SET status=?,updated_at=? WHERE id=? AND organisation_id=?",
                       (target, now(), dps_id, actor.organisation_id))
            audit(tx, actor.organisation_id, actor.user_id, f"dps.{target}", "dps", dps_id,
                  {"from": current["status"], "to": target})
        return self.get_dps(actor, dps_id)

    def add_category(self, actor: Actor, dps_id: str, code: str, name: str, description: str = "") -> dict:
        actor.require("dps.edit")
        self.get_dps(actor, dps_id)
        category_id = uid()
        with self.db.transaction() as tx:
            tx.execute("INSERT INTO dps_categories(id,dps_id,code,name,description) VALUES (?,?,?,?,?)",
                       (category_id, dps_id, code.strip() or category_id[:8], name.strip(), description.strip()))
            audit(tx, actor.organisation_id, actor.user_id, "dps.category_added", "dps", dps_id, {"category_id": category_id})
        return self.db.one("SELECT * FROM dps_categories WHERE id=?", (category_id,))

    def add_criterion(self, actor: Actor, dps_id: str, name: str, description: str = "",
                      category_id: str | None = None, required: bool = True) -> dict:
        actor.require("dps.edit")
        self.get_dps(actor, dps_id)
        criterion_id = uid()
        order = int(self.db.scalar("SELECT COUNT(*) FROM qualification_criteria WHERE dps_id=?", (dps_id,)) or 0)
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO qualification_criteria(id,dps_id,category_id,name,description,required,sort_order) VALUES (?,?,?,?,?,?,?)",
                (criterion_id, dps_id, category_id or None, name.strip(), description.strip(), int(required), order),
            )
            audit(tx, actor.organisation_id, actor.user_id, "dps.criterion_added", "dps", dps_id, {"criterion_id": criterion_id})
        return self.db.one("SELECT * FROM qualification_criteria WHERE id=?", (criterion_id,))

    def ensure_supplier(self, user_id: str, name: str, registration_number: str = "", website: str = "") -> dict:
        existing = self.db.one("SELECT * FROM supplier_organisations WHERE owner_user_id=?", (user_id,))
        timestamp = now()
        if existing:
            with self.db.transaction() as tx:
                tx.execute("UPDATE supplier_organisations SET name=?,registration_number=?,website=?,updated_at=? WHERE id=?",
                           (name.strip(), registration_number.strip(), website.strip(), timestamp, existing["id"]))
            return self.db.one("SELECT * FROM supplier_organisations WHERE id=?", (existing["id"],))
        supplier_id = uid()
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO supplier_organisations(id,owner_user_id,name,registration_number,website,status,created_at,updated_at) "
                "VALUES (?,?,?,?,?,'active',?,?)",
                (supplier_id, user_id, name.strip(), registration_number.strip(), website.strip(), timestamp, timestamp),
            )
        return self.db.one("SELECT * FROM supplier_organisations WHERE id=?", (supplier_id,))

    def apply(self, user_id: str, dps_id: str, supplier_id: str, answers: dict | None = None) -> dict:
        dps = self.db.one("SELECT id,organisation_id,status FROM dynamic_purchasing_systems WHERE id=?", (dps_id,))
        supplier = self.db.one("SELECT * FROM supplier_organisations WHERE id=? AND owner_user_id=?", (supplier_id, user_id))
        if not dps or dps["status"] != "published":
            raise ValueError("This DPS is not open for applications")
        if not supplier:
            raise PermissionError("Supplier profile not found")
        existing = self.db.one("SELECT * FROM admission_applications WHERE dps_id=? AND supplier_id=?", (dps_id, supplier_id))
        if existing:
            return existing
        application_id, timestamp = uid(), now()
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO admission_applications(id,dps_id,supplier_id,status,answers_json,created_at,updated_at) "
                "VALUES (?,?,?,'draft',?,?,?)",
                (application_id, dps_id, supplier_id, json_dump(answers or {}), timestamp, timestamp),
            )
            audit(tx, dps["organisation_id"], user_id, "application.created", "application", application_id, {"supplier_id": supplier_id})
        return self.db.one("SELECT * FROM admission_applications WHERE id=?", (application_id,))

    def submit_application(self, user_id: str, application_id: str, answers: dict) -> dict:
        application = self.db.one(
            "SELECT a.*,s.owner_user_id,d.organisation_id FROM admission_applications a "
            "JOIN supplier_organisations s ON s.id=a.supplier_id JOIN dynamic_purchasing_systems d ON d.id=a.dps_id "
            "WHERE a.id=?", (application_id,)
        )
        if not application or application["owner_user_id"] != user_id:
            raise LookupError("Application not found")
        require_transition(APPLICATION_TRANSITIONS, application["status"], "submitted")
        timestamp = now()
        with self.db.transaction() as tx:
            tx.execute("UPDATE admission_applications SET status='submitted',answers_json=?,submitted_at=?,updated_at=? WHERE id=?",
                       (json_dump(answers), timestamp, timestamp, application_id))
            audit(tx, application["organisation_id"], user_id, "application.submitted", "application", application_id)
        return self.db.one("SELECT * FROM admission_applications WHERE id=?", (application_id,))

    def list_applications(self, actor: Actor, status: str | None = None) -> list[dict]:
        actor.require("suppliers.view")
        query = (
            "SELECT a.*,d.title dps_title,d.reference dps_reference,s.name supplier_name,s.registration_number "
            "FROM admission_applications a JOIN dynamic_purchasing_systems d ON d.id=a.dps_id "
            "JOIN supplier_organisations s ON s.id=a.supplier_id WHERE d.organisation_id=?"
        )
        params: list = [actor.organisation_id]
        if status:
            query += " AND a.status=?"
            params.append(status)
        query += " ORDER BY a.updated_at DESC"
        results = self.db.rows(query, params)
        for item in results:
            item["answers"] = json_load(item.pop("answers_json"), {})
        return results

    def decide_application(self, actor: Actor, application_id: str, target: str, reason: str = "") -> dict:
        permission = "suppliers.admit" if target in {"admitted", "rejected", "suspended"} else "suppliers.review"
        actor.require(permission)
        application = self.db.one(
            "SELECT a.* FROM admission_applications a JOIN dynamic_purchasing_systems d ON d.id=a.dps_id "
            "WHERE a.id=? AND d.organisation_id=?", (application_id, actor.organisation_id),
        )
        if not application:
            raise LookupError("Application not found")
        require_transition(APPLICATION_TRANSITIONS, application["status"], target)
        timestamp = now()
        with self.db.transaction() as tx:
            tx.execute(
                "UPDATE admission_applications SET status=?,reviewed_by=?,reviewed_at=?,decision_reason=?,updated_at=? WHERE id=?",
                (target, actor.user_id, timestamp, reason.strip(), timestamp, application_id),
            )
            audit(tx, actor.organisation_id, actor.user_id, f"application.{target}", "application", application_id,
                  {"from": application["status"], "reason": reason.strip()})
        return self.db.one("SELECT * FROM admission_applications WHERE id=?", (application_id,))

    def create_competition(self, actor: Actor, dps_id: str, title: str, description: str = "", deadline: str | None = None) -> dict:
        actor.require("competitions.manage")
        dps = self.get_dps(actor, dps_id)
        if dps["status"] != "published":
            raise ValueError("Competitions can only be created under a published DPS")
        competition_id, timestamp = uid(), now()
        reference = f"CO-{timestamp[:4]}-{competition_id[:8].upper()}"
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO competitions(id,dps_id,organisation_id,reference,title,description,status,deadline,created_by,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,'draft',?,?,?,?)",
                (competition_id, dps_id, actor.organisation_id, reference, title.strip(), description.strip(), deadline or None,
                 actor.user_id, timestamp, timestamp),
            )
            audit(tx, actor.organisation_id, actor.user_id, "competition.created", "competition", competition_id, {"dps_id": dps_id})
        return self.get_competition(actor, competition_id)

    def list_competitions(self, actor: Actor) -> list[dict]:
        actor.require("competitions.view")
        return self.db.rows(
            "SELECT c.*,d.title dps_title FROM competitions c JOIN dynamic_purchasing_systems d ON d.id=c.dps_id "
            "WHERE c.organisation_id=? ORDER BY c.updated_at DESC", (actor.organisation_id,)
        )

    def get_competition(self, actor: Actor, competition_id: str) -> dict:
        actor.require("competitions.view")
        item = self.db.one("SELECT * FROM competitions WHERE id=? AND organisation_id=?", (competition_id, actor.organisation_id))
        if not item:
            raise LookupError("Competition not found")
        item["criteria"] = self.db.rows("SELECT * FROM evaluation_criteria WHERE competition_id=? ORDER BY sort_order", (competition_id,))
        item["submissions"] = self.db.rows(
            "SELECT s.*,so.name supplier_name FROM submissions s JOIN supplier_organisations so ON so.id=s.supplier_id "
            "WHERE s.competition_id=? ORDER BY s.updated_at DESC", (competition_id,)
        )
        item["invitations"] = self.db.rows(
            "SELECT i.*,so.name supplier_name FROM competition_invitations i JOIN supplier_organisations so ON so.id=i.supplier_id "
            "WHERE i.competition_id=? ORDER BY so.name", (competition_id,)
        )
        item["evaluations"] = self.db.rows(
            "SELECT e.*,u.name evaluator_name FROM evaluations e JOIN users u ON u.id=e.evaluator_user_id "
            "JOIN submissions s ON s.id=e.submission_id WHERE s.competition_id=? ORDER BY e.created_at", (competition_id,)
        )
        item["award"] = self.db.one("SELECT * FROM awards WHERE competition_id=?", (competition_id,))
        return item

    def transition_competition(self, actor: Actor, competition_id: str, target: str) -> dict:
        actor.require("competitions.manage" if target != "awarded" else "awards.approve")
        current = self.get_competition(actor, competition_id)
        require_transition(COMPETITION_TRANSITIONS, current["status"], target)
        if target == "published":
            if not current["criteria"]:
                raise ValueError("Add evaluation criteria before publishing")
            weight = sum(Decimal(str(item["weight"])) for item in current["criteria"])
            if weight != Decimal("100"):
                raise ValueError("Evaluation criterion weights must total 100")
        with self.db.transaction() as tx:
            tx.execute("UPDATE competitions SET status=?,updated_at=? WHERE id=? AND organisation_id=?",
                       (target, now(), competition_id, actor.organisation_id))
            if target == "published":
                admitted = tx.rows("SELECT supplier_id FROM admission_applications WHERE dps_id=? AND status='admitted'", (current["dps_id"],))
                for row in admitted:
                    tx.execute(
                        "INSERT INTO competition_invitations(competition_id,supplier_id,status,invited_at) VALUES (?,?,'invited',?) ON CONFLICT DO NOTHING",
                        (competition_id, row["supplier_id"], now()),
                    )
            audit(tx, actor.organisation_id, actor.user_id, f"competition.{target}", "competition", competition_id,
                  {"from": current["status"]})
        return self.get_competition(actor, competition_id)

    def add_evaluation_criterion(self, actor: Actor, competition_id: str, name: str, weight, max_score=10) -> dict:
        actor.require("competitions.manage")
        self.get_competition(actor, competition_id)
        criterion_id = uid()
        order = int(self.db.scalar("SELECT COUNT(*) FROM evaluation_criteria WHERE competition_id=?", (competition_id,)) or 0)
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO evaluation_criteria(id,competition_id,name,description,weight,max_score,sort_order) VALUES (?,?,?,'',?,?,?)",
                (criterion_id, competition_id, name.strip(), str(Decimal(str(weight))), str(Decimal(str(max_score))), order),
            )
            audit(tx, actor.organisation_id, actor.user_id, "competition.criterion_added", "competition",
                  competition_id, {"criterion_id": criterion_id})
        return self.db.one("SELECT * FROM evaluation_criteria WHERE id=?", (criterion_id,))

    def submit_bid(self, user_id: str, competition_id: str, supplier_id: str, value_amount, response: dict) -> dict:
        invitation = self.db.one(
            "SELECT i.*,c.status competition_status,c.organisation_id FROM competition_invitations i JOIN competitions c ON c.id=i.competition_id "
            "JOIN supplier_organisations so ON so.id=i.supplier_id WHERE i.competition_id=? AND i.supplier_id=? AND so.owner_user_id=?",
            (competition_id, supplier_id, user_id),
        )
        if not invitation or invitation["competition_status"] != "published":
            raise PermissionError("No open invitation found")
        submission_id, timestamp = uid(), now()
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO submissions(id,competition_id,supplier_id,status,value_amount,currency,response_json,submitted_at,created_at,updated_at) "
                "VALUES (?,?,?,'submitted',?,'EUR',?,?,?,?)",
                (submission_id, competition_id, supplier_id, _money(value_amount), json_dump(response), timestamp, timestamp, timestamp),
            )
            audit(tx, invitation["organisation_id"], user_id, "submission.submitted", "submission", submission_id)
        return self.db.one("SELECT * FROM submissions WHERE id=?", (submission_id,))

    def declare_conflict(self, actor: Actor, competition_id: str, has_conflict: bool, declaration: str) -> None:
        actor.require("submissions.evaluate")
        self.get_competition(actor, competition_id)
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO conflicts(id,competition_id,user_id,declaration,has_conflict,created_at) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(competition_id,user_id) DO UPDATE SET declaration=excluded.declaration,has_conflict=excluded.has_conflict,created_at=excluded.created_at",
                (uid(), competition_id, actor.user_id, declaration.strip(), int(has_conflict), now()),
            )
            audit(tx, actor.organisation_id, actor.user_id, "evaluation.conflict_declared", "competition",
                  competition_id, {"has_conflict": bool(has_conflict)})

    def evaluate(self, actor: Actor, submission_id: str, criterion_id: str, score, comment: str = "") -> dict:
        actor.require("submissions.evaluate")
        row = self.db.one(
            "SELECT s.id,c.id competition_id,c.organisation_id,ec.max_score FROM submissions s "
            "JOIN competitions c ON c.id=s.competition_id JOIN evaluation_criteria ec ON ec.competition_id=c.id "
            "WHERE s.id=? AND ec.id=? AND c.organisation_id=?",
            (submission_id, criterion_id, actor.organisation_id),
        )
        if not row:
            raise LookupError("Submission or criterion not found")
        conflict = self.db.one("SELECT has_conflict FROM conflicts WHERE competition_id=? AND user_id=?", (row["competition_id"], actor.user_id))
        if not conflict:
            raise ValueError("Declare conflicts before evaluating")
        if bool(conflict["has_conflict"]):
            raise PermissionError("An evaluator with a declared conflict cannot score this competition")
        numeric_score = Decimal(str(score))
        if numeric_score < 0 or numeric_score > Decimal(str(row["max_score"])):
            raise ValueError("Score is outside the criterion range")
        evaluation_id, timestamp = uid(), now()
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO evaluations(id,submission_id,criterion_id,evaluator_user_id,score,comment,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(submission_id,criterion_id,evaluator_user_id) "
                "DO UPDATE SET score=excluded.score,comment=excluded.comment,updated_at=excluded.updated_at",
                (evaluation_id, submission_id, criterion_id, actor.user_id, str(numeric_score), comment.strip(), timestamp, timestamp),
            )
            audit(tx, actor.organisation_id, actor.user_id, "submission.scored", "submission", submission_id, {"criterion_id": criterion_id})
        return self.db.one(
            "SELECT * FROM evaluations WHERE submission_id=? AND criterion_id=? AND evaluator_user_id=?",
            (submission_id, criterion_id, actor.user_id),
        )

    def create_award(self, actor: Actor, competition_id: str, submission_id: str, rationale: str = "") -> dict:
        actor.require("awards.approve")
        competition = self.get_competition(actor, competition_id)
        if competition["status"] != "evaluation":
            raise ValueError("Competition must be in evaluation before creating an award")
        if not any(item["id"] == submission_id for item in competition["submissions"]):
            raise LookupError("Submission not found in this competition")
        award_id, timestamp = uid(), now()
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO awards(id,competition_id,submission_id,status,rationale,created_at,updated_at) VALUES (?,?,?,'draft',?,?,?)",
                (award_id, competition_id, submission_id, rationale.strip(), timestamp, timestamp),
            )
            audit(tx, actor.organisation_id, actor.user_id, "award.created", "award", award_id, {"competition_id": competition_id})
        return self.db.one("SELECT * FROM awards WHERE id=?", (award_id,))

    def transition_award(self, actor: Actor, award_id: str, target: str) -> dict:
        actor.require("awards.approve")
        award = self.db.one(
            "SELECT a.* FROM awards a JOIN competitions c ON c.id=a.competition_id WHERE a.id=? AND c.organisation_id=?",
            (award_id, actor.organisation_id),
        )
        if not award:
            raise LookupError("Award not found")
        require_transition(AWARD_TRANSITIONS, award["status"], target)
        timestamp = now()
        with self.db.transaction() as tx:
            tx.execute("UPDATE awards SET status=?,approved_by=?,approved_at=?,updated_at=? WHERE id=?",
                       (target, actor.user_id if target == "approved" else award.get("approved_by"),
                        timestamp if target == "approved" else award.get("approved_at"), timestamp, award_id))
            if target == "published":
                tx.execute("UPDATE competitions SET status='awarded',updated_at=? WHERE id=?", (timestamp, award["competition_id"]))
            audit(tx, actor.organisation_id, actor.user_id, f"award.{target}", "award", award_id)
        return self.db.one("SELECT * FROM awards WHERE id=?", (award_id,))

    def create_contract(self, actor: Actor, award_id: str, reference: str, starts_at: str | None = None,
                        ends_at: str | None = None) -> dict:
        actor.require("awards.approve")
        award = self.db.one(
            "SELECT a.*,s.value_amount,s.currency FROM awards a JOIN competitions c ON c.id=a.competition_id "
            "JOIN submissions s ON s.id=a.submission_id WHERE a.id=? AND c.organisation_id=?",
            (award_id, actor.organisation_id),
        )
        if not award or award["status"] != "published":
            raise ValueError("A contract requires a published award")
        existing = self.db.one("SELECT * FROM contracts WHERE award_id=?", (award_id,))
        if existing:
            return existing
        contract_id = uid()
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO contracts(id,award_id,reference,status,value_amount,currency,starts_at,ends_at,created_at) "
                "VALUES (?,?,?,'draft',?,?,?,?,?)",
                (contract_id, award_id, reference.strip(), award["value_amount"], award["currency"], starts_at, ends_at, now()),
            )
            audit(tx, actor.organisation_id, actor.user_id, "contract.created", "contract", contract_id, {"award_id": award_id})
        return self.db.one("SELECT * FROM contracts WHERE id=?", (contract_id,))

    def dashboard(self, actor: Actor) -> dict:
        actor.require("dps.view")
        oid = actor.organisation_id
        return {
            "dps": int(self.db.scalar("SELECT COUNT(*) FROM dynamic_purchasing_systems WHERE organisation_id=?", (oid,)) or 0),
            "open_dps": int(self.db.scalar("SELECT COUNT(*) FROM dynamic_purchasing_systems WHERE organisation_id=? AND status='published'", (oid,)) or 0),
            "applications": int(self.db.scalar(
                "SELECT COUNT(*) FROM admission_applications a JOIN dynamic_purchasing_systems d ON d.id=a.dps_id WHERE d.organisation_id=?", (oid,)
            ) or 0),
            "pending_applications": int(self.db.scalar(
                "SELECT COUNT(*) FROM admission_applications a JOIN dynamic_purchasing_systems d ON d.id=a.dps_id "
                "WHERE d.organisation_id=? AND a.status IN ('submitted','under_review','needs_clarification')", (oid,)
            ) or 0),
            "competitions": int(self.db.scalar("SELECT COUNT(*) FROM competitions WHERE organisation_id=?", (oid,)) or 0),
            "pending_actions": int(self.db.scalar(
                "SELECT COUNT(*) FROM chat_pending_actions WHERE organisation_id=? AND status='pending'", (oid,)
            ) or 0),
        }
