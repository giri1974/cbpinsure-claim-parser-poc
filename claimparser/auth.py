"""Minimal username/password login with two roles for the POC.

Roles:
  admin - full control (including delete/clear-data operations)
  user  - everything except delete operations

Credentials resolution (first found wins), so it works local and on cloud:
  1. Streamlit secrets [auth] table:  admin_password / user_password (and optional
     admin_user / user_user to rename the logins)
  2. env vars APP_ADMIN_PASSWORD / APP_USER_PASSWORD (+ APP_ADMIN_USER / APP_USER_USER)
  3. dev fallback (local only): admin/admin123 and user/user123

Passwords are compared against a SHA-256 hash with a constant-time check. Nothing
is stored in the repo; set real passwords via secrets/env for any shared deployment.
"""
from __future__ import annotations

import hashlib
import hmac
import os

import streamlit as st


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _secret(key: str):
    try:
        auth = st.secrets.get("auth")
        if auth and key in auth:
            return auth[key]
    except Exception:
        pass
    return None


def _creds() -> dict[str, dict]:
    """Return {username: {"password_hash":..., "role":...}} for admin + user."""
    admin_user = _secret("admin_user") or os.getenv("APP_ADMIN_USER") or "admin"
    user_user = _secret("user_user") or os.getenv("APP_USER_USER") or "user"
    admin_pw = _secret("admin_password") or os.getenv("APP_ADMIN_PASSWORD") or "admin123"
    user_pw = _secret("user_password") or os.getenv("APP_USER_PASSWORD") or "user123"
    return {
        admin_user: {"password_hash": _sha(str(admin_pw)), "role": "admin"},
        user_user: {"password_hash": _sha(str(user_pw)), "role": "user"},
    }


def current_user() -> dict | None:
    return st.session_state.get("auth_user")


def is_admin() -> bool:
    u = current_user()
    return bool(u and u.get("role") == "admin")


def can_delete() -> bool:
    """Only admins may perform delete / clear-data operations."""
    return is_admin()


def logout() -> None:
    st.session_state.pop("auth_user", None)


def _login_form() -> None:
    import base64
    from pathlib import Path
    logo = Path(__file__).resolve().parent.parent / "CBInsureLogo.png"
    st.markdown("""
    <style>
      [data-testid="stAppViewContainer"] { background:#F5F7FA; }
      .cbp-login { max-width:380px; margin:6vh auto 0; background:#fff; border:1px solid #E6EAF0;
        border-radius:14px; padding:28px 30px; box-shadow:0 2px 10px rgba(16,24,40,.06); }
    </style>""", unsafe_allow_html=True)
    c = st.columns([1, 2, 1])[1]
    with c:
        if logo.exists():
            st.image(str(logo), width=180)
        st.markdown("### Claims Intake & Document Extraction")
        st.caption("Sign in to continue")
        with st.form("login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            ok = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if ok:
            creds = _creds()
            rec = creds.get(username.strip())
            if rec and hmac.compare_digest(rec["password_hash"], _sha(password)):
                st.session_state["auth_user"] = {"username": username.strip(), "role": rec["role"]}
                st.rerun()
            else:
                st.error("Invalid username or password.")
        st.caption("Demo for CBPInsure built and owned by Trigent")


def require_login() -> dict:
    """Gate the page. Renders the login form and stops if not authenticated.
    Returns the authenticated user dict."""
    user = current_user()
    if not user:
        _login_form()
        st.stop()
    return user
