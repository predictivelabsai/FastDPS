# FastDPS

[![Production](https://img.shields.io/badge/production-dps.fastsme.com-0f766e)](https://dps.fastsme.com)

FastDPS is an open-source, chat-first dynamic purchasing system. It gives
buying organisations a governed workspace for continuously admitting qualified
suppliers, running call-off competitions, evaluating responses, approving
awards, and publishing portable Open Contracting Data Standard (OCDS) records.

The default local deployment needs no external services: it uses SQLite,
deterministic assistant commands, synthetic demonstration data, and local
authentication. PostgreSQL, Google OpenID Connect, an OpenAI-compatible model,
and TED/Doffin eForms conversion are optional.

[![FastDPS product walkthrough](docs/demo/fastdps-walkthrough.gif)](https://dps.fastsme.com)

## What is implemented

- Multi-organisation identity and membership with local login and optional
  Google OpenID Connect.
- Dynamic organisation roles: administrators can create, rename, archive, and
  compose roles from an audited permission catalogue.
- Protected owner role, grant-boundary enforcement, tenant isolation, CSRF,
  expiring invitations, and append-only audit events.
- Dynamic purchasing systems, categories, qualification criteria, publication,
  closure, and archiving.
- Supplier profiles, continuously open admission applications, clarification,
  admission, rejection, suspension, and withdrawal states.
- Call-off competitions, automatic invitation of admitted suppliers, supplier
  submissions, conflict declarations, weighted evaluation, awards, and
  contracts.
- Versioned and content-hashed procurement documents.
- Three-pane conversational workspace with typed server-sent events, structured
  result artifacts, and confirm-before-write tools.
- OCDS release/package import, searchable notice projections, DPS export, and
  an optional pinned TED/Doffin XML conversion adapter.
- FastAPI integration surface with generated OpenAPI documentation.
- SQLite migrations and PostgreSQL connection/migration scaffolding.

AI is intentionally separated from procurement authority. It can explain,
draft, search, and propose actions; it cannot publish, admit, reject, award, or
change access without an authorised user and an explicit confirmation.

## Run locally

Python 3.13 is required.

```bash
python3.13 -m venv .venv
.venv/bin/python -m ensurepip --upgrade
.venv/bin/python -m pip install -e '.[dev]'
cp .env.sample .env
.venv/bin/python seed.py
.venv/bin/python web_app.py
```

Open `http://localhost:5024`. With `FASTDPS_ALLOW_TEST_AUTH=true`, the local
demonstration workspace is available at `/auth/test`. It has no committed
password and the route is disabled unless explicitly enabled.

Run verification with:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m compileall -q fastdps web_app.py seed.py
```

## Chat commands

Natural language and explicit commands use the same guarded tool layer:

```text
Create a DPS for digital services
List DPS
Publish DPS <id>
Add category <dps-id> | <code> | <name>
Add qualification criterion <dps-id> | <name>
Create competition <dps-id> | Laptop call-off
Add evaluation criterion <competition-id> | Quality | 60
Publish competition <id>
Show supplier applications
Admit application <id>
Create award <competition-id> | <submission-id> | rationale
Approve award <id>
Create contract <award-id> | CON-001
Search notices cloud hosting
Show audit activity
```

Read operations run immediately. Every write produces a preview with an
expiring confirmation. FastDPS checks the user's current permission again when
the confirmation is submitted, making revoked rights effective immediately.

## Database

SQLite is used when `DB_URL` is empty:

```env
FASTDPS_DB=./data/fastdps.sqlite
```

For PostgreSQL:

```env
DB_URL=postgresql://user:password@database:5432/fastdps
DB_SCHEMA=fast_dps
```

The process-wide PostgreSQL pool is bounded by `DB_POOL_MIN_SIZE` and
`DB_POOL_MAX_SIZE`. Baseline migrations use a portable SQL subset and run in
the configured schema. Set `FASTDPS_TEST_POSTGRES_URL` to opt into
deployment-specific parity tests when credentials become available; the test
uses and removes its own uniquely named schema.

## Authentication

Local accounts are available without an identity provider. Google sign-in uses
the standard endpoints `/auth/google` and `/auth/google/callback`, requests only
`openid email profile`, validates state and the returned verified email, and
supports allowlists through `GOOGLE_ALLOWED_DOMAINS` and
`GOOGLE_ALLOWED_EMAILS`.

Never commit `.env`, OAuth secrets, uploaded documents, or database files.

## OCDS and eForms

OCDS JSON import and export are included in the normal installation. Optional
TED/Doffin XML conversion is pinned to a reviewed upstream commit:

```bash
.venv/bin/python -m pip install -e '.[ocds-converter]'
```

The adapter keeps the converter's tracking database isolated per job, then
imports generated releases through FastDPS's idempotent OCDS ingestion layer.
See [third-party notices](THIRD_PARTY_NOTICES.md).

## API and operations

- Workspace: `/app`
- Health: `/healthz`
- Production health: `https://dps.fastsme.com/healthz`
- API documentation: `/api/v1/docs`
- OpenAPI schema: `/api/v1/openapi.json`

The Docker image exposes port `5024`. See [architecture](docs/architecture.md),
[threat model](docs/threat_model.md), and the
[product roadmap](docs/product_roadmap.doc).

Production deployment is managed by the sibling FastDevOps control plane:

```bash
python scripts/coolify.py status
python scripts/coolify.py env --sync --yes
python scripts/coolify.py deploy --yes
```

The canonical deployment is `https://dps.fastsme.com`; pushes to `main` are
configured to trigger a Coolify rebuild after repository checks pass.

FastDPS is released under the MIT License.
