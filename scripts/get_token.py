"""
Perform a development email OTP login.
This helper belongs to Phase 4.
Run it from the repository root.
The Supabase anon key sends and verifies the OTP.

The email address is entered interactively.
The college domain is checked before sending mail.
The OTP is entered without terminal echo.
No login credentials are accepted as arguments.

Supabase creates a session after verification.
The access token stays in memory unless output is explicitly requested.
Never paste tokens anywhere public.
The --print-token flag explicitly opts into terminal output.

Without the flag, this helper makes an authenticated request.
It calls the local backend's me endpoint by default.
Only email and role are displayed by default.
With the flag, it prints the token after login and exits.

Start FastAPI before using the default identity check.
The backend verifies the returned access token.
The backend reads the user's current profile.
The migration must have been applied first.

The helper does not promote any user.
An administrator is promoted manually with SQL.
The helper does not store a session on disk.
The Supabase client disables session persistence.

Network failures produce fixed error messages.
Raw provider exceptions are never printed.
Tests replace input and external services.
No frontend or quota behavior is implemented here.
Token output does not require a running local backend.
"""

import argparse
from getpass import getpass
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

from supabase import ClientOptions, create_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import is_allowed_email
from app.config import Settings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Log in with email OTP for local API testing.")
    parser.add_argument(
        "--print-token", action="store_true",
        help="Print the access token after login instead of checking /me.",
    )
    args = parser.parse_args(argv)
    try:
        settings = Settings()
        email = input("College email: ").strip().lower()
        if not is_allowed_email(email, settings.allowed_email_domain):
            print("Use your college email address.")
            return 1
        client = create_client(
            settings.supabase_url, settings.supabase_anon_key.get_secret_value(),
            options=ClientOptions(persist_session=False, auto_refresh_token=False),
        )
        client.auth.sign_in_with_otp({"email": email})
        code = getpass("Email OTP code (hidden): ").strip()
        session = client.auth.verify_otp({"email": email, "token": code, "type": "email"}).session
        if session is None or not session.access_token:
            raise ValueError("Missing session")
        if args.print_token:
            # Explicit opt-in supports manual API testing; never paste tokens publicly.
            print(session.access_token)
            return 0
        request = Request("http://127.0.0.1:8000/me",
                          headers={"Authorization": "Bearer " + session.access_token})
        with urlopen(request, timeout=15) as response:
            profile = json.load(response)
        print(f"Email: {profile['email']} | Role: {profile['role']}")
        return 0
    except Exception:
        print("Login check failed; check OTP, Supabase setup, and the running backend.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
