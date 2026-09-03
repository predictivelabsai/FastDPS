# PostgreSQL migrations

FastDPS deliberately keeps its baseline DDL in the portable `migrations/sqlite`
directory. The PostgreSQL migration runner executes those numbered files inside
the configured `DB_SCHEMA`; PostgreSQL-only follow-up migrations can be added to
this directory when production requirements need native indexes or data types.

Set `DB_URL` and `DB_SCHEMA` to enable PostgreSQL. CI can opt into parity tests
with `TEST_POSTGRES_URL`.
