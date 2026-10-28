"""
Assemble Streamlit navigation behind a backend login gate.
Every page reaches application data through api_client.
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

from pathlib import Path
import sys

import streamlit as st

# Streamlit starts this file as a script; expose the repo package consistently.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend import api_client as api
from frontend.pages import admin_upload, home, login, my_notes, past_papers, quiz, settings, subject

st.set_page_config(page_title="Lecture Notes", page_icon="📚", layout="wide")

if not st.session_state.get("access_token"):
    st.navigation([st.Page(login.render, title="Login", url_path="login", default=True)]).run()
else:
    try:
        profile = api.me()
    except api.ApiError as error:
        st.error(str(error))
        if st.button("Return to login"):
            api.clear_session()
            st.rerun()
        st.stop()
    st.sidebar.caption(profile["email"])
    if st.sidebar.button("Log out"):
        api.clear_session()
        st.rerun()
    home_page = st.Page(home.render, title="Home", url_path="home", default=True)
    subject_page = st.Page(subject.render, title="Subject", url_path="subject")
    st.session_state["subject_page"] = subject_page
    pages = [home_page, subject_page, st.Page(settings.render, title="Settings", url_path="settings"),
             st.Page(my_notes.render, title="My handwritten notes", url_path="my-notes"),
             st.Page(past_papers.render, title="Past papers", url_path="past-papers"),
             st.Page(quiz.render, title="Quiz", url_path="quiz")]
    if profile["role"] == "admin":
        pages.append(st.Page(admin_upload.render, title="Admin upload", url_path="admin-upload"))
    try:
        st.navigation(pages).run()
    except api.ApiError as error:
        st.error(str(error))
