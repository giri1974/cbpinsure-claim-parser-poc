"""Configuration with a Local / Cloud database switch.

Mode selection (highest priority first):
  1. config.set_mode("local"|"cloud")      - used by the Streamlit sidebar switch and the CLI --db flag
  2. DB_MODE environment variable
  3. automatic: Windows -> local, anything else (e.g. Streamlit Cloud, Linux) -> cloud

Credentials are never stored in the repo:
  local : SQL_SERVER / SQL_USER / SQL_PASSWORD env vars, else ../Connection_String.txt (top block)
  cloud : Streamlit secrets [cloud], else CLOUD_SQL_* env vars, else ../Connection_String.txt ("Remote Database" block)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CONN_FILE = Path(os.getenv("CONN_FILE", ROOT.parent / "Connection_String.txt"))
DEFAULT_SAMPLES = Path(os.getenv(
    "SAMPLES_DIR", ROOT.parent / "CBPInsure-20261104T094959Z-1-001" / "CBPInsure"))
# POC/demo: only process this many files per case folder (0 = no limit)
MAX_FILES_PER_CASE = int(os.getenv("MAX_FILES_PER_CASE", "10"))
ODBC_DRIVER = os.getenv("ODBC_DRIVER", "ODBC Driver 17 for SQL Server")
LOCAL_DB_NAME = os.getenv("CLAIMS_DB_NAME", "CBPInsureClaims")

_MODE: str | None = None
_OCR_ENGINE: str | None = None


# ------------------------------------------------------------------ OCR engine
def set_engine(engine: str | None) -> None:
    global _OCR_ENGINE
    if engine not in (None, "auto", "tesseract", "rapidocr"):
        raise ValueError("engine must be auto|tesseract|rapidocr")
    _OCR_ENGINE = engine


def ocr_engine() -> str:
    # RapidOCR is the default: it scored better than Tesseract on the sample scans,
    # and the parsers are tuned to its output. Override with OCR_ENGINE / the UI switch.
    e = _OCR_ENGINE or os.getenv("OCR_ENGINE", "").strip().lower()
    return e if e in ("auto", "tesseract", "rapidocr") else "rapidocr"


# ------------------------------------------------------------------ mode
def set_mode(mode: str | None) -> None:
    global _MODE
    if mode not in (None, "local", "cloud", "postgres"):
        raise ValueError("mode must be 'local', 'cloud' or 'postgres'")
    _MODE = mode


def mode() -> str:
    m = _MODE or os.getenv("DB_MODE", "").strip().lower()
    if m in ("local", "cloud", "postgres"):
        return m
    if sys.platform == "win32":
        return "local"
    # Hosted (Streamlit Cloud / Render / Linux): prefer Postgres when it's configured, else SQL Server cloud
    return "postgres" if _postgres_cfg() else "cloud"


# ------------------------------------------------------------------ credential sources
def _read_file() -> str:
    return CONN_FILE.read_text(encoding="utf-8", errors="ignore") if CONN_FILE.exists() else ""


def _local_from_file() -> dict:
    txt = _read_file().split("Remote Database")[0]
    cfg = {}
    for key, name in (("server", "SERVER"), ("user", "USER ID"), ("password", "Password")):
        m = re.search(rf"^\s*{name}\s*:\s*(.+?)\s*$", txt, re.I | re.M)
        if m:
            cfg[key] = m.group(1)
    return cfg


def _cloud_from_file() -> dict:
    parts = _read_file().split("Remote Database")
    if len(parts) < 2:
        return {}
    txt = parts[1]
    cfg = {}
    cs = re.search(r"Server=([^;]+);\s*Database=([^;]+);\s*User Id=([^;]+)", txt, re.I)
    if cs:
        cfg.update(server=cs.group(1).strip(), database=cs.group(2).strip(), user=cs.group(3).strip())
    m = re.search(r"^\s*Pwd\s*:\s*(.+?)\s*$", txt, re.I | re.M)
    if m:
        cfg["password"] = m.group(1)
    m = re.search(r"^\s*Port\s*:\s*(\d+)", txt, re.I | re.M)
    cfg["port"] = int(m.group(1)) if m else 1433
    return cfg


def _cloud_from_secrets() -> dict:
    try:
        import streamlit as st
        from streamlit.runtime import exists
        if not exists():
            return {}
        sec = st.secrets.get("cloud")
        return dict(sec) if sec else {}
    except Exception:       # no secrets file / not running under streamlit
        return {}


def _cloud_from_env() -> dict:
    keys = {"server": "CLOUD_SQL_SERVER", "database": "CLOUD_SQL_DATABASE", "user": "CLOUD_SQL_USER",
            "password": "CLOUD_SQL_PASSWORD", "port": "CLOUD_SQL_PORT"}
    return {k: os.environ[v] for k, v in keys.items() if os.getenv(v)}


# ---- Postgres (Neon / Render) : used for the hosted Streamlit/Render deployment ----
def _parse_db_url(url: str) -> dict:
    """postgresql://user:pass@host:port/dbname?... -> settings dict."""
    import urllib.parse as up
    u = up.urlparse(url)
    return {"server": u.hostname or "", "port": u.port or 5432,
            "user": up.unquote(u.username or ""), "password": up.unquote(u.password or ""),
            "database": (u.path or "/").lstrip("/")}


def _postgres_cfg() -> dict:
    # 1) single DATABASE_URL env (Render sets this automatically when you link a DB)
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    cfg = _parse_db_url(url) if url else {}
    # 2) discrete PG* env vars
    env = {"server": os.getenv("PGHOST"), "port": os.getenv("PGPORT"), "user": os.getenv("PGUSER"),
           "password": os.getenv("PGPASSWORD"), "database": os.getenv("PGDATABASE")}
    cfg.update({k: v for k, v in env.items() if v})
    # 3) Streamlit secrets [postgres] (url=... or discrete keys)
    try:
        import streamlit as st
        from streamlit.runtime import exists
        if exists():
            sec = st.secrets.get("postgres")
            if sec:
                sec = dict(sec)
                if sec.get("url"):
                    cfg = {**cfg, **_parse_db_url(sec["url"])}
                cfg.update({k: v for k, v in sec.items() if k != "url" and v})
    except Exception:
        pass
    return cfg if cfg.get("server") and cfg.get("database") else {}


# ------------------------------------------------------------------ public API
def settings() -> dict:
    """Resolved connection settings for the active mode."""
    if mode() == "postgres":
        cfg = _postgres_cfg()
        cfg.setdefault("port", 5432)
        cfg["port"] = int(cfg.get("port") or 5432)
        cfg.setdefault("server", "")
        cfg.setdefault("database", "")
        cfg.setdefault("user", "")
        cfg.setdefault("password", "")
        cfg["mode"] = "postgres"
        cfg["driver"] = "psycopg"
        return cfg
    if mode() == "cloud":
        cfg = {"port": 1433, **_cloud_from_file(), **_cloud_from_env(), **_cloud_from_secrets()}
        cfg["port"] = int(cfg.get("port") or 1433)
        cfg["mode"] = "cloud"
        cfg["driver"] = "pymssql"           # pure FreeTDS: works on Linux / Streamlit Cloud, no ODBC install
        cfg.setdefault("server", "")
        cfg.setdefault("database", "")
        return cfg
    f = _local_from_file()
    return {
        "mode": "local", "driver": "pyodbc",
        "server": os.getenv("SQL_SERVER") or f.get("server", r"localhost\SQLEXPRESS"),
        "user": os.getenv("SQL_USER") or f.get("user", "sa"),
        "password": os.getenv("SQL_PASSWORD") or f.get("password", ""),
        "database": LOCAL_DB_NAME, "port": None,
    }


def database_name() -> str:
    return settings()["database"]


def server_label() -> str:
    s = settings()
    return f"{s['server']}" + (f":{s['port']}" if s.get("port") else "")


def cloud_configured() -> bool:
    prev = _MODE
    try:
        set_mode("cloud")
        s = settings()
        return bool(s["server"] and s.get("user") and s.get("password") and s["database"])
    finally:
        set_mode(prev)


def postgres_configured() -> bool:
    return bool(_postgres_cfg())


def odbc_conn_str(database: str | None) -> str:
    s = settings()
    parts = [f"DRIVER={{{ODBC_DRIVER}}}", f"SERVER={s['server']}", f"UID={s['user']}",
             f"PWD={{{s['password']}}}", "TrustServerCertificate=yes"]
    if database:
        parts.append(f"DATABASE={database}")
    return ";".join(parts)
