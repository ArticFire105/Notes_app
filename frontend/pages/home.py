"""
Show subject cards and route the chosen subject to its page.
Module counts come from the existing backend endpoints.
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
    st.title("Your subjects")
    columns = st.columns(3)
    for index, subject in enumerate(api.subjects()):
        with columns[index % 3]:
            with st.container(border=True):
                st.subheader(subject["code"])
                st.write(subject["name"])
                st.caption(f'{len(api.modules(subject["id"]))} modules')
                if st.button("Open subject", key=f'open_{subject["id"]}'):
                    st.session_state["selected_subject"] = subject
                    st.switch_page(st.session_state["subject_page"])
