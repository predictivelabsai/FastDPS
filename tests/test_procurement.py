from __future__ import annotations

import pytest

from fastdps.services.procurement import ProcurementService
from fastdps.services.workflows import WorkflowService


def open_dps(service, owner, title="Professional services"):
    item = service.create_dps(owner, title, estimated_value="125000.50")
    service.add_category(owner, item["id"], "79000000", "Business services")
    service.add_criterion(owner, item["id"], "Relevant experience", "One comparable engagement")
    return service.transition_dps(owner, item["id"], "published")


def test_dps_requires_category_before_publication(db, owner):
    service = ProcurementService(db)
    item = service.create_dps(owner, "Empty system")
    with pytest.raises(ValueError, match="category"):
        service.transition_dps(owner, item["id"], "published")


def test_full_supplier_competition_evaluation_award_contract_flow(db, owner):
    service = ProcurementService(db)
    dps = open_dps(service, owner)
    supplier = service.ensure_supplier(owner.user_id, "Sample Supplier", "REG-100")
    application = service.apply(owner.user_id, dps["id"], supplier["id"], {"experience": "Provided"})
    application = service.submit_application(owner.user_id, application["id"], {"experience": "Provided"})
    application = service.decide_application(owner, application["id"], "under_review")
    application = service.decide_application(owner, application["id"], "admitted", "Requirements met")
    assert application["status"] == "admitted"

    competition = service.create_competition(owner, dps["id"], "Discovery call-off")
    quality = service.add_evaluation_criterion(owner, competition["id"], "Quality", "60", 10)
    service.add_evaluation_criterion(owner, competition["id"], "Price", "40", 10)
    competition = service.transition_competition(owner, competition["id"], "published")
    assert len(competition["invitations"]) == 1

    submission = service.submit_bid(owner.user_id, competition["id"], supplier["id"], "8800.00", {"method": "Agile"})
    service.transition_competition(owner, competition["id"], "closed")
    service.transition_competition(owner, competition["id"], "evaluation")
    with pytest.raises(ValueError, match="Declare conflicts"):
        service.evaluate(owner, submission["id"], quality["id"], "8")
    service.declare_conflict(owner, competition["id"], False, "No conflict")
    assert service.evaluate(owner, submission["id"], quality["id"], "8")["score"] == "8"
    award = service.create_award(owner, competition["id"], submission["id"], "Highest weighted score")
    award = service.transition_award(owner, award["id"], "approved")
    award = service.transition_award(owner, award["id"], "published")
    contract = service.create_contract(owner, award["id"], "CON-001")
    assert award["status"] == "published"
    assert contract["value_amount"] == "8800.00"


def test_competition_criteria_must_total_one_hundred(db, owner):
    service = ProcurementService(db)
    dps = open_dps(service, owner)
    competition = service.create_competition(owner, dps["id"], "Bad weights")
    service.add_evaluation_criterion(owner, competition["id"], "Quality", 80)
    with pytest.raises(ValueError, match="total 100"):
        service.transition_competition(owner, competition["id"], "published")


def test_invalid_lifecycle_transition_is_rejected(db, owner):
    service = ProcurementService(db)
    item = service.create_dps(owner, "Invalid transition")
    with pytest.raises(ValueError, match="Invalid transition"):
        service.transition_dps(owner, item["id"], "archived")


def test_custom_workflow_steps_and_transitions_are_tenant_scoped(db, owner):
    service = WorkflowService(db)
    workflow = service.create(owner, "Local approval", "dps")
    service.add_step(owner, workflow["id"], "draft", "Draft", "dps.edit", 0)
    service.add_step(owner, workflow["id"], "approved", "Approved", "dps.publish", 1)
    transition = service.add_transition(
        owner, workflow["id"], "draft", "approved", "Approve", "dps.publish"
    )
    assert transition["from_step"] == "draft"
    assert transition["to_step"] == "approved"
    with pytest.raises(ValueError, match="already exists"):
        service.add_transition(owner, workflow["id"], "draft", "approved", "Approve", "dps.publish")
