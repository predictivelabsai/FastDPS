"""FastDPS FastHTML entry point and browser routes."""
from __future__ import annotations

import json
import os
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()

from fasthtml.common import *
from starlette.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from fastdps import __version__
from fastdps.api import api
from fastdps.auth import google_authorize_url, google_enabled, google_exchange
from fastdps.bootstrap import ensure_demo, initialize
from fastdps.config import settings
from fastdps.database import get_database
from fastdps.rbac import RoleService
from fastdps.security import Actor, csrf_valid, token
from fastdps.services.audit import AuditService
from fastdps.services.chat import ChatService
from fastdps.services.documents import DocumentService
from fastdps.services.identity import IdentityService
from fastdps.services.ocds import OcdsService
from fastdps.services.procurement import ProcurementService
from fastdps.web.ui import (
    applications_page, audit_page, auth_page, chat_page, competition_detail_page,
    competitions_page, documents_page, dps_detail_page, dps_list_page, dps_new_page,
    imports_page, landing_page, roles_page, supplier_portal_page,
    invitation_page,
)


app, rt = fast_app(
    live=False, pico=False, secret_key=settings.secret, max_age=8 * 60 * 60,
    same_site="lax", sess_https_only=settings.public_url.startswith("https://"),
)
app.mount("/static", StaticFiles(directory=settings.root / "static"), name="static")
app.mount("/api/v1", api)


@app.on_event("startup")
async def startup() -> None:
    initialize()


def _login(session: dict, user: dict, organisation: dict) -> None:
    session.clear()
    session["auth"] = {"user_id": user["id"], "organisation_id": organisation["id"]}
    session["csrf_token"] = token()


def _actor(request) -> Actor | None:
    auth = request.session.get("auth")
    if not auth:
        return None
    try:
        return IdentityService().actor(auth["user_id"], auth["organisation_id"])
    except (LookupError, PermissionError):
        request.session.clear()
        return None


def _required(request, permission: str | None = None) -> Actor | Response:
    actor = _actor(request)
    if not actor:
        return RedirectResponse(f"/login?next={quote(request.url.path, safe='')}", status_code=303)
    if permission and not actor.can(permission):
        return PlainTextResponse("Forbidden", status_code=403)
    return actor


async def _form(request, permission: str | None = None):
    actor = _required(request, permission)
    if isinstance(actor, Response):
        return actor, None
    data = await request.form()
    if not csrf_valid(request.session, data.get("csrf") or request.headers.get("x-csrf-token")):
        return PlainTextResponse("Invalid CSRF token", status_code=403), None
    return actor, data


@rt("/")
def home(request):
    return RedirectResponse("/app", status_code=303) if _actor(request) else landing_page()


@rt("/login", methods=["GET"])
def login_form(error: str = ""):
    messages = {"invalid": "The email or password was not recognised.", "google": "Google sign-in is unavailable or was not authorised.", "required": "Sign in to continue."}
    return auth_page("login", messages.get(error, error))


@rt("/login", methods=["POST"])
async def login_submit(request):
    data = await request.form()
    user = IdentityService().authenticate(str(data.get("email", "")), str(data.get("password", "")))
    if not user:
        return RedirectResponse("/login?error=invalid", status_code=303)
    memberships = IdentityService().memberships(user["id"])
    if not memberships:
        return RedirectResponse("/login?error=No+active+workspace", status_code=303)
    organisation = IdentityService().organisation(memberships[0]["organisation_id"])
    pending = request.session.get("pending_invitation", "")
    _login(request.session, user, organisation)
    return RedirectResponse(f"/invitations/{pending}" if pending else "/app", status_code=303)


@rt("/signup", methods=["GET"])
def signup_form(error: str = ""):
    return auth_page("signup", error)


@rt("/signup", methods=["POST"])
async def signup_submit(request):
    data = await request.form()
    try:
        user, organisation = IdentityService().create_workspace(
            str(data.get("email", "")), str(data.get("password", "")),
            str(data.get("name", "")), str(data.get("organisation", "")),
        )
        ProcurementService().seed_workflows(organisation["id"])
    except Exception as exc:
        return auth_page("signup", str(exc))
    pending = request.session.get("pending_invitation", "")
    _login(request.session, user, organisation)
    return RedirectResponse(f"/invitations/{pending}" if pending else "/app", status_code=303)


@rt("/auth/google")
def google_start(request):
    if not google_enabled():
        return RedirectResponse("/login?error=Google+sign-in+is+not+configured", status_code=303)
    return RedirectResponse(google_authorize_url(request.session), status_code=303)


@rt("/auth/google/callback")
def google_callback(request, code: str = "", state: str = ""):
    try:
        pending = request.session.get("pending_invitation", "")
        profile = google_exchange(code, state, request.session)
        user, organisation = IdentityService().ensure_oauth_workspace(profile["email"], profile["name"])
        ProcurementService().seed_workflows(organisation["id"])
        _login(request.session, user, organisation)
        return RedirectResponse(f"/invitations/{pending}" if pending else "/app", status_code=303)
    except Exception:
        return RedirectResponse("/login?error=google", status_code=303)


@rt("/auth/test")
def test_auth(request):
    if not settings.allow_test_auth:
        return PlainTextResponse("Not found", status_code=404)
    user, organisation = ensure_demo()
    _login(request.session, user, organisation)
    return RedirectResponse("/app", status_code=303)


@rt("/logout")
def logout(request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@rt("/healthz")
def healthz():
    db = get_database()
    try:
        migrations = int(db.scalar("SELECT COUNT(*) FROM schema_migrations") or 0)
        database_status = "ok"
    except Exception:
        migrations, database_status = 0, "error"
    return JSONResponse({
        "status": "ok" if database_status == "ok" else "degraded", "product": "FastDPS", "version": __version__,
        "environment": settings.environment, "database": {"status": database_status, "dialect": db.dialect, "schema": db.schema if db.dialect == "postgres" else None, "migrations": migrations},
        "llm": "configured" if settings.llm_api_key and settings.llm_model else "deterministic",
    }, status_code=200 if database_status == "ok" else 503)


@rt("/developers")
def developers():
    return RedirectResponse("/api/v1/docs", status_code=303)


def robots(_request):
    return PlainTextResponse(f"User-agent: *\nAllow: /\nSitemap: {settings.public_url}/sitemap.xml\n")


def sitemap(_request):
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f'<url><loc>{settings.public_url}/</loc></url>'
        f'<url><loc>{settings.public_url}/developers</loc></url>'
        '</urlset>'
    )
    return Response(body, media_type="application/xml")


# FastHTML's route wrapper reserves dotted suffixes for response transforms;
# register machine-readable files directly with Starlette.
app.router.routes.insert(0, Route("/sitemap.xml", sitemap, methods=["GET"]))
app.router.routes.insert(0, Route("/robots.txt", robots, methods=["GET"]))


@rt("/app")
def workspace(request, sid: str = ""):
    actor = _required(request, "chat.use")
    if isinstance(actor, Response):
        return actor
    service = ChatService()
    messages = service.messages(actor, sid) if sid else []
    return chat_page(actor, service.sessions(actor), messages, sid, ProcurementService().dashboard(actor), request.session["csrf_token"])


def _sse(name: str, payload) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, default=str)}\n\n"


@rt("/api/chat/stream", methods=["POST"])
async def chat_stream(request):
    actor = _required(request, "chat.use")
    if isinstance(actor, Response):
        return JSONResponse({"error": "Authentication required"}, status_code=401)
    data = await request.form()
    if not csrf_valid(request.session, request.headers.get("x-csrf-token")):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)
    try:
        _, events = ChatService().respond(actor, str(data.get("message", "")), str(data.get("sid", "")) or None)
    except Exception as exc:
        events = [("error", {"message": str(exc)})]

    async def event_stream():
        for name, payload in events:
            yield _sse(name, payload)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@rt("/api/chat/actions/{action_id}/confirm", methods=["POST"])
async def confirm_chat_action(request, action_id: str):
    actor = _required(request, "chat.use")
    if isinstance(actor, Response):
        return JSONResponse({"error": "Authentication required"}, status_code=401)
    if not csrf_valid(request.session, request.headers.get("x-csrf-token")):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)
    try:
        return JSONResponse(ChatService().confirm(actor, action_id))
    except (LookupError, ValueError, PermissionError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)


@rt("/dps")
def dps_list(request):
    actor = _required(request, "dps.view")
    if isinstance(actor, Response): return actor
    return dps_list_page(actor, ProcurementService().list_dps(actor), request.session["csrf_token"])


@rt("/dps/new", methods=["GET"])
def dps_new(request):
    actor = _required(request, "dps.create")
    if isinstance(actor, Response): return actor
    return dps_new_page(actor, request.session["csrf_token"])


@rt("/dps/new", methods=["POST"])
async def dps_create(request):
    actor, data = await _form(request, "dps.create")
    if data is None: return actor
    try:
        item = ProcurementService().create_dps(actor, title=str(data.get("title", "")), description=str(data.get("description", "")),
                                               reference=str(data.get("reference", "")), currency=str(data.get("currency", "EUR")),
                                               estimated_value=data.get("estimated_value"), opens_at=data.get("opens_at"), closes_at=data.get("closes_at"))
        return RedirectResponse(f"/dps/{item['id']}", status_code=303)
    except Exception as exc:
        return dps_new_page(actor, request.session["csrf_token"], str(exc))


@rt("/dps/{dps_id}")
def dps_detail(request, dps_id: str):
    actor = _required(request, "dps.view")
    if isinstance(actor, Response): return actor
    try:
        return dps_detail_page(actor, ProcurementService().get_dps(actor, dps_id), request.session["csrf_token"])
    except LookupError:
        return PlainTextResponse("Not found", status_code=404)


@rt("/dps/{dps_id}/categories", methods=["POST"])
async def category_add(request, dps_id: str):
    actor, data = await _form(request, "dps.edit")
    if data is None: return actor
    ProcurementService().add_category(actor, dps_id, str(data.get("code", "")), str(data.get("name", "")), str(data.get("description", "")))
    return RedirectResponse(f"/dps/{dps_id}", status_code=303)


@rt("/dps/{dps_id}/criteria", methods=["POST"])
async def criterion_add(request, dps_id: str):
    actor, data = await _form(request, "dps.edit")
    if data is None: return actor
    ProcurementService().add_criterion(actor, dps_id, str(data.get("name", "")), str(data.get("description", "")))
    return RedirectResponse(f"/dps/{dps_id}", status_code=303)


@rt("/dps/{dps_id}/transition", methods=["POST"])
async def dps_transition(request, dps_id: str):
    actor, data = await _form(request, "dps.publish")
    if data is None: return actor
    ProcurementService().transition_dps(actor, dps_id, str(data.get("target", "")))
    return RedirectResponse(f"/dps/{dps_id}", status_code=303)


@rt("/dps/{dps_id}/ocds")
def dps_ocds(request, dps_id: str):
    actor = _required(request, "ocds.export")
    if isinstance(actor, Response): return actor
    content = json.dumps(OcdsService().export_dps(actor, dps_id), indent=2).encode()
    return Response(content, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="fastdps-{dps_id}.json"'})


@rt("/suppliers")
def suppliers(request):
    actor = _required(request, "suppliers.view")
    if isinstance(actor, Response): return actor
    return applications_page(actor, ProcurementService().list_applications(actor), request.session["csrf_token"])


@rt("/applications/{application_id}/transition", methods=["POST"])
async def application_transition(request, application_id: str):
    actor, data = await _form(request, "suppliers.review")
    if data is None: return actor
    ProcurementService().decide_application(actor, application_id, str(data.get("target", "")), str(data.get("reason", "")))
    return RedirectResponse("/suppliers", status_code=303)


@rt("/competitions", methods=["GET"])
def competitions(request):
    actor = _required(request, "competitions.view")
    if isinstance(actor, Response): return actor
    service = ProcurementService()
    return competitions_page(actor, service.list_competitions(actor), service.list_dps(actor), request.session["csrf_token"])


@rt("/competitions", methods=["POST"])
async def competition_create(request):
    actor, data = await _form(request, "competitions.manage")
    if data is None: return actor
    item = ProcurementService().create_competition(actor, str(data.get("dps_id", "")), str(data.get("title", "")), deadline=str(data.get("deadline", "")) or None)
    return RedirectResponse(f"/competitions/{item['id']}", status_code=303)


@rt("/competitions/{competition_id}")
def competition_detail(request, competition_id: str):
    actor = _required(request, "competitions.view")
    if isinstance(actor, Response): return actor
    return competition_detail_page(actor, ProcurementService().get_competition(actor, competition_id), request.session["csrf_token"])


@rt("/competitions/{competition_id}/transition", methods=["POST"])
async def competition_transition(request, competition_id: str):
    actor, data = await _form(request, "competitions.manage")
    if data is None: return actor
    ProcurementService().transition_competition(actor, competition_id, str(data.get("target", "")))
    return RedirectResponse(f"/competitions/{competition_id}", status_code=303)


@rt("/competitions/{competition_id}/criteria", methods=["POST"])
async def competition_criterion(request, competition_id: str):
    actor, data = await _form(request, "competitions.manage")
    if data is None: return actor
    ProcurementService().add_evaluation_criterion(actor, competition_id, str(data.get("name", "")), str(data.get("weight", "100")))
    return RedirectResponse(f"/competitions/{competition_id}", status_code=303)


@rt("/documents", methods=["GET"])
def documents(request):
    actor = _required(request, "dps.view")
    if isinstance(actor, Response): return actor
    return documents_page(actor, DocumentService().list(actor), ProcurementService().list_dps(actor), request.session["csrf_token"])


@rt("/documents", methods=["POST"])
async def document_upload(request):
    actor, data = await _form(request, "documents.manage")
    if data is None: return actor
    upload = data.get("file")
    content = await upload.read()
    DocumentService().add(actor, "dps", str(data.get("entity_id", "")), str(data.get("title", "")), upload.filename, content, upload.content_type)
    return RedirectResponse("/documents", status_code=303)


@rt("/admin/roles", methods=["GET"])
def role_admin(request, edit: str = "", invite: str = ""):
    actor = _required(request, "roles.manage")
    if isinstance(actor, Response): return actor
    service = RoleService()
    editing = service.get_role(actor.organisation_id, edit) if edit else None
    identity = IdentityService()
    invite_link = f"Invitation link: {settings.public_url}/invitations/{invite}" if invite else ""
    return roles_page(actor, service.list_roles(actor.organisation_id), service.list_permissions(), identity.list_members(actor), identity.invitations(actor), request.session["csrf_token"], editing, invite_link)


async def _role_write(request, role_id: str | None = None):
    actor, data = await _form(request, "roles.manage")
    if data is None: return actor
    permissions = data.getlist("permissions")
    if not actor.is_platform_admin and not set(permissions).issubset(actor.permissions):
        return PlainTextResponse("You cannot grant rights you do not hold", status_code=403)
    service = RoleService()
    if role_id:
        service.update_role(actor.organisation_id, role_id, str(data.get("name", "")), str(data.get("description", "")), permissions, actor.user_id)
    else:
        service.create_role(actor.organisation_id, str(data.get("name", "")), str(data.get("description", "")), permissions, actor.user_id)
    return RedirectResponse("/admin/roles", status_code=303)


@rt("/admin/roles", methods=["POST"])
async def role_create(request):
    return await _role_write(request)


@rt("/admin/roles/{role_id}", methods=["POST"])
async def role_update(request, role_id: str):
    return await _role_write(request, role_id)


@rt("/admin/invitations", methods=["POST"])
async def invitation_create(request):
    actor, data = await _form(request, "org.manage")
    if data is None: return actor
    _, raw_token = IdentityService().invite(actor, str(data.get("email", "")), [str(data.get("role_id", ""))])
    return RedirectResponse(f"/admin/roles?invite={quote(raw_token, safe='')}", status_code=303)


@rt("/admin/members/{membership_id}/roles", methods=["POST"])
async def member_role_assign(request, membership_id: str):
    actor, data = await _form(request, "roles.manage")
    if data is None: return actor
    IdentityService().assign_role(actor, membership_id, str(data.get("role_id", "")))
    return RedirectResponse("/admin/roles", status_code=303)


@rt("/admin/members/{membership_id}/roles/{role_id}/remove", methods=["POST"])
async def member_role_remove(request, membership_id: str, role_id: str):
    actor, data = await _form(request, "roles.manage")
    if data is None: return actor
    try:
        IdentityService().remove_role(actor, membership_id, role_id)
    except ValueError as exc:
        return PlainTextResponse(str(exc), status_code=409)
    return RedirectResponse("/admin/roles", status_code=303)


@rt("/invitations/{raw_token}", methods=["GET"])
def invitation_view(request, raw_token: str):
    invitation = IdentityService().invitation(raw_token)
    actor = _actor(request)
    if not actor:
        request.session["pending_invitation"] = raw_token
    return invitation_page(invitation, bool(actor), request.session.get("csrf_token", ""))


@rt("/invitations/{raw_token}", methods=["POST"])
async def invitation_accept(request, raw_token: str):
    actor, data = await _form(request)
    if data is None: return actor
    try:
        organisation = IdentityService().accept_invitation(actor.user_id, raw_token)
    except (ValueError, PermissionError) as exc:
        return invitation_page(IdentityService().invitation(raw_token), True, request.session["csrf_token"], str(exc))
    request.session["auth"]["organisation_id"] = organisation["id"]
    return RedirectResponse("/app", status_code=303)


@rt("/imports", methods=["GET"])
def imports(request):
    actor = _required(request, "ocds.import")
    if isinstance(actor, Response): return actor
    service = OcdsService()
    return imports_page(actor, service.jobs(actor), service.notices(actor), request.session["csrf_token"])


@rt("/imports", methods=["POST"])
async def import_upload(request):
    actor, data = await _form(request, "ocds.import")
    if data is None: return actor
    upload = data.get("file")
    content = await upload.read()
    if upload.filename.lower().endswith(".xml"):
        OcdsService().import_xml(actor, content, upload.filename)
    else:
        OcdsService().import_json(actor, content, upload.filename)
    return RedirectResponse("/imports", status_code=303)


@rt("/audit")
def audit(request):
    actor = _required(request, "audit.view")
    if isinstance(actor, Response): return actor
    return audit_page(actor, AuditService().list(actor), request.session["csrf_token"])


@rt("/supplier", methods=["GET"])
def supplier_portal(request):
    actor = _required(request)
    if isinstance(actor, Response): return actor
    db = get_database()
    supplier = db.one("SELECT * FROM supplier_organisations WHERE owner_user_id=?", (actor.user_id,))
    applications = db.rows("SELECT * FROM admission_applications WHERE supplier_id=? ORDER BY updated_at DESC", (supplier["id"],)) if supplier else []
    invitations = db.rows(
        "SELECT c.*,s.status submission_status FROM competition_invitations i JOIN competitions c ON c.id=i.competition_id "
        "LEFT JOIN submissions s ON s.competition_id=c.id AND s.supplier_id=i.supplier_id "
        "WHERE i.supplier_id=? AND c.status='published' ORDER BY c.deadline", (supplier["id"],)
    ) if supplier else []
    return supplier_portal_page(actor, supplier, ProcurementService().public_dps(), applications, invitations, request.session["csrf_token"])


@rt("/supplier/profile", methods=["POST"])
async def supplier_profile(request):
    actor, data = await _form(request)
    if data is None: return actor
    ProcurementService().ensure_supplier(actor.user_id, str(data.get("name", "")), str(data.get("registration_number", "")), str(data.get("website", "")))
    return RedirectResponse("/supplier", status_code=303)


@rt("/supplier/apply", methods=["POST"])
async def supplier_apply(request):
    actor, data = await _form(request)
    if data is None: return actor
    supplier = get_database().one("SELECT * FROM supplier_organisations WHERE owner_user_id=?", (actor.user_id,))
    if not supplier:
        return PlainTextResponse("Create a supplier profile first", status_code=409)
    application = ProcurementService().apply(actor.user_id, str(data.get("dps_id", "")), supplier["id"])
    ProcurementService().submit_application(actor.user_id, application["id"], {})
    return RedirectResponse("/supplier", status_code=303)


@rt("/supplier/competitions/{competition_id}/submit", methods=["POST"])
async def supplier_submit(request, competition_id: str):
    actor, data = await _form(request)
    if data is None: return actor
    ProcurementService().submit_bid(actor.user_id, competition_id, str(data.get("supplier_id", "")), str(data.get("value_amount", "")), {"summary": str(data.get("response", ""))})
    return RedirectResponse("/supplier", status_code=303)


@rt("/competitions/{competition_id}/conflict", methods=["POST"])
async def competition_conflict(request, competition_id: str):
    actor, data = await _form(request, "submissions.evaluate")
    if data is None: return actor
    ProcurementService().declare_conflict(actor, competition_id, bool(data.get("has_conflict")), str(data.get("declaration", "")))
    return RedirectResponse(f"/competitions/{competition_id}", status_code=303)


@rt("/competitions/{competition_id}/evaluate", methods=["POST"])
async def competition_evaluate(request, competition_id: str):
    actor, data = await _form(request, "submissions.evaluate")
    if data is None: return actor
    ProcurementService().evaluate(actor, str(data.get("submission_id", "")), str(data.get("criterion_id", "")), str(data.get("score", "")))
    return RedirectResponse(f"/competitions/{competition_id}", status_code=303)


@rt("/competitions/{competition_id}/awards", methods=["POST"])
async def competition_award(request, competition_id: str):
    actor, data = await _form(request, "awards.approve")
    if data is None: return actor
    ProcurementService().create_award(actor, competition_id, str(data.get("submission_id", "")), str(data.get("rationale", "")))
    return RedirectResponse(f"/competitions/{competition_id}", status_code=303)


@rt("/awards/{award_id}/transition", methods=["POST"])
async def award_transition(request, award_id: str):
    actor, data = await _form(request, "awards.approve")
    if data is None: return actor
    award = ProcurementService().transition_award(actor, award_id, str(data.get("target", "")))
    return RedirectResponse(f"/competitions/{award['competition_id']}", status_code=303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_app:app", host="0.0.0.0", port=settings.port, reload=os.getenv("FASTDPS_RELOAD", "false").lower() == "true")
