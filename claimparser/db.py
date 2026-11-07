"""SQL Server (LocalDB) schema + persistence. Extends the schema from the
reference app.py with the full 19-field import list from the requirements doc."""
from __future__ import annotations

import json
import re
from contextlib import contextmanager

from . import config

SCHEMA = [
    """IF OBJECT_ID('dbo.policies') IS NULL CREATE TABLE dbo.policies (
        policy_id NVARCHAR(100) NOT NULL PRIMARY KEY,
        policyholder NVARCHAR(300) NULL,
        effective_date DATE NULL,
        term_end_date DATE NULL,
        benefit_period_weeks INT NULL DEFAULT 52,
        benefit_maximum DECIMAL(12,2) NULL,
        deductible DECIMAL(12,2) NULL,
        source_file NVARCHAR(500) NULL)""",
    """IF OBJECT_ID('dbo.members') IS NULL CREATE TABLE dbo.members (
        member_id NVARCHAR(100) NOT NULL PRIMARY KEY,
        member_name NVARCHAR(300) NULL)""",
    """IF OBJECT_ID('dbo.claimants') IS NULL CREATE TABLE dbo.claimants (
        claimant_id NVARCHAR(100) NOT NULL PRIMARY KEY,
        member_id NVARCHAR(100) NULL REFERENCES dbo.members(member_id),
        claimant_name NVARCHAR(300) NULL)""",
    """IF OBJECT_ID('dbo.claims') IS NULL CREATE TABLE dbo.claims (
        claim_number NVARCHAR(100) NOT NULL PRIMARY KEY,
        case_name NVARCHAR(300) NULL,
        policy_id NVARCHAR(100) NULL REFERENCES dbo.policies(policy_id),
        member_id NVARCHAR(100) NULL,
        member_name NVARCHAR(300) NULL,
        claimant_id NVARCHAR(100) NULL REFERENCES dbo.claimants(claimant_id),
        claimant_name NVARCHAR(300) NULL,
        date_of_loss DATE NULL,
        received_date DATE NULL,
        date_of_service_from DATE NULL,
        date_of_service_thru DATE NULL,
        diagnosis_code NVARCHAR(50) NULL,
        diagnosis_desc NVARCHAR(500) NULL,
        activity_code NVARCHAR(20) NULL,
        provider_tin NVARCHAR(50) NULL,
        provider_name NVARCHAR(300) NULL,
        provider_address NVARCHAR(500) NULL,
        patient_account_no NVARCHAR(100) NULL,
        total_charges DECIMAL(12,2) NULL,
        total_cob_allowable DECIMAL(12,2) NULL,
        total_cob_paid DECIMAL(12,2) NULL,
        total_primary_paid DECIMAL(12,2) NULL,
        deductible_amount DECIMAL(12,2) NULL,
        copay_amount DECIMAL(12,2) NULL,
        coinsurance_amount DECIMAL(12,2) NULL,
        net_payable DECIMAL(12,2) NULL,
        other_insurance NVARCHAR(200) NULL,
        needs_review BIT NOT NULL DEFAULT 1,
        review_notes NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME())""",
    """IF OBJECT_ID('dbo.claim_line_items') IS NULL CREATE TABLE dbo.claim_line_items (
        line_id INT IDENTITY(1,1) PRIMARY KEY,
        claim_number NVARCHAR(100) NOT NULL REFERENCES dbo.claims(claim_number),
        bill_file NVARCHAR(300) NULL,
        line_no INT NULL,
        dos_from DATE NULL,
        dos_thru DATE NULL,
        cpt_code NVARCHAR(30) NULL,
        procedure_desc NVARCHAR(300) NULL,
        provider_tin NVARCHAR(50) NULL,
        provider_name NVARCHAR(300) NULL,
        charge_amount DECIMAL(12,2) NULL,
        allowed_amount DECIMAL(12,2) NULL,
        paid_amount DECIMAL(12,2) NULL)""",
    """IF OBJECT_ID('dbo.source_documents') IS NULL CREATE TABLE dbo.source_documents (
        doc_id INT IDENTITY(1,1) PRIMARY KEY,
        case_name NVARCHAR(300) NULL,
        claim_number NVARCHAR(100) NULL,
        file_name NVARCHAR(300) NULL,
        file_path NVARCHAR(900) NOT NULL UNIQUE,
        doc_types NVARCHAR(200) NULL,
        page_count INT NULL,
        extract_method NVARCHAR(30) NULL,
        parsed_json NVARCHAR(MAX) NULL,
        raw_text NVARCHAR(MAX) NULL,
        processed_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME())""",
    """IF OBJECT_ID('dbo.document_pages') IS NULL CREATE TABLE dbo.document_pages (
        page_id INT IDENTITY(1,1) PRIMARY KEY,
        doc_id INT NOT NULL REFERENCES dbo.source_documents(doc_id),
        page_no INT NOT NULL,
        page_type NVARCHAR(30) NULL,
        page_text NVARCHAR(MAX) NULL)""",
    """IF OBJECT_ID('dbo.accumulator_lines') IS NULL CREATE TABLE dbo.accumulator_lines (
        id INT IDENTITY(1,1) PRIMARY KEY,
        case_name NVARCHAR(300) NULL,
        claim_no NVARCHAR(100) NULL,
        line_number INT NULL,
        claimant_id NVARCHAR(100) NULL,
        claimant_name NVARCHAR(300) NULL,
        loss_activity NVARCHAR(20) NULL,
        loss_activity_desc NVARCHAR(200) NULL,
        diagnosis_code NVARCHAR(50) NULL,
        diagnosis_desc NVARCHAR(500) NULL,
        procedure_code NVARCHAR(30) NULL,
        procedure_desc NVARCHAR(300) NULL,
        provider_id NVARCHAR(50) NULL,
        provider_name NVARCHAR(300) NULL,
        incurred_from DATE NULL,
        incurred_to DATE NULL,
        received_date DATE NULL,
        total_charges DECIMAL(12,2) NULL,
        allowed_amount DECIMAL(12,2) NULL,
        deductible DECIMAL(12,2) NULL,
        copay DECIMAL(12,2) NULL,
        amount_paid DECIMAL(12,2) NULL,
        remark_code NVARCHAR(20) NULL,
        policy_effective_dt NVARCHAR(20) NULL,
        source_file NVARCHAR(500) NULL)""",
]


class _Conn:
    """Uniform wrapper so the rest of the code works with pyodbc (local) and pymssql (cloud).
    SQL is written with '?' placeholders; they are converted to %s for pymssql."""

    def __init__(self, raw, qmark: bool):
        self.raw, self.qmark = raw, qmark

    def execute(self, sql: str, *params):
        if len(params) == 1 and isinstance(params[0], (list, tuple)):
            params = tuple(params[0])
        cur = self.raw.cursor()
        if not self.qmark:
            sql = sql.replace("?", "%s")
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        return cur

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()


def _open(database: str | None, autocommit: bool = False) -> _Conn:
    s = config.settings()
    if s["driver"] == "psycopg":
        import psycopg
        raw = psycopg.connect(host=s["server"], port=s["port"], user=s["user"], password=s["password"],
                              dbname=database or s["database"], sslmode="require",
                              autocommit=autocommit, connect_timeout=20)
        return _Conn(raw, qmark=False)
    if s["driver"] == "pymssql":
        import pymssql
        raw = pymssql.connect(server=s["server"], port=str(s["port"]), user=s["user"], password=s["password"],
                              database=database or s["database"], login_timeout=15, timeout=60,
                              autocommit=autocommit, charset="UTF-8")
        return _Conn(raw, qmark=False)
    import pyodbc
    return _Conn(pyodbc.connect(config.odbc_conn_str(database), autocommit=autocommit, timeout=10), qmark=True)


# ---- Postgres schema (dbo.* so the rest of the code's "dbo.table" SQL works unchanged) ----
def _pg_schema() -> list[str]:
    """Translate the SQL Server SCHEMA DDL to Postgres. Mechanical type/syntax mapping."""
    out = ["CREATE SCHEMA IF NOT EXISTS dbo"]
    for ddl in SCHEMA:
        d = re.sub(r"IF OBJECT_ID\('dbo\.(\w+)'\) IS NULL\s+CREATE TABLE dbo\.\1",
                   r"CREATE TABLE IF NOT EXISTS dbo.\1", ddl)
        d = re.sub(r"INT IDENTITY\(1,1\)\s+PRIMARY KEY", "SERIAL PRIMARY KEY", d, flags=re.I)
        d = re.sub(r"NVARCHAR\(MAX\)", "TEXT", d, flags=re.I)
        d = re.sub(r"N?VARCHAR\(\d+\)", "TEXT", d, flags=re.I)
        d = re.sub(r"DATETIME2", "TIMESTAMPTZ", d, flags=re.I)
        d = re.sub(r"DECIMAL\(\d+,\s*\d+\)", "NUMERIC(14,2)", d, flags=re.I)
        d = re.sub(r"\bBIT\b", "BOOLEAN", d, flags=re.I)
        d = re.sub(r"SYSUTCDATETIME\(\)", "now()", d, flags=re.I)
        d = re.sub(r"DEFAULT 1\b", "DEFAULT TRUE", d)   # needs_review default
        out.append(d)
    return out


def ensure_database() -> None:
    """Local: create the database if missing. Cloud/Postgres: the hosted database already exists."""
    if config.mode() in ("cloud", "postgres"):
        return
    name = config.database_name()
    cn = _open("master", autocommit=True)
    try:
        cn.execute(f"IF DB_ID('{name}') IS NULL CREATE DATABASE [{name}]")
    finally:
        cn.close()


def test_connection() -> tuple[bool, str]:
    """Used by the UI / CLI to show a clear message instead of a stack trace."""
    try:
        ensure_database()
        with connect() as cn:
            cn.execute("SELECT 1").fetchone()
        return True, f"Connected to {config.database_name()} on {config.server_label()} ({config.mode()})"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:400]}"


@contextmanager
def connect():
    cn = _open(config.database_name())
    try:
        yield cn
        cn.commit()
    except Exception:
        cn.rollback()
        raise
    finally:
        cn.close()


def init_db() -> None:
    ensure_database()
    ddls = _pg_schema() if config.mode() == "postgres" else SCHEMA
    with connect() as cn:
        for ddl in ddls:
            cn.execute(ddl)


def reset_data() -> None:
    """Delete all rows (keeps the schema). Child tables first."""
    with connect() as cn:
        for t in ("document_pages", "claim_line_items", "claims", "claimants", "members", "policies",
                  "source_documents", "accumulator_lines"):
            cn.execute(f"DELETE FROM dbo.{t}")


# ---------------------------------------------------------------- upserts
def _upsert(cn, table: str, key: str, row: dict) -> None:
    cols = list(row)
    sets = ", ".join(f"{c}=?" for c in cols if c != key)
    vals = [row[c] for c in cols if c != key] + [row[key]]
    cur = cn.execute(f"UPDATE dbo.{table} SET {sets} WHERE {key}=?", vals) if sets else None
    if cur is None or cur.rowcount == 0:
        cn.execute(f"INSERT INTO dbo.{table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                   [row[c] for c in cols])


def save_case(case: dict) -> None:
    """Persist one assembled case: policy, member, claimant, claims, lines, docs."""
    with connect() as cn:
        if case.get("policy"):
            _upsert(cn, "policies", "policy_id", case["policy"])
        if case.get("member"):
            _upsert(cn, "members", "member_id", case["member"])
        if case.get("claimant"):
            _upsert(cn, "claimants", "claimant_id", case["claimant"])
        for claim in case["claims"]:
            _upsert(cn, "claims", "claim_number", claim["row"])
            cn.execute("DELETE FROM dbo.claim_line_items WHERE claim_number=?", claim["row"]["claim_number"])
            for ln in claim["lines"]:
                cols = list(ln)
                cn.execute(f"INSERT INTO dbo.claim_line_items ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                           [ln[c] for c in cols])
        for d in case["documents"]:
            d = dict(d)
            pages = d.pop("_pages", [])
            _upsert(cn, "source_documents", "file_path", d)
            doc_id = cn.execute("SELECT doc_id FROM dbo.source_documents WHERE file_path=?",
                                d["file_path"]).fetchone()[0]
            cn.execute("DELETE FROM dbo.document_pages WHERE doc_id=?", doc_id)
            for no, kind, text in pages:
                cn.execute("INSERT INTO dbo.document_pages (doc_id, page_no, page_type, page_text) VALUES (?,?,?,?)",
                           doc_id, no, kind, text)
        if case.get("accumulator"):
            cn.execute("DELETE FROM dbo.accumulator_lines WHERE case_name=?", case["case_name"])
            for a in case["accumulator"]:
                cols = list(a)
                cn.execute(f"INSERT INTO dbo.accumulator_lines ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                           [a[c] for c in cols])


def bool_true(col: str) -> str:
    """Dialect-safe 'this BIT/BOOLEAN column is true' predicate.
    SQL Server has no TRUE literal and no bool type; Postgres rejects `= 1` on boolean."""
    return col if config.settings()["driver"] == "psycopg" else f"{col} = 1"


def query_df(sql: str, params=()):
    import pandas as pd
    with connect() as cn:
        cur = cn.execute(sql, *([list(params)] if params else []))
        cols = [c[0] for c in cur.description]
        rows = [tuple(r) for r in cur.fetchall()]
    return pd.DataFrame.from_records(rows, columns=cols, coerce_float=True)


def update_claim_fields(claim_number: str, fields: dict) -> None:
    allowed = {"activity_code", "date_of_loss", "diagnosis_code", "diagnosis_desc", "provider_tin",
               "provider_name", "provider_address", "needs_review", "review_notes",
               "date_of_service_from", "date_of_service_thru", "total_charges",
               "total_cob_allowable", "total_primary_paid", "net_payable"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if "needs_review" in sets and sets["needs_review"] is not None:
        sets["needs_review"] = bool(sets["needs_review"])   # BIT/BOOLEAN safe across drivers
    if not sets:
        return
    with connect() as cn:
        cn.execute(f"UPDATE dbo.claims SET {', '.join(k + '=?' for k in sets)} WHERE claim_number=?",
                   list(sets.values()) + [claim_number])
