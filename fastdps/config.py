"""Environment-backed FastDPS configuration."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


SCHEMA_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")


def _csv(name: str) -> tuple[str, ...]:
    return tuple(part.strip().lower() for part in os.getenv(name, "").split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    root: Path
    secret: str
    port: int
    public_url: str
    environment: str
    data_dir: Path
    sqlite_path: Path
    database_url: str
    database_schema: str
    allow_test_auth: bool
    platform_admins: tuple[str, ...]
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    google_allowed_domains: tuple[str, ...]
    google_allowed_emails: tuple[str, ...]
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    ocid_prefix: str

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(__file__).resolve().parent.parent
        data_dir = Path(os.getenv("FASTDPS_DATA_DIR", str(root / "data")))
        schema = os.getenv("DB_SCHEMA", "fast_dps").strip() or "fast_dps"
        if not SCHEMA_PATTERN.fullmatch(schema):
            raise ValueError("DB_SCHEMA contains an unsafe PostgreSQL identifier")
        return cls(
            root=root,
            secret=os.getenv("FASTDPS_SECRET", "fastdps-local-change-me"),
            port=int(os.getenv("FASTDPS_PORT", "5024")),
            public_url=os.getenv("FASTDPS_PUBLIC_URL", "http://localhost:5024").rstrip("/"),
            environment=os.getenv("FASTDPS_ENV_LABEL", "Local"),
            data_dir=data_dir,
            sqlite_path=Path(os.getenv("FASTDPS_DB", str(data_dir / "fastdps.sqlite"))),
            database_url=(os.getenv("DB_URL", "").strip() or os.getenv("DATABASE_URL_PROD", "").strip()),
            database_schema=schema,
            allow_test_auth=os.getenv("FASTDPS_ALLOW_TEST_AUTH", "false").lower() == "true",
            platform_admins=_csv("FASTDPS_PLATFORM_ADMINS"),
            google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
            google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
            google_redirect_uri=os.getenv("GOOGLE_REDIRECT_URI", "").strip(),
            google_allowed_domains=_csv("GOOGLE_ALLOWED_DOMAINS"),
            google_allowed_emails=_csv("GOOGLE_ALLOWED_EMAILS"),
            llm_api_key=(os.getenv("LLM_API_KEY", "").strip() or os.getenv("XAI_API_KEY", "").strip()),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            llm_model=os.getenv("LLM_MODEL", "").strip(),
            ocid_prefix=os.getenv("FASTDPS_OCID_PREFIX", "ocds-fastdps").strip(),
        )


settings = Settings.from_env()
