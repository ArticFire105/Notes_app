"""
Proxy email OTP and session refresh through FastAPI.
Supabase Auth uses the anon key without persisting sessions.
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

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, SecretStr
from supabase import ClientOptions, create_client

from app.auth import is_allowed_email
from app.config import Settings

router = APIRouter(prefix="/auth", tags=["login"])


class EmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class VerifyRequest(EmailRequest):
    code: SecretStr


class RefreshRequest(BaseModel):
    refresh_token: SecretStr


def login_client():
    settings = Settings()
    client = create_client(
        settings.supabase_url, settings.supabase_anon_key.get_secret_value(),
        options=ClientOptions(persist_session=False, auto_refresh_token=False),
    )
    return settings, client


def college_email(email, settings):
    email = email.strip().lower()
    if not is_allowed_email(email, settings.allowed_email_domain):
        raise HTTPException(403, "Use your college email address.")
    return email


def session_response(session, request):
    if session is None or not session.access_token or not session.refresh_token:
        raise HTTPException(401, "Login failed. Request a new code and try again.")
    # HTTP caches must never retain the response containing session credentials.
    browser = request.headers.get("X-Browser-Session") == "1"
    content = {"access_token": session.access_token, "expires_at": session.expires_at}
    if not browser:
        content["refresh_token"] = session.refresh_token
    response = JSONResponse(content=content, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
    if browser:
        secure = request.url.scheme == "https"
        response.set_cookie("notes_refresh", session.refresh_token, max_age=30 * 24 * 60 * 60,
                            httponly=True, secure=secure, samesite="none" if secure else "lax", path="/auth")
    return response


@router.post("/send-code")
def send_code(request: EmailRequest):
    settings, client = login_client()
    email = college_email(request.email, settings)
    try:
        client.auth.sign_in_with_otp({"email": email})
    except Exception:
        raise HTTPException(400, "Could not send code. Check the email and try again later.") from None
    return {"message": "Check your college email for the code."}


@router.post("/verify")
def verify_code(request: VerifyRequest, http_request: Request):
    settings, client = login_client()
    email = college_email(request.email, settings)
    code = request.code.get_secret_value()
    if not 6 <= len(code) <= 8 or not code.isascii() or not code.isdigit():
        raise HTTPException(400, "Enter the 6–8 digit email code.")
    try:
        session = client.auth.verify_otp(
            {"email": email, "token": code, "type": "email"}
        ).session
    except Exception:
        raise HTTPException(401, "Code invalid or expired. Request a new code.") from None
    return session_response(session, http_request)


@router.post("/refresh")
def refresh_session(http_request: Request, request: RefreshRequest | None = None):
    if request is None and http_request.headers.get("X-Browser-Session") != "1":
        raise HTTPException(403, "Browser session header required.")
    settings, client = login_client()
    try:
        token = request.refresh_token.get_secret_value() if request else http_request.cookies.get("notes_refresh")
        if not token:
            raise ValueError("Missing session")
        session = client.auth.refresh_session(token).session
        if session is None or session.user is None:
            raise ValueError("Missing identity")
        college_email(session.user.email or "", settings)
    except Exception:
        raise HTTPException(401, "Session expired. Please sign in again.") from None
    return session_response(session, http_request)


@router.post("/logout")
def logout(request: Request):
    if request.headers.get("X-Browser-Session") != "1":
        raise HTTPException(403, "Browser session header required.")
    response = JSONResponse(content={"ok": True}, headers={"Cache-Control": "no-store"})
    response.delete_cookie("notes_refresh", path="/auth")
    return response
