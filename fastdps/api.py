"""Versioned FastAPI integration surface."""
from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from fastdps import __version__
from fastdps.rbac import RoleService
from fastdps.security import Actor, csrf_valid
from fastdps.services.identity import IdentityService
from fastdps.services.audit import AuditService
from fastdps.services.documents import DocumentService
from fastdps.services.ocds import OcdsService
from fastdps.services.procurement import ProcurementService
from fastdps.services.workflows import WorkflowService


api = FastAPI(title="FastDPS API", version=__version__, docs_url="/docs", openapi_url="/openapi.json")


@api.exception_handler(PermissionError)
async def permission_error_handler(_request: Request, exc: PermissionError):
    return JSONResponse({"detail": str(exc)}, status_code=403)


@api.exception_handler(LookupError)
async def lookup_error_handler(_request: Request, exc: LookupError):
    return JSONResponse({"detail": str(exc)}, status_code=404)


@api.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


def actor_from_request(request: Request) -> Actor:
    auth = request.session.get("auth") if hasattr(request, "session") else None
    if not auth:
        raise HTTPException(401, "Authentication required")
    try:
        return IdentityService().actor(auth["user_id"], auth["organisation_id"])
    except (LookupError, PermissionError) as exc:
        raise HTTPException(403, str(exc)) from exc


def require_csrf(request: Request, x_csrf_token: str | None = Header(default=None)) -> None:
    if not csrf_valid(request.session, x_csrf_token):
        raise HTTPException(403, "Invalid CSRF token")


class DpsCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    reference: str = ""
    currency: str = "EUR"
    estimated_value: str | None = None
    opens_at: str | None = None
    closes_at: str | None = None


class CategoryCreate(BaseModel):
    code: str
    name: str
    description: str = ""


class Transition(BaseModel):
    target: str
    reason: str = ""


class CompetitionCreate(BaseModel):
    dps_id: str
    title: str
    description: str = ""
    deadline: str | None = None


class RoleWrite(BaseModel):
    name: str
    description: str = ""
    permissions: list[str] = Field(default_factory=list)


class CriterionCreate(BaseModel):
    name: str
    description: str = ""
    weight: str = "100"
    max_score: str = "10"


class SupplierWrite(BaseModel):
    name: str
    registration_number: str = ""
    website: str = ""


class ApplicationWrite(BaseModel):
    dps_id: str
    supplier_id: str
    answers: dict[str, Any] = Field(default_factory=dict)


class SubmissionWrite(BaseModel):
    supplier_id: str
    value_amount: str
    response: dict[str, Any] = Field(default_factory=dict)


class ConflictWrite(BaseModel):
    has_conflict: bool
    declaration: str


class EvaluationWrite(BaseModel):
    submission_id: str
    criterion_id: str
    score: str
    comment: str = ""


class AwardWrite(BaseModel):
    submission_id: str
    rationale: str = ""


class InvitationWrite(BaseModel):
    email: str
    role_ids: list[str]


class MembershipRoleWrite(BaseModel):
    role_id: str


class WorkflowWrite(BaseModel):
    name: str
    entity_type: str


class WorkflowStepWrite(BaseModel):
    key: str
    name: str
    permission: str
    order: int = 0


class WorkflowTransitionWrite(BaseModel):
    from_step: str
    to_step: str
    action_name: str
    permission: str


class ContractWrite(BaseModel):
    reference: str
    starts_at: str | None = None
    ends_at: str | None = None


@api.get("/health")
def health():
    return {"status": "ok", "product": "FastDPS", "version": __version__}


@api.get("/dps")
def list_dps(actor: Actor = Depends(actor_from_request)):
    return {"items": ProcurementService().list_dps(actor)}


@api.post("/dps", dependencies=[Depends(require_csrf)])
def create_dps(body: DpsCreate, actor: Actor = Depends(actor_from_request)):
    try:
        return ProcurementService().create_dps(actor, **body.model_dump())
    except (ValueError, PermissionError) as exc:
        raise HTTPException(400 if isinstance(exc, ValueError) else 403, str(exc)) from exc


@api.get("/dps/{dps_id}")
def get_dps(dps_id: str, actor: Actor = Depends(actor_from_request)):
    try:
        return ProcurementService().get_dps(actor, dps_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@api.post("/dps/{dps_id}/categories", dependencies=[Depends(require_csrf)])
def add_category(dps_id: str, body: CategoryCreate, actor: Actor = Depends(actor_from_request)):
    return ProcurementService().add_category(actor, dps_id, **body.model_dump())


@api.post("/dps/{dps_id}/transition", dependencies=[Depends(require_csrf)])
def transition_dps(dps_id: str, body: Transition, actor: Actor = Depends(actor_from_request)):
    try:
        return ProcurementService().transition_dps(actor, dps_id, body.target)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@api.get("/applications")
def applications(actor: Actor = Depends(actor_from_request)):
    return {"items": ProcurementService().list_applications(actor)}


@api.post("/applications/{application_id}/transition", dependencies=[Depends(require_csrf)])
def transition_application(application_id: str, body: Transition, actor: Actor = Depends(actor_from_request)):
    return ProcurementService().decide_application(actor, application_id, body.target, body.reason)


@api.get("/competitions")
def competitions(actor: Actor = Depends(actor_from_request)):
    return {"items": ProcurementService().list_competitions(actor)}


@api.get("/competitions/{competition_id}")
def competition(competition_id: str, actor: Actor = Depends(actor_from_request)):
    return ProcurementService().get_competition(actor, competition_id)


@api.post("/competitions", dependencies=[Depends(require_csrf)])
def create_competition(body: CompetitionCreate, actor: Actor = Depends(actor_from_request)):
    return ProcurementService().create_competition(actor, **body.model_dump())


@api.post("/competitions/{competition_id}/criteria", dependencies=[Depends(require_csrf)])
def create_evaluation_criterion(competition_id: str, body: CriterionCreate, actor: Actor = Depends(actor_from_request)):
    return ProcurementService().add_evaluation_criterion(actor, competition_id, body.name, body.weight, body.max_score)


@api.post("/competitions/{competition_id}/transition", dependencies=[Depends(require_csrf)])
def transition_competition(competition_id: str, body: Transition, actor: Actor = Depends(actor_from_request)):
    return ProcurementService().transition_competition(actor, competition_id, body.target)


@api.put("/supplier/profile", dependencies=[Depends(require_csrf)])
def supplier_profile(body: SupplierWrite, actor: Actor = Depends(actor_from_request)):
    return ProcurementService().ensure_supplier(actor.user_id, **body.model_dump())


@api.post("/supplier/applications", dependencies=[Depends(require_csrf)])
def supplier_application(body: ApplicationWrite, actor: Actor = Depends(actor_from_request)):
    service = ProcurementService()
    application = service.apply(actor.user_id, body.dps_id, body.supplier_id, body.answers)
    return service.submit_application(actor.user_id, application["id"], body.answers)


@api.post("/competitions/{competition_id}/submissions", dependencies=[Depends(require_csrf)])
def supplier_submission(competition_id: str, body: SubmissionWrite, actor: Actor = Depends(actor_from_request)):
    return ProcurementService().submit_bid(actor.user_id, competition_id, body.supplier_id, body.value_amount, body.response)


@api.put("/competitions/{competition_id}/conflict", dependencies=[Depends(require_csrf)])
def declare_conflict(competition_id: str, body: ConflictWrite, actor: Actor = Depends(actor_from_request)):
    ProcurementService().declare_conflict(actor, competition_id, body.has_conflict, body.declaration)
    return {"ok": True}


@api.put("/evaluations", dependencies=[Depends(require_csrf)])
def evaluate(body: EvaluationWrite, actor: Actor = Depends(actor_from_request)):
    return ProcurementService().evaluate(actor, **body.model_dump())


@api.post("/competitions/{competition_id}/awards", dependencies=[Depends(require_csrf)])
def create_award(competition_id: str, body: AwardWrite, actor: Actor = Depends(actor_from_request)):
    return ProcurementService().create_award(actor, competition_id, body.submission_id, body.rationale)


@api.post("/awards/{award_id}/transition", dependencies=[Depends(require_csrf)])
def transition_award(award_id: str, body: Transition, actor: Actor = Depends(actor_from_request)):
    return ProcurementService().transition_award(actor, award_id, body.target)


@api.post("/awards/{award_id}/contracts", dependencies=[Depends(require_csrf)])
def create_contract(award_id: str, body: ContractWrite, actor: Actor = Depends(actor_from_request)):
    return ProcurementService().create_contract(actor, award_id, body.reference, body.starts_at, body.ends_at)


@api.get("/roles")
def roles(actor: Actor = Depends(actor_from_request)):
    actor.require("roles.manage")
    service = RoleService()
    return {"items": service.list_roles(actor.organisation_id), "permissions": service.list_permissions()}


@api.post("/roles", dependencies=[Depends(require_csrf)])
def create_role(body: RoleWrite, actor: Actor = Depends(actor_from_request)):
    actor.require("roles.manage")
    if not actor.is_platform_admin and not set(body.permissions).issubset(actor.permissions):
        raise HTTPException(403, "You cannot grant rights you do not hold")
    return RoleService().create_role(actor.organisation_id, body.name, body.description, body.permissions, actor.user_id)


@api.put("/roles/{role_id}", dependencies=[Depends(require_csrf)])
def update_role(role_id: str, body: RoleWrite, actor: Actor = Depends(actor_from_request)):
    actor.require("roles.manage")
    if not actor.is_platform_admin and not set(body.permissions).issubset(actor.permissions):
        raise HTTPException(403, "You cannot grant rights you do not hold")
    return RoleService().update_role(actor.organisation_id, role_id, body.name, body.description, body.permissions, actor.user_id)


@api.delete("/roles/{role_id}", dependencies=[Depends(require_csrf)])
def archive_role(role_id: str, actor: Actor = Depends(actor_from_request)):
    actor.require("roles.manage")
    RoleService().archive_role(actor.organisation_id, role_id, actor.user_id)
    return {"ok": True}


@api.get("/members")
def members(actor: Actor = Depends(actor_from_request)):
    return {"items": IdentityService().list_members(actor)}


@api.post("/invitations", dependencies=[Depends(require_csrf)])
def invite_member(body: InvitationWrite, actor: Actor = Depends(actor_from_request)):
    invitation, raw_token = IdentityService().invite(actor, body.email, body.role_ids)
    return {"invitation": invitation, "token": raw_token}


@api.post("/members/{membership_id}/roles", dependencies=[Depends(require_csrf)])
def assign_member_role(membership_id: str, body: MembershipRoleWrite, actor: Actor = Depends(actor_from_request)):
    IdentityService().assign_role(actor, membership_id, body.role_id)
    return {"ok": True}


@api.delete("/members/{membership_id}/roles/{role_id}", dependencies=[Depends(require_csrf)])
def remove_member_role(membership_id: str, role_id: str, actor: Actor = Depends(actor_from_request)):
    IdentityService().remove_role(actor, membership_id, role_id)
    return {"ok": True}


@api.get("/workflows")
def workflows(actor: Actor = Depends(actor_from_request)):
    return {"items": WorkflowService().list(actor)}


@api.post("/workflows", dependencies=[Depends(require_csrf)])
def create_workflow(body: WorkflowWrite, actor: Actor = Depends(actor_from_request)):
    return WorkflowService().create(actor, body.name, body.entity_type)


@api.post("/workflows/{workflow_id}/steps", dependencies=[Depends(require_csrf)])
def create_workflow_step(workflow_id: str, body: WorkflowStepWrite, actor: Actor = Depends(actor_from_request)):
    return WorkflowService().add_step(actor, workflow_id, body.key, body.name, body.permission, body.order)


@api.post("/workflows/{workflow_id}/transitions", dependencies=[Depends(require_csrf)])
def create_workflow_transition(workflow_id: str, body: WorkflowTransitionWrite,
                               actor: Actor = Depends(actor_from_request)):
    return WorkflowService().add_transition(
        actor, workflow_id, body.from_step, body.to_step, body.action_name, body.permission
    )


@api.get("/audit")
def audit(actor: Actor = Depends(actor_from_request)):
    return {"items": AuditService().list(actor)}


@api.get("/documents")
def documents(actor: Actor = Depends(actor_from_request)):
    return {"items": DocumentService().list(actor)}


@api.post("/documents", dependencies=[Depends(require_csrf)])
async def upload_document(entity_type: str, entity_id: str, title: str, file: UploadFile, actor: Actor = Depends(actor_from_request)):
    return DocumentService().add(actor, entity_type, entity_id, title, file.filename or "document.bin", await file.read(), file.content_type or "application/octet-stream")


@api.post("/documents/{document_id}/versions", dependencies=[Depends(require_csrf)])
async def upload_document_version(document_id: str, file: UploadFile, actor: Actor = Depends(actor_from_request)):
    return DocumentService().add_version(
        actor, document_id, file.filename or "document.bin", await file.read(),
        file.content_type or "application/octet-stream",
    )


@api.get("/documents/versions/{version_id}")
def download_document(version_id: str, actor: Actor = Depends(actor_from_request)):
    path, version = DocumentService().version_path(actor, version_id)
    return FileResponse(path, filename=version["file_name"], media_type=version["mime_type"])


@api.post("/ocds/import", dependencies=[Depends(require_csrf)])
async def import_ocds(file: UploadFile, actor: Actor = Depends(actor_from_request)):
    content = await file.read()
    if (file.filename or "").lower().endswith(".xml"):
        return OcdsService().import_xml(actor, content, file.filename or "notice.xml")
    return OcdsService().import_json(actor, content, file.filename or "release.json")


@api.get("/ocds/notices")
def search_notices(q: str = "", actor: Actor = Depends(actor_from_request)):
    return {"items": OcdsService().notices(actor, q)}


@api.get("/dps/{dps_id}/ocds")
def export_ocds(dps_id: str, actor: Actor = Depends(actor_from_request)):
    return OcdsService().export_dps(actor, dps_id)
