"""
Render email OTP login using backend auth endpoints.
Successful verification saves credentials only in the current session.
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

import streamlit as st

from frontend import api_client as api


def render():
    st.title("Lecture Notes")
    st.write("Sign in with your @dxb.manipal.edu email.")
    with st.form("send_code"):
        email = st.text_input("College email").strip().lower()
        send = st.form_submit_button("Send code")
    if send:
        if email.count("@") != 1 or not email.split("@")[0] or email.split("@")[-1] != "dxb.manipal.edu":
            st.error("Use your @dxb.manipal.edu college email address.")
        else:
            try:
                api.send_code(email)
                st.session_state["login_email"] = email
                st.success("Check your college email for a six-digit code.")
            except api.ApiError as error:
                st.error(str(error))
    if st.session_state.get("login_email"):
        st.caption("Code sent to " + st.session_state["login_email"])
        with st.form("verify_code"):
            code = st.text_input("Six-digit code", type="password", max_chars=6)
            verify = st.form_submit_button("Verify")
        if verify:
            if len(code) != 6 or not code.isascii() or not code.isdigit():
                st.error("Enter the six-digit email code.")
                return
            try:
                session = api.verify_code(st.session_state["login_email"], code)
                api.clear_session()
                api.save_session(session)
                st.rerun()
            except api.ApiError as error:
                st.error(str(error))
