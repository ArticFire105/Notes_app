"""
Wrap backend HTTP endpoints for the Streamlit screens.
Only session state retains authentication and BYOK credentials.
This file implements only Phase 6.
The UI communicates with FastAPI over HTTP.
Database access belongs to the backend.
Service role credentials belong to the backend.
Frontend configuration uses the process environment.
No frontend code loads a dotenv file.
Access tokens belong to Streamlit session state.
Refresh tokens belong to Streamlit session state.
User API keys belong to Streamlit session state.
Secrets never belong in URLs.
Secrets never belong in cached functions.
Secrets never belong in log messages.
Raw provider errors are hidden.
Backend authorization remains authoritative.
Roles come from the current user profile.
Official notes define the available question scope.
Module database IDs differ from display numbers.
PDF links are signed by the backend.
Chat histories are separated by subject.
Sources remain attached to their answers.
Daily allowance comes from the backend.
BYOK requests use a request header.
Uploads use the existing PDF endpoint.
Ingestion status is checked separately.
Later phase pages remain placeholders.
Functions stay small to support learning.
Tests replace remote services.
Tests do not open real dotenv files.
Live email delivery requires manual testing.
Run uv run pytest from the repository root.
Start FastAPI before starting Streamlit.
"""

import os
from time import time

import httpx
import streamlit as st


class ApiError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def save_session(session):
    for name in ("access_token", "refresh_token", "expires_at"):
        st.session_state[name] = session.get(name)


def clear_session():
    # Clear histories and widget values too when a different user signs in.
    st.session_state.clear()


def request(method, path, *, authenticated=True, use_key=False, **kwargs):
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    if authenticated and st.session_state.get("expires_at"):
        if st.session_state["expires_at"] <= time() + 30:
            try:
                session = request("POST", "/auth/refresh", authenticated=False,
                                  json={"refresh_token": st.session_state.get("refresh_token", "")})
                save_session(session)
            except ApiError as error:
                if error.status == 401:
                    clear_session()
                raise
    headers = {}
    if authenticated:
        headers["Authorization"] = "Bearer " + st.session_state.get("access_token", "")
    if use_key and st.session_state.get("user_api_key"):
        headers["X-User-Api-Key"] = st.session_state["user_api_key"]
    try:
        # No redirects: credentials must stay at the configured backend.
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            response = client.request(method, base_url + path, headers=headers, **kwargs)
    except httpx.RequestError:
        raise ApiError("Cannot reach the backend. Check that FastAPI is running.") from None
    if response.status_code >= 300:
        messages = {
            400: "Check your input and try again.",
            401: "Your session or login code expired. Please sign in again.",
            403: "Your account does not have permission for this action.",
            404: "This item is no longer available.",
            409: "This document already exists. Choose another title.",
            413: "The PDF is too large. Choose a file under 25 MB.",
            422: "Check the selected scope and required fields.",
            429: "Allowance or rate limit reached. Add your own key in Settings, or try later.",
        }
        if authenticated and response.status_code == 401:
            clear_session()
        # Never display response bodies: upstream diagnostics may contain secrets.
        raise ApiError(messages.get(response.status_code, "Backend request failed. Please try later."),
                       response.status_code)
    try:
        return response.json()
    except ValueError:
        raise ApiError("The backend returned an unreadable response.") from None


def send_code(email):
    return request("POST", "/auth/send-code", authenticated=False, json={"email": email})


def verify_code(email, code):
    return request("POST", "/auth/verify", authenticated=False, json={"email": email, "code": code})


def me():
    return request("GET", "/me")


def usage():
    return request("GET", "/me/usage")


def subjects():
    return request("GET", "/subjects")


def modules(subject_id):
    return request("GET", f"/subjects/{subject_id}/modules")


def documents(module_id):
    return request("GET", f"/modules/{module_id}/documents")


def document_status(document_id):
    return request("GET", f"/documents/{document_id}")


def pdf_url(document_id):
    return request("GET", f"/documents/{document_id}/pdf-url")["url"]


def ask(question, subject_id, module_id=None, document_id=None):
    return request("POST", "/ask", use_key=True,
                   json={"question": question, "subject_id": subject_id,
                         "module_id": module_id, "document_id": document_id})


def test_key():
    return request("POST", "/me/test-key", use_key=True)


def upload(subject_id, module_id, title, uploaded):
    return request("POST", "/documents",
                   data={"subject_id": subject_id, "module_id": module_id, "title": title},
                   files={"file": (uploaded.name, uploaded.getvalue(), "application/pdf")})
