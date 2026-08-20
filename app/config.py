"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Settings:
    app_name: str = "CloudOpsAI"
    secret_key: str = os.getenv(
        "CLOUDOPSAI_SECRET_KEY",
        "dev-only-secret-change-before-production",
    )
    database_url: str = os.getenv(
        "CLOUDOPSAI_DATABASE_URL",
        f"sqlite:///{DATA_DIR / 'cloudopsai.db'}",
    )
    debug: bool = os.getenv("CLOUDOPSAI_DEBUG", "true").lower() == "true"


settings = Settings()
