# FastDPS repository guidelines

FastDPS is a Python 3.13 FastHTML application with a same-process FastAPI
integration surface. Keep browser routes thin, procurement decisions in
services, permission checks server-side, and SQL inside the portable database
and service boundary.

- All business records must be scoped to an organisation unless explicitly
  global supplier or platform data.
- Consequential chat actions must remain previewed, confirmed, permission
  checked at confirmation time, and idempotent.
- AI may explain, search, compare, and draft. It may never approve, publish,
  admit, reject, award, or alter permissions on its own authority.
- Role names and role-permission assignments are data. Permission keys are a
  reviewed code catalogue.
- Use `Decimal`-compatible text values for money and evaluation weights. Never
  use binary floating-point values for authoritative calculations.
- Use additive numbered migrations and deterministic synthetic fixtures.
- Keep SQLite working without external services. PostgreSQL tests are explicit
  opt-ins through `FASTDPS_TEST_POSTGRES_URL`.
- Never commit `.env`, credentials, real procurement data, uploaded evidence,
  database files, browser state, or generated local artifacts.

Run before handing work off:

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/python -m compileall -q fastdps web_app.py seed.py
git diff --check
```

Keep `docs/product_roadmap.doc` synchronized with delivered scope and deferred
follow-up work.
