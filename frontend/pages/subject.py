"""
Display module PDFs and send scoped questions to the backend.
Chat history and source metadata stay in the subject's session history.
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


def scope_ids(scope, module, document):
    if scope == "Whole subject":
        return None, None
    if scope == "This PDF":
        if document is None:
            raise ValueError("Select a ready PDF first.")
        return module["id"], document["id"]
    return module["id"], None


def show_answer(message, code):
    st.markdown(message["answer"])
    with st.expander("Sources"):
        for source in message["sources"]:
            module = f'Module {source["module"]}' if source["module"] is not None else "Whole subject"
            st.text(f'[{source["n"]}] {code} · {module} · {source["document"]} · '
                    f'p.{source["page"]} (score {source["score"]:.2f})')


def render():
    subject = st.session_state.get("selected_subject")
    if not subject:
        st.info("Open a subject from Home.")
        return
    subject_id = subject["id"]
    st.title(f'{subject["code"]} · {subject["name"]}')
    modules = api.modules(subject_id)
    if not modules:
        st.info("No modules yet.")
        return
    documents = {}
    for module in modules:
        with st.expander(f'Module {module["number"]} · {module["title"]}'):
            documents[module["id"]] = api.documents(module["id"])
            for document in documents[module["id"]]:
                st.write(f'{document["title"]} · {document["status"]}')
                if document["status"] == "ready":
                    if st.button("Get PDF link", key=f'pdf_{document["id"]}'):
                        st.link_button("View PDF", api.pdf_url(document["id"]))
            if not documents[module["id"]]:
                st.caption("No PDFs uploaded yet.")
    module = st.selectbox("Selected module", modules,
                          format_func=lambda item: f'Module {item["number"]} · {item["title"]}',
                          key=f"module_{subject_id}")
    scope = st.radio("Ask from", ["This module", "This PDF", "Whole subject"],
                     horizontal=True, key=f"scope_{subject_id}")
    ready = [doc for doc in documents[module["id"]] if doc["status"] == "ready"]
    document = None
    if scope == "This PDF":
        if ready:
            document = st.selectbox("Selected PDF", ready, format_func=lambda item: item["title"],
                                    key=f'chat_pdf_{subject_id}_{module["id"]}')
        else:
            st.info("This module has no ready PDFs.")
    usage = api.usage()
    remaining = max(0, usage["limit"] - usage["used"])
    st.caption(f'Questions left today: {remaining}/{usage["limit"]}')
    if remaining == 0:
        st.info("Use your own Google AI Studio key in Settings to keep going.")
    histories = st.session_state.setdefault("histories", {})
    history = histories.setdefault(subject_id, [])
    for message in history:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                show_answer(message, subject["code"])
            else:
                st.markdown(message["content"])
    question = st.chat_input("Ask about your notes", max_chars=1000,
                             disabled=scope == "This PDF" and document is None)
    if question and question.strip():
        module_id, document_id = scope_ids(scope, module, document)
        # Append only completed exchanges so a failed request can be retried cleanly.
        with st.spinner("Looking in your notes…"):
            answer = api.ask(question.strip(), subject_id, module_id, document_id)
        history.append({"role": "user", "content": question.strip()})
        history.append({"role": "assistant", **answer})
        st.rerun()
