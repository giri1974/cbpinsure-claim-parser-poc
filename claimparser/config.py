"""Configuration. SQL Server settings come from env vars / .env, else are read
from the Connection_String.txt that sits in the parent folder (so the password
is never copied into the project)."""
from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB_NAME = os.getenv("CLAIMS_DB_NAME", "CBPInsureClaims")
CONN_FILE = Path(os.getenv("CONN_FILE", ROOT.parent / "Connection_String.txt"))
DEFAULT_SAMPLES = Path(os.getenv(
    "SAMPLES_DIR", ROOT.parent / "CBPInsure-20261104T094959Z-1-001" / "CBPInsure"))
# POC/demo: only process this many files per case folder (0 = no limit)
MAX_FILES_PER_CASE = int(os.getenv("MAX_FILES_PER_CASE", "10"))
ODBC_DRIVER = os.getenv("ODBC_DRIVER", "ODBC Driver 17 for SQL Server")


def _from_file() -> dict:
    cfg = {}
    if CONN_FILE.exists():
        txt = CONN_FILE.read_text(encoding="utf-8", errors="ignore")
        for key, name in (("server", "SERVER"), ("user", "USER ID"), ("password", "Password")):
            m = re.search(rf"^\s*{name}\s*:\s*(.+?)\s*$", txt, re.I | re.M)
            if m:
                cfg[key] = m.group(1)
    return cfg


def sql_settings() -> dict:
    f = _from_file()
    return {
        "server": os.getenv("SQL_SERVER") or f.get("server", r"localhost\SQLEXPRESS"),
        "user": os.getenv("SQL_USER") or f.get("user", "sa"),
        "password": os.getenv("SQL_PASSWORD") or f.get("password", ""),
    }


def conn_str(database: str | None) -> str:
    s = sql_settings()
    parts = [f"DRIVER={{{ODBC_DRIVER}}}", f"SERVER={s['server']}",
             f"UID={s['user']}", f"PWD={{{s['password']}}}",
             "TrustServerCertificate=yes"]
    if database:
        parts.append(f"DATABASE={database}")
    return ";".join(parts)
