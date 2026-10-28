"""
Authenticate API requests using Supabase Auth.
This dependency runs before protected route handlers.
Supabase verifies each uncached bearer token.
The database supplies the current application role.

This file implements Phase 4 authentication.
It does not implement quotas or a frontend.
The public health route needs no authentication.
All other application routes use this dependency.

The anon key is sufficient for token verification.
The service role key is not used here.
Credentials are unwrapped only at the client boundary.
Provider exceptions never reach the response.

Only the configured college email domain is allowed.
Email comparisons ignore letter case.
Suffix lookalikes must fail the domain check.
The verified identity supplies the profile ID.

Profiles are loaded on every request.
Role changes therefore take effect immediately.
Missing profiles are treated as unauthenticated.
Client metadata cannot grant an admin role.

The identity cache lasts at most sixty seconds.
Entries never outlive the token expiry time.
Revocation can take sixty seconds to take effect.
Hashed cache keys avoid retaining bearer tokens.

The cache is bounded for this single-process prototype.
A lock protects it across FastAPI worker threads.
Tests replace Supabase and database calls.
Tests use fake tokens and disable dotenv loading.
No authentication state is written to disk.
"""

import base64
import hashlib
import json
from threading import Lock
from time import time, monotonic

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.rows import dict_row
from supabase import create_client

from app.config import Settings
from app.db import get_conn

bearer = HTTPBearer(auto_error=False)
_identity_cache = {}
_cache_lock = Lock()
CACHE_SECONDS = 60
MAX_CACHE_ENTRIES = 256
_rate_lock = Lock()
_rate_events = {}
RATE_LIMITS = {"upload": (10, 3600), "worksheet": (30, 3600), "chat": (30, 60)}


def check_rate_limit(user_id, category):
    limit, window = RATE_LIMITS[category]
    now = monotonic()
    with _rate_lock:
        # Drop expired entries so idle accounts do not accumulate indefinitely.
        for key, events in list(_rate_events.items()):
            remaining = [event for event in events if now - event < RATE_LIMITS[key[1]][1]]
            if remaining:
                _rate_events[key] = remaining
            else:
                del _rate_events[key]
        key = (str(user_id), category)
        events = _rate_events.setdefault(key, [])
        if len(events) >= limit:
            retry = max(1, int(window - (now - events[0])) + 1)
            raise HTTPException(429, f"Too many {category} requests. Please try again later.",
                                headers={"Retry-After": str(retry)})
        events.append(now)


def is_allowed_email(email: str, domain: str) -> bool:
    parts = email.lower().split("@")
    return len(parts) == 2 and bool(parts[0]) and parts[1] == domain.lower()


def verified_identity(token: str, settings):
    key = hashlib.sha256(token.encode()).hexdigest()
    with _cache_lock:
        cached = _identity_cache.get(key)
        if cached and cached[0] > time():
            return cached[1]
    try:
        client = create_client(settings.supabase_url, settings.supabase_anon_key.get_secret_value())
        user = client.auth.get_user(token).user
        if user is None or not user.id or not user.email:
            raise ValueError("Missing identity")
        # Decode expiry only AFTER Supabase verifies the token; this is not verification.
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        expiry = float(claims["exp"])
        if not expiry > time():
            raise ValueError("Expired token")
        identity = {"id": user.id, "email": user.email}
    except Exception:
        raise HTTPException(401, "Invalid or expired access token.",
                            headers={"WWW-Authenticate": "Bearer"}) from None
    with _cache_lock:
        now = time()
        for old_key in list(_identity_cache):
            if _identity_cache[old_key][0] <= now:
                del _identity_cache[old_key]
        if len(_identity_cache) >= MAX_CACHE_ENTRIES:
            del _identity_cache[next(iter(_identity_cache))]
        _identity_cache[key] = (min(now + CACHE_SECONDS, expiry), identity)
    return identity


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if credentials is None:
        raise HTTPException(401, "Provide a bearer access token.",
                            headers={"WWW-Authenticate": "Bearer"})
    settings = Settings()
    identity = verified_identity(credentials.credentials, settings)
    if not is_allowed_email(identity["email"], settings.allowed_email_domain):
        raise HTTPException(403, "Use your college email address.")
    with get_conn() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("select id, role from public.profiles where id = %s", (identity["id"],))
            profile = cursor.fetchone()
    if profile is None:
        raise HTTPException(401, "User profile not found.", headers={"WWW-Authenticate": "Bearer"})
    return {"id": profile["id"], "email": identity["email"], "role": profile["role"]}


def require_role(*roles):
    def check_role(user=Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "Your role cannot perform this action.")
        return user
    return check_role
