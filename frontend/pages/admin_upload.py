"""
Upload official PDFs and poll their backend ingestion status.
The current backend role is checked before rendering admin controls.
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


@st.fragment(run_every="3s")
def upload_status():
    document_id = st.session_state.get("pending_upload")
    if not document_id:
        return
    try:
        document = api.document_status(document_id)
    except api.ApiError as error:
        st.error(str(error))
        return
    if document["status"] == "ready":
        st.success(f'{document["title"]} is ready.')
        st.session_state.pop("pending_upload", None)
    elif document["status"] == "failed":
        st.error("PDF ingestion failed. Check PDF text, model access, and backend setup.")
        st.session_state.pop("pending_upload", None)
    else:
        st.info("Processing PDF… Status refreshes every three seconds.")


def render():
    if api.me()["role"] != "admin":
        st.error("Administrator access required.")
        return
    st.title("Admin upload")
    subjects = api.subjects()
    if not subjects:
        st.info("No subjects yet.")
        return
    subject = st.selectbox("Subject", subjects, format_func=lambda item: item["code"])
    modules = api.modules(subject["id"])
    if not modules:
        st.info("No modules for this subject.")
        return
    module = st.selectbox("Module", modules,
                          format_func=lambda item: f'Module {item["number"]} · {item["title"]}',
                          key=f'upload_module_{subject["id"]}')
    with st.form("upload_pdf", clear_on_submit=True):
        title = st.text_input("Title", max_chars=500)
        uploaded = st.file_uploader("Official PDF (under 25 MB)", type=["pdf"])
        submit = st.form_submit_button("Upload", disabled=bool(st.session_state.get("pending_upload")))
    if submit:
        if not title.strip() or uploaded is None:
            st.error("Provide a title and PDF.")
        elif uploaded.size >= 25 * 1024 * 1024:
            st.error("PDF must be under 25 MB.")
        else:
            document = api.upload(subject["id"], module["id"], title.strip(), uploaded)
            st.session_state["pending_upload"] = document["id"]
            st.rerun()
    upload_status()
