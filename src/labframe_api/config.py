"""Configuration helpers for the LabFrame API service."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def resolve_db_path() -> Path:
    """Return the SQLite database path used by the API service."""
    env_value = os.getenv("LABFRAME_DB_PATH")
    if env_value:
        return Path(env_value).expanduser().resolve()

    project_root = Path(__file__).resolve().parents[3]
    return project_root / "db" / "database.sqlite"

