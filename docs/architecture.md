# FastDPS architecture

## System shape

FastDPS is a modular monolith. FastHTML renders the public site and workspace,
HTMX-compatible forms provide resilient browser interactions, vanilla
JavaScript consumes the assistant's typed event stream, and FastAPI exposes a
versioned integration surface within the same process.

```text
FastHTML workspace ─┐
                    ├─ application services ─ repositories/transactions ─ SQLite
FastAPI /api/v1 ────┘                                           └─────── PostgreSQL
          │
          └─ chat router ─ guarded tools ─ confirmation ─ same services

OCDS JSON ─ importer ─ canonical release store ─ searchable projection
eForms XML ─ optional pinned converter ──────────┘
```

## Boundaries

- `web_app.py` wires browser routes, sessions, CSRF, static files, and the
  mounted API.
- `fastdps/api.py` contains typed integration contracts.
- `fastdps/services/` owns workflows and transactions.
- `fastdps/rbac/` owns the permission catalogue and dynamic role composition.
- `fastdps/domain/` owns lifecycle transition invariants.
- `fastdps/database.py` supplies the shared transaction/query adapter,
  migrations, and bounded PostgreSQL pool.
- `fastdps/web/` contains server-rendered components only.
- `migrations/` is the authoritative schema history.

Routes never infer authority from a role name. They obtain an `Actor` for the
current user and organisation, then require a permission key. Services repeat
checks at the mutation boundary. Business queries include the organisation
identifier unless the data is intentionally global, such as published systems
visible in the supplier portal.

## Chat safety model

Read tools return structured artifacts immediately. Write tools create a
`chat_pending_actions` record containing the organisation, requesting user,
required permission, payload, and expiry. Confirmation atomically claims the
pending action, rechecks current permission, calls the same domain service used
by forms and the API, and records the outcome in the audit trail. Failed
execution releases the claim for a safe retry.

The optional model provider receives an explanatory prompt only. The local
router remains the authority for tool selection and no provider response can
directly execute code or SQL.

## Storage portability

Authoritative money, weights, and scores are stored as decimal strings. UUIDs
and ISO-8601 timestamps avoid engine-specific identity and time behavior. The
baseline DDL uses a common SQLite/PostgreSQL subset. PostgreSQL runs migrations
inside the validated `DB_SCHEMA` and uses a process-wide bounded pool.

OCDS releases are retained as complete canonical JSON alongside a denormalized
notice index. Import idempotency uses the organisation, OCID, release ID, and a
canonical checksum. Input-file checksums make repeated uploads safe.

## Deployment

The application is stateless apart from the configured database and
`FASTDPS_DATA_DIR`. Production deployments must provide a stable session secret,
persistent encrypted storage, TLS at the edge, backups, and malware scanning
for uploaded evidence.
