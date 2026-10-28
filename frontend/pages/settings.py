"""
Show today's allowance and manage a session-only Google API key.
Key testing uses the backend rather than contacting Google directly.
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


def save_key():
    st.session_state["user_api_key"] = st.session_state.get("key_input", "").strip()


def remove_key():
    st.session_state.pop("user_api_key", None)
    st.session_state["key_input"] = ""


def render():
    st.title("Settings")
    usage = api.usage()
    st.write(f'Today: {usage["used"]}/{usage["limit"]} shared-key questions used.')
    st.caption(f'Resets at {usage["resets_at"]}')
    st.subheader("Use your own key")
    st.markdown("[Google AI Studio](https://aistudio.google.com/apikey): "
                "sign in → Create API key → paste here.")
    st.caption("Your key lives only in this tab's session. Refreshing or closing the tab "
               "clears it. Logging out clears it immediately.")
    # Streamlit removes widget state on other pages; retain the session key across navigation.
    if "key_input" not in st.session_state:
        st.session_state["key_input"] = st.session_state.get("user_api_key", "")
    st.text_input("Google AI Studio API key", type="password", key="key_input",
                  on_change=save_key)
    st.button("Remove key", on_click=remove_key)
    if st.button("Test key", disabled=not st.session_state.get("user_api_key")):
        api.test_key()
        st.success("Your key works.")
    st.write("Free AI Studio keys: Google may use your content to improve its products "
             "(see Google's terms). Don't upload personal info.")
    st.markdown("[Google's terms](https://ai.google.dev/gemini-api/terms)")
    st.caption("Other providers: coming later.")
