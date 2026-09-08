"""FastHTML components for the public site and authenticated workspace."""
from __future__ import annotations

from fasthtml.common import *

from fastdps.config import settings
from fastdps.security import Actor


def head(title: str, description: str = "Open-source, chat-first dynamic procurement.", canonical_path: str = "") -> Head:
    canonical = f"{settings.public_url}{canonical_path}" if canonical_path else ""
    return Head(
        Meta(charset="utf-8"),
        Meta(name="viewport", content="width=device-width, initial-scale=1, viewport-fit=cover"),
        Meta(name="theme-color", content="#172033"),
        Meta(name="description", content=description),
        Meta(property="og:title", content=f"{title} · FastDPS"),
        Meta(property="og:description", content=description),
        Meta(property="og:type", content="website"),
        Meta(property="og:url", content=canonical) if canonical else None,
        Meta(name="twitter:card", content="summary"),
        Title(f"{title} · FastDPS"),
        Link(rel="canonical", href=canonical) if canonical else None,
        Link(rel="icon", href="/static/favicon.svg", type="image/svg+xml"),
        Link(rel="preconnect", href="https://fonts.googleapis.com"),
        Link(rel="preconnect", href="https://fonts.gstatic.com", crossorigin=""),
        Link(rel="stylesheet", href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Newsreader:opsz,wght@6..72,600&display=swap"),
        Link(rel="stylesheet", href="/static/app.css?v=1"),
    )


def logo() -> A:
    return A(Span("F", cls="brand-mark"), Span("Fast", cls="brand-fast"), Span("DPS", cls="brand-accent"), href="/", cls="brand")


def landing_page() -> Html:
    description = "Create dynamic purchasing systems, continuously qualify suppliers, and run auditable call-off competitions in an open workspace."
    return Html(
        head("Open dynamic procurement", description, "/"),
        Body(
            Header(logo(), Nav(A("Pricing", href="#pricing", cls="quiet-link"), A("Sign in", href="/login", cls="quiet-link"), A("Start locally", href="/signup", cls="button small")), cls="public-nav"),
            Main(
                Section(
                    Div(
                        P("OPEN DYNAMIC PROCUREMENT", cls="eyebrow"),
                        H1("Run fair, flexible procurement without a heavyweight suite."),
                        P("Create dynamic purchasing systems, continuously qualify suppliers, run call-off competitions, and keep every decision auditable — from one open workspace.", cls="hero-copy"),
                        Div(A("Create your workspace", href="/signup", cls="button"), A("View the API", href="/api/v1/docs", cls="button secondary"), cls="hero-actions"),
                        P("MIT licensed · SQLite included · PostgreSQL ready", cls="proof"),
                        cls="hero-content",
                    ),
                    Div(
                        Div(Span("You", cls="chat-label"), P("Create a DPS for digital services"), cls="landing-message user"),
                        Div(Span("FastDPS", cls="chat-label"), P("I prepared a draft with an open admission stage. Review the scope, categories, and dates before creating it."), cls="landing-message assistant"),
                        Div(P("Draft DPS"), Strong("Digital services"), Span("Awaiting confirmation", cls="status amber"), cls="landing-artifact"),
                        cls="hero-demo",
                    ),
                    cls="hero",
                ),
                Section(
                    Div(H2("Continuous admission"), P("Suppliers can apply throughout the life of an open system, with governed review and clarification.")),
                    Div(H2("Competitive call-offs"), P("Invite admitted suppliers, receive submissions, score transparently, and approve awards.")),
                    Div(H2("Chat with guardrails"), P("Draft and navigate conversationally. Every consequential action remains permission-checked and confirmed.")),
                    cls="feature-grid",
                ),

                Section(
                    P("PRICING", cls="eyebrow"),
                    H2("Simple pricing for every FastSME product."),
                    P("Every Fast* product uses the same two options: bring your own cloud for free, or host with us for €1 per month."),
                    Div(
                        Article(P("BYOC", cls="eyebrow"), H3("Bring Your Own Cloud"), P(Strong("Free")), P("Self-host on your own infrastructure or cloud. Full control of data and upgrades. No per-seat platform fee.")),
                        Article(P("HOSTED", cls="eyebrow"), H3("Host with us"), P(Strong("€1 / month")), P("We run the product for you on FastSME-managed infrastructure. €1 per product per month.")),
                        cls="feature-grid",
                    ),
                    id="pricing",
                    cls="open-source-block",
                ),
                Section(
                    P("PORTABLE BY DESIGN", cls="eyebrow"), H2("Your process, your data, your deployment."),
                    P("FastDPS runs locally with SQLite and exposes a versioned API. Move to PostgreSQL when your deployment is ready, without changing the domain model."),
                    cls="open-source-block",
                ),
                cls="public-main",
            ),
            Footer(
                Span("FastDPS · Open-source dynamic procurement"),
                A("GitHub", href="https://github.com/predictivelabsai/FastDPS"),
                A("API", href="/developers"),
                cls="public-footer",
            ),
        ),
    )


def auth_page(mode: str = "login", error: str = "") -> Html:
    signup = mode == "signup"
    return Html(
        head("Create workspace" if signup else "Sign in"),
        Body(
            Main(
                A("← Back", href="/", cls="back-link"),
                Div(
                    logo(),
                    H1("Create your workspace" if signup else "Welcome back"),
                    P("Start with a local account. Google sign-in can be configured from environment variables." if signup else "Sign in to continue to your procurement workspace.", cls="muted"),
                    Div(error, cls="alert error") if error else None,
                    Form(
                        Label("Name", Input(name="name", required=True, autocomplete="name")) if signup else None,
                        Label("Organisation", Input(name="organisation", required=True, autocomplete="organization")) if signup else None,
                        Label("Email", Input(type="email", name="email", required=True, autocomplete="email")),
                        Label("Password", Input(type="password", name="password", required=True, minlength="10", autocomplete="new-password" if signup else "current-password")),
                        Button("Create workspace" if signup else "Sign in", type="submit", cls="button full"),
                        action="/signup" if signup else "/login", method="post", cls="auth-form",
                    ),
                    A("Continue with Google", href="/auth/google", cls="button secondary full"),
                    P(A("Already have an account? Sign in", href="/login") if signup else A("Need a workspace? Create one", href="/signup"), cls="auth-switch"),
                    cls="auth-card",
                ),
                cls="auth-page",
            )
        ),
    )


NAV = (
    ("Workspace", "/app", "chat"),
    ("Dynamic systems", "/dps", "dps"),
    ("Suppliers", "/suppliers", "suppliers"),
    ("Competitions", "/competitions", "competitions"),
    ("Documents", "/documents", "documents"),
    ("Open data", "/imports", "imports"),
    ("Supplier portal", "/supplier", "supplier"),
    ("Roles & access", "/admin/roles", "roles"),
    ("Audit trail", "/audit", "audit"),
)


def sidebar(actor: Actor, active: str, sessions: list[dict] | None = None) -> Aside:
    visible = []
    permission_for = {
        "suppliers": "suppliers.view", "competitions": "competitions.view", "documents": "dps.view",
        "imports": "ocds.import", "roles": "roles.manage", "audit": "audit.view", "chat": "chat.use", "dps": "dps.view",
    }
    for label, href, key in NAV:
        required = permission_for.get(key)
        if required and not actor.can(required):
            continue
        visible.append(A(Span(label), href=href, cls=f"nav-item {'active' if active == key else ''}"))
    history = []
    if active == "chat":
        history = [
            Div(P("CONVERSATIONS", cls="nav-section-label"), *[
                A(item["title"], href=f"/app?sid={item['id']}", cls="history-item") for item in (sessions or [])
            ], cls="history")
        ]
    return Aside(
        Div(logo(), Button("×", type="button", cls="drawer-close", onclick="toggleNav()"), cls="sidebar-head"),
        A("+ New conversation", href="/app", cls="new-chat") if actor.can("chat.use") else None,
        Nav(*visible, cls="side-nav"),
        *history,
        Div(
            Div(Span(actor.name[:1].upper(), cls="avatar"), Div(Strong(actor.name), Small(actor.organisation_name)), cls="identity"),
            A("Sign out", href="/logout", cls="signout"),
            cls="sidebar-foot",
        ),
        id="sidebar", cls="sidebar",
    )


def shell(actor: Actor, active: str, content, title: str, sessions=None, right=None, csrf: str = "") -> Html:
    return Html(
        head(title),
        Body(
            Div(cls="drawer-overlay", onclick="toggleNav()"),
            sidebar(actor, active, sessions),
            Main(
                Header(Button("☰", type="button", cls="mobile-nav", onclick="toggleNav()"), Div(H1(title), Small(actor.organisation_name)),
                       Div(Span(actor.name, cls="top-user")), cls="workspace-head"),
                content,
                cls="workspace-main",
            ),
            Aside(right or empty_artifact(), id="artifact-pane", cls="artifact-pane"),
            Button("Results", type="button", id="artifact-toggle", cls="artifact-toggle", onclick="toggleArtifact()"),
            Script(f"window.FASTDPS_CSRF={csrf!r};"),
            Script(src="/static/chat.js?v=1"),
            cls=f"app-shell {'has-right' if right else ''}",
        ),
    )


def empty_artifact():
    return Div(Button("×", type="button", cls="artifact-close", onclick="toggleArtifact()"), P("RESULTS", cls="eyebrow"), H2("Your working panel"),
               P("Search results, drafts, evaluations, and confirmations appear here while you work.", cls="muted"), cls="artifact-empty")


def status_badge(value: str):
    return Span(value.replace("_", " ").title(), cls=f"status {value.replace('_', '-')}")


def stat(label: str, value) -> Div:
    return Div(Strong(str(value)), Span(label), cls="stat-card")


def chat_page(actor: Actor, sessions: list[dict], messages: list[dict], current_sid: str, stats: dict, csrf: str) -> Html:
    message_nodes = []
    for item in messages:
        message_nodes.append(Div(Span("You" if item["role"] == "user" else "FastDPS", cls="message-author"),
                                 P(item["content"], cls="message-copy"), cls=f"message {item['role']}"))
    if not message_nodes:
        message_nodes = [
            Div(P("PROCUREMENT COPILOT", cls="eyebrow"), H2("What would you like to move forward?"),
                P("Draft a dynamic system, inspect supplier admissions, prepare a call-off, or ask what needs attention.", cls="muted"),
                Div(
                    Button("Create a DPS for digital services", cls="suggestion", data_prompt="Create a DPS for digital services"),
                    Button("List DPS", cls="suggestion", data_prompt="List DPS"),
                    Button("Show supplier applications", cls="suggestion", data_prompt="Show supplier applications"),
                    Button("Show audit activity", cls="suggestion", data_prompt="Show audit activity"),
                    cls="suggestions",
                ), cls="chat-welcome")
        ]
    content = Div(
        Div(stat("Dynamic systems", stats["dps"]), stat("Open", stats["open_dps"]), stat("Pending admissions", stats["pending_applications"]), stat("Competitions", stats["competitions"]), cls="chat-stats"),
        Div(*message_nodes, id="messages", cls="messages"),
        Form(
            Input(type="hidden", name="sid", id="chat-sid", value=current_sid),
            Textarea(name="message", id="chat-input", rows="1", placeholder="Ask FastDPS or describe an action…", required=True),
            Button("Send", type="submit", cls="send-button"),
            id="chat-form", cls="chat-composer",
        ),
        cls="chat-column",
    )
    return shell(actor, "chat", content, "Workspace", sessions=sessions, csrf=csrf)


def page_intro(eyebrow: str, title: str, copy: str, action=None):
    return Div(Div(P(eyebrow, cls="eyebrow"), H2(title), P(copy, cls="muted")), action, cls="page-intro")


def dps_list_page(actor: Actor, records: list[dict], csrf: str):
    cards = [
        A(Div(status_badge(item["status"]), Small(item["reference"])), H3(item["title"]), P(item["description"] or "No description yet."),
          Div(Span(item["currency"]), Span(item["closes_at"] or "No closing date")), href=f"/dps/{item['id']}", cls="record-card")
        for item in records
    ]
    content = Div(page_intro("DYNAMIC PURCHASING SYSTEMS", "Open access, governed decisions", "Create systems that remain open to qualified suppliers throughout their duration.",
                             A("Create DPS", href="/dps/new", cls="button") if actor.can("dps.create") else None),
                  Div(*cards, cls="record-grid") if cards else empty_state("No systems yet", "Create the first dynamic purchasing system."), cls="page-scroll")
    return shell(actor, "dps", content, "Dynamic systems", csrf=csrf)


def dps_new_page(actor: Actor, csrf: str, error: str = ""):
    content = Div(page_intro("NEW SYSTEM", "Create a dynamic purchasing system", "Start with the commercial scope. Categories and qualification criteria come next."),
                  Div(error, cls="alert error") if error else None,
                  Form(Input(type="hidden", name="csrf", value=csrf), Label("Title", Input(name="title", required=True)),
                       Label("Reference", Input(name="reference", placeholder="Generated when left blank")),
                       Label("Description", Textarea(name="description", rows="5")),
                       Div(Label("Currency", Input(name="currency", value="EUR", maxlength="3")), Label("Estimated value", Input(name="estimated_value", inputmode="decimal")), cls="form-row"),
                       Div(Label("Opens at", Input(type="datetime-local", name="opens_at")), Label("Closes at", Input(type="datetime-local", name="closes_at")), cls="form-row"),
                       Button("Create draft", type="submit", cls="button"), action="/dps/new", method="post", cls="panel form-stack"), cls="page-scroll narrow")
    return shell(actor, "dps", content, "Create DPS", csrf=csrf)


def dps_detail_page(actor: Actor, item: dict, csrf: str):
    categories = [Div(Strong(row["code"]), H4(row["name"]), P(row["description"]), cls="list-row") for row in item["categories"]]
    criteria = [Div(H4(row["name"]), P(row["description"]), status_badge("required" if row["required"] else "optional"), cls="list-row") for row in item["criteria"]]
    transition = None
    if actor.can("dps.publish") and item["status"] == "draft":
        transition = Form(Input(type="hidden", name="csrf", value=csrf), Input(type="hidden", name="target", value="published"), Button("Publish system", cls="button"), action=f"/dps/{item['id']}/transition", method="post")
    content = Div(
        page_intro(item["reference"], item["title"], item["description"] or "No description yet.", Div(status_badge(item["status"]), transition, cls="inline-actions")),
        Div(stat("Estimated value", f"{item['currency']} {item['estimated_value'] or '—'}"), stat("Opens", item["opens_at"] or "Not set"), stat("Closes", item["closes_at"] or "Not set"), cls="stats-grid"),
        Div(
            Section(H3("Categories"), *categories, empty_state("No categories", "Add a category before publication.") if not categories else None,
                    Form(Input(type="hidden", name="csrf", value=csrf), Div(Label("CPV or category code", Input(name="code", required=True)), Label("Name", Input(name="name", required=True)), cls="form-row"),
                         Label("Description", Input(name="description")), Button("Add category", cls="button small"), action=f"/dps/{item['id']}/categories", method="post", cls="inline-form") if actor.can("dps.edit") else None,
                    cls="panel"),
            Section(H3("Qualification criteria"), *criteria, empty_state("No criteria", "Add objective admission requirements.") if not criteria else None,
                    Form(Input(type="hidden", name="csrf", value=csrf), Label("Criterion", Input(name="name", required=True)), Label("Description", Input(name="description")), Button("Add criterion", cls="button small"), action=f"/dps/{item['id']}/criteria", method="post", cls="inline-form") if actor.can("dps.edit") else None,
                    cls="panel"), cls="two-column"),
        A("Export OCDS JSON", href=f"/dps/{item['id']}/ocds", cls="quiet-link") if actor.can("ocds.export") else None,
        cls="page-scroll",
    )
    return shell(actor, "dps", content, item["title"], csrf=csrf)


def applications_page(actor: Actor, applications: list[dict], csrf: str):
    rows = []
    for item in applications:
        actions = None
        if actor.can("suppliers.admit") and item["status"] == "under_review":
            actions = Div(*[
                Form(Input(type="hidden", name="csrf", value=csrf), Input(type="hidden", name="target", value=target),
                     Button(label, cls=f"button small {'danger' if target == 'rejected' else ''}"), action=f"/applications/{item['id']}/transition", method="post")
                for target, label in (("admitted", "Admit"), ("rejected", "Reject"))
            ], cls="inline-actions")
        elif actor.can("suppliers.review") and item["status"] == "submitted":
            actions = Form(Input(type="hidden", name="csrf", value=csrf), Input(type="hidden", name="target", value="under_review"), Button("Start review", cls="button small"), action=f"/applications/{item['id']}/transition", method="post")
        rows.append(Div(Div(H3(item["supplier_name"]), P(f"{item['dps_reference']} · {item['dps_title']}", cls="muted")), Div(status_badge(item["status"]), actions, cls="row-actions"), cls="table-row"))
    content = Div(page_intro("SUPPLIER ADMISSION", "A continuously open qualification queue", "Review applications consistently and retain the reasons for each decision."), Div(*rows, cls="table-card") if rows else empty_state("No applications", "Applications to your published systems will appear here."), cls="page-scroll")
    return shell(actor, "suppliers", content, "Suppliers", csrf=csrf)


def competitions_page(actor: Actor, competitions: list[dict], dps_records: list[dict], csrf: str):
    rows = [A(Div(H3(item["title"]), P(f"{item['reference']} · {item['dps_title']}", cls="muted")), status_badge(item["status"]), href=f"/competitions/{item['id']}", cls="table-row") for item in competitions]
    form = None
    if actor.can("competitions.manage"):
        form = Form(Input(type="hidden", name="csrf", value=csrf), Label("Published DPS", Select(*[Option(d["title"], value=d["id"]) for d in dps_records if d["status"] == "published"], name="dps_id", required=True)),
                    Label("Competition title", Input(name="title", required=True)), Label("Submission deadline", Input(type="datetime-local", name="deadline")),
                    Button("Create call-off", cls="button"), action="/competitions", method="post", cls="panel form-stack compact")
    content = Div(page_intro("CALL-OFF COMPETITIONS", "Compete work among admitted suppliers", "Publishing a call-off automatically invites suppliers admitted to its parent system."), form, Div(*rows, cls="table-card") if rows else empty_state("No competitions", "Create a call-off under a published DPS."), cls="page-scroll")
    return shell(actor, "competitions", content, "Competitions", csrf=csrf)


def documents_page(actor: Actor, documents: list[dict], dps_records: list[dict], csrf: str):
    rows = [Div(Div(H3(item["title"]), P(f"{item['entity_type']} · version {item['current_version']}", cls="muted")), Span(item["updated_at"][:10]), cls="table-row") for item in documents]
    form = Form(Input(type="hidden", name="csrf", value=csrf), Label("DPS", Select(*[Option(d["title"], value=d["id"]) for d in dps_records], name="entity_id", required=True)),
                Label("Title", Input(name="title", required=True)), Label("File", Input(type="file", name="file", required=True)), Button("Upload document", cls="button"), action="/documents", method="post", enctype="multipart/form-data", cls="panel form-stack compact") if actor.can("documents.manage") else None
    content = Div(page_intro("DOCUMENTS", "Versioned procurement evidence", "Files are content-hashed and scoped to your organisation."), form, Div(*rows, cls="table-card") if rows else empty_state("No documents", "Upload a document to a dynamic system."), cls="page-scroll")
    return shell(actor, "documents", content, "Documents", csrf=csrf)


def roles_page(actor: Actor, roles: list[dict], permissions: list[dict], members: list[dict], invitations: list[dict], csrf: str, editing: dict | None = None, invite_link: str = ""):
    grouped = {}
    for permission in permissions:
        grouped.setdefault(permission["category"], []).append(permission)
    selected = set((editing or {}).get("permissions", []))
    permission_fields = []
    for category, items in grouped.items():
        permission_fields.append(Fieldset(Legend(category), *[
            Label(Input(type="checkbox", name="permissions", value=item["key"], checked=item["key"] in selected), Span(item["name"]), Small(item["description"]), cls="permission-option") for item in items
        ]))
    role_cards = [Div(Div(H3(role["name"]), P(role["description"], cls="muted")), Span(f"{len(role['permissions'])} rights"), A("Edit", href=f"/admin/roles?edit={role['id']}", cls="quiet-link"), cls="role-card") for role in roles]
    member_rows = []
    for member in members:
        role_chips = Div(*[
            Form(Input(type="hidden", name="csrf", value=csrf), Button(f"{role['name']} ×", cls="role-chip", title="Remove role"),
                 action=f"/admin/members/{member['id']}/roles/{role['id']}/remove", method="post") for role in member["roles"]
        ], cls="role-chips")
        assignment = Form(Input(type="hidden", name="csrf", value=csrf), Select(*[Option(role["name"], value=role["id"]) for role in roles], name="role_id"),
                          Button("Assign", cls="button small"), action=f"/admin/members/{member['id']}/roles", method="post", cls="assign-role")
        member_rows.append(Div(Div(Strong(member["name"]), Small(member["email"]), role_chips), assignment, cls="table-row"))
    invitation_rows = [Div(Div(Strong(item["email"]), Small(f"Invited by {item['invited_by_name']}")), status_badge(item["status"]), cls="table-row") for item in invitations]
    action = f"/admin/roles/{editing['id']}" if editing else "/admin/roles"
    form = Form(Input(type="hidden", name="csrf", value=csrf), Label("Role name", Input(name="name", required=True, value=(editing or {}).get("name", ""))),
                Label("Description", Input(name="description", value=(editing or {}).get("description", ""))), *permission_fields,
                Button("Update role" if editing else "Create role", cls="button"), action=action, method="post", cls="panel form-stack role-form")
    invite_form = Form(Input(type="hidden", name="csrf", value=csrf), Label("Email", Input(type="email", name="email", required=True)),
                       Label("Initial role", Select(*[Option(role["name"], value=role["id"]) for role in roles], name="role_id", required=True)),
                       Button("Create invitation", cls="button"), action="/admin/invitations", method="post", cls="form-stack compact")
    content = Div(page_intro("ACCESS CONTROL", "Roles belong to your organisation", "Rename roles and compose their rights from the audited permission catalogue."),
                  Div(Section(H3("Active roles"), *role_cards, cls="panel"), Section(H3("Role editor"), form, cls="panel"), cls="two-column roles-layout"),
                  Div(invite_link, cls="alert success") if invite_link else None,
                  Div(Section(H3("Members"), *member_rows, cls="panel"), Section(H3("Invite member"), invite_form, H3("Invitations"), *invitation_rows, cls="panel"), cls="two-column"), cls="page-scroll")
    return shell(actor, "roles", content, "Roles & access", csrf=csrf)


def invitation_page(invitation: dict | None, signed_in: bool, csrf: str = "", error: str = ""):
    if not invitation:
        title, copy = "Invitation unavailable", "This invitation does not exist or is no longer available."
        action = A("Return home", href="/", cls="button")
    else:
        title = f"Join {invitation['organisation_name']}"
        copy = f"You were invited as {', '.join(role['name'] for role in invitation['roles']) or 'a member'}."
        if signed_in:
            action = Form(Input(type="hidden", name="csrf", value=csrf), Button("Accept invitation", cls="button full"), method="post")
        else:
            action = A("Sign in to accept", href="/login", cls="button full")
    return Html(head("Invitation"), Body(Main(Div(logo(), H1(title), P(copy, cls="muted"), Div(error, cls="alert error") if error else None, action, cls="auth-card"), cls="auth-page")))


def imports_page(actor: Actor, jobs: list[dict], notices: list[dict], csrf: str):
    jobs_ui = [Div(Div(Strong(row["file_name"]), Small(row["source"])), Div(status_badge(row["status"]), Span(f"{row['imported_count']} releases")), cls="table-row") for row in jobs]
    notices_ui = [Div(Div(Strong(row["title"]), Small(row["buyer_name"] or row["ocid"])), Div(status_badge(row["stage"]), Span(row["deadline"] or "No deadline")), cls="table-row") for row in notices]
    form = Form(Input(type="hidden", name="csrf", value=csrf), Label("OCDS JSON or supported eForms XML", Input(type="file", name="file", accept=".json,.xml,application/json,text/xml", required=True)),
                Button("Import", cls="button"), action="/imports", method="post", enctype="multipart/form-data", cls="panel form-stack compact")
    content = Div(page_intro("OPEN CONTRACTING DATA", "Bring notices into one searchable model", "Import OCDS releases directly or install the optional converter for TED and Doffin eForms XML."), form,
                  Section(H3("Import jobs"), *jobs_ui, empty_state("No imports", "Upload an OCDS release package to begin.") if not jobs_ui else None, cls="panel"),
                  Section(H3("Notice index"), *notices_ui, cls="panel") if notices_ui else None, cls="page-scroll")
    return shell(actor, "imports", content, "Open data", csrf=csrf)


def audit_page(actor: Actor, events: list[dict], csrf: str):
    rows = [Div(Div(Strong(row["action"].replace(".", " · ")), Small(f"{row['entity_type']} · {row.get('actor_name') or 'System'}")), Span(row["created_at"][:19].replace("T", " ")), cls="table-row") for row in events]
    content = Div(page_intro("GOVERNANCE", "An append-only decision trail", "Every governed mutation records the actor, organisation, entity, and timestamp."), Div(*rows, cls="table-card"), cls="page-scroll")
    return shell(actor, "audit", content, "Audit trail", csrf=csrf)


def supplier_portal_page(actor: Actor, supplier: dict | None, systems: list[dict], applications: list[dict], invitations: list[dict], csrf: str):
    profile = Form(Input(type="hidden", name="csrf", value=csrf), Label("Supplier name", Input(name="name", required=True, value=(supplier or {}).get("name", ""))),
                   Label("Registration number", Input(name="registration_number", value=(supplier or {}).get("registration_number", ""))),
                   Label("Website", Input(type="url", name="website", value=(supplier or {}).get("website", ""))), Button("Save supplier profile", cls="button"), action="/supplier/profile", method="post", cls="panel form-stack compact")
    app_by_dps = {app["dps_id"]: app for app in applications}
    system_cards = []
    for item in systems:
        application = app_by_dps.get(item["id"])
        action = status_badge(application["status"]) if application else (
            Form(Input(type="hidden", name="csrf", value=csrf), Input(type="hidden", name="dps_id", value=item["id"]), Button("Start application", cls="button small"), action="/supplier/apply", method="post") if supplier else Span("Create a supplier profile first", cls="muted")
        )
        system_cards.append(Div(Div(Small(item["reference"]), H3(item["title"]), P(item["description"])), action, cls="record-card"))
    invitation_cards = []
    for item in invitations:
        if item.get("submission_status"):
            action = status_badge(item["submission_status"])
        else:
            action = Form(Input(type="hidden", name="csrf", value=csrf), Input(type="hidden", name="supplier_id", value=supplier["id"]),
                          Label("Bid value", Input(name="value_amount", inputmode="decimal", required=True)),
                          Label("Response summary", Textarea(name="response", rows="3", required=True)),
                          Button("Submit response", cls="button small"), action=f"/supplier/competitions/{item['id']}/submit", method="post", cls="inline-form")
        invitation_cards.append(Div(Div(Small(item["reference"]), H3(item["title"]), P(f"Deadline: {item['deadline'] or 'Not set'}")), action, cls="record-card"))
    content = Div(page_intro("SUPPLIER PORTAL", "Join open systems and compete for work", "Your supplier profile is separate from the buying organisation you may also belong to."),
                  Div(Section(H3("Supplier profile"), profile), Section(H3("Open systems"), *system_cards, empty_state("No open systems", "Published systems will appear here.") if not system_cards else None), cls="two-column"),
                  Section(H3("Invited competitions"), *invitation_cards, empty_state("No invitations", "Call-off invitations appear after admission.") if not invitation_cards else None, cls="panel supplier-invitations"), cls="page-scroll")
    return shell(actor, "supplier", content, "Supplier portal", csrf=csrf)


def competition_detail_page(actor: Actor, item: dict, csrf: str):
    criteria = [Div(Strong(row["name"]), Span(f"Weight {row['weight']}% · max {row['max_score']}"), cls="list-row") for row in item["criteria"]]
    submissions = []
    for row in item["submissions"]:
        score_forms = []
        if item["status"] == "evaluation" and actor.can("submissions.evaluate"):
            score_forms = [Form(Input(type="hidden", name="csrf", value=csrf), Input(type="hidden", name="submission_id", value=row["id"]), Input(type="hidden", name="criterion_id", value=criterion["id"]),
                                Label(criterion["name"], Input(name="score", type="number", min="0", max=criterion["max_score"], step="0.1", required=True)), Button("Save score", cls="button small"),
                                action=f"/competitions/{item['id']}/evaluate", method="post", cls="score-form") for criterion in item["criteria"]]
        award_form = Form(Input(type="hidden", name="csrf", value=csrf), Input(type="hidden", name="submission_id", value=row["id"]), Label("Rationale", Input(name="rationale", required=True)), Button("Create award recommendation", cls="button small"), action=f"/competitions/{item['id']}/awards", method="post", cls="inline-form") if item["status"] == "evaluation" and actor.can("awards.approve") and not item.get("award") else None
        submissions.append(Div(Div(Strong(row["supplier_name"]), Small(f"{row['currency']} {row['value_amount'] or '—'}")), status_badge(row["status"]), *score_forms, award_form, cls="submission-row"))
    next_target = {"draft": "published", "published": "closed", "closed": "evaluation"}.get(item["status"])
    action = Form(Input(type="hidden", name="csrf", value=csrf), Input(type="hidden", name="target", value=next_target), Button(f"Move to {next_target}", cls="button"), action=f"/competitions/{item['id']}/transition", method="post") if next_target and actor.can("competitions.manage") else None
    criterion_form = Form(Input(type="hidden", name="csrf", value=csrf), Div(Label("Criterion", Input(name="name", required=True)), Label("Weight %", Input(name="weight", value="100", inputmode="decimal", required=True)), cls="form-row"), Button("Add criterion", cls="button small"), action=f"/competitions/{item['id']}/criteria", method="post", cls="inline-form") if actor.can("competitions.manage") and item["status"] == "draft" else None
    conflict_form = Form(Input(type="hidden", name="csrf", value=csrf), Label("Conflict declaration", Input(name="declaration", value="I have reviewed my interests for this competition.", required=True)),
                         Label(Input(type="checkbox", name="has_conflict", value="1"), "I have a conflict"), Button("Record declaration", cls="button small"), action=f"/competitions/{item['id']}/conflict", method="post", cls="panel inline-form") if item["status"] == "evaluation" and actor.can("submissions.evaluate") else None
    award_actions = None
    if item.get("award") and actor.can("awards.approve"):
        award = item["award"]
        target = {"draft": "approved", "approved": "published"}.get(award["status"])
        award_actions = Div(H3("Award recommendation"), P(award["rationale"]), status_badge(award["status"]),
                            Form(Input(type="hidden", name="csrf", value=csrf), Input(type="hidden", name="target", value=target), Button(f"Move award to {target}", cls="button small"), action=f"/awards/{award['id']}/transition", method="post") if target else None, cls="panel")
    content = Div(page_intro(item["reference"], item["title"], item["description"] or "Call-off competition", Div(status_badge(item["status"]), action, cls="inline-actions")),
                  conflict_form,
                  Div(Section(H3("Evaluation criteria"), *criteria, criterion_form, cls="panel"), Section(H3("Submissions"), *submissions, empty_state("No submissions", "Invited supplier submissions appear here.") if not submissions else None, cls="panel"), cls="two-column"),
                  award_actions, cls="page-scroll")
    return shell(actor, "competitions", content, item["title"], csrf=csrf)


def empty_state(title: str, copy: str):
    return Div(H3(title), P(copy, cls="muted"), cls="empty-state")
