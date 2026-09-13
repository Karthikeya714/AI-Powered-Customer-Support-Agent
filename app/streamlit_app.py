"""Phase 18 — simple Streamlit demo.

Thin UI over SupportAgent (Phase 12) — kept intentionally minimal per the
plan ("do not over-engineer the frontend"). The core functionality
remains fully usable without Streamlit — see src/agent.py's CLI
(`python -m src.agent "message"`).

Usage:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import os
import sys

# Streamlit Community Cloud launches app/streamlit_app.py in a way that
# doesn't put the repo root on sys.path (unlike `python -m streamlit run
# ...` from the repo root, which does) - so a sibling top-level package
# like `src` isn't importable by default. Add it explicitly, before any
# `from src...` import below.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import streamlit as st

# When hosted on Streamlit Community Cloud, config comes from its Secrets
# manager (st.secrets), not a local .env file (which is gitignored and
# never deployed). Copy secrets into os.environ *before* importing
# src.agent, since that import chain evaluates src.config's Settings()
# immediately via os.getenv() at import time. A no-op locally, where
# src/config.py's own load_dotenv(".env") already populated os.environ.
try:
    for _key, _value in st.secrets.items():
        os.environ.setdefault(_key, str(_value))
except FileNotFoundError:
    pass  # no secrets.toml - fine when running locally with a real .env

from src.agent import SupportAgent
from src.retrieval.index import load_case_metadata_by_id

EXAMPLE_MESSAGES = {
    "-- choose an example or write your own below --": "",
    "Example: common technical issue (expect AUTO_HANDLE)": "My music keeps stopping every few seconds, it's really annoying",
    "Example: security risk (expect ESCALATE)": "I don't recognize this large payment on my account, someone must have hacked in",
}


@st.cache_resource
def get_agent() -> SupportAgent:
    return SupportAgent()


@st.cache_resource
def get_case_metadata() -> dict:
    return load_case_metadata_by_id()


st.set_page_config(page_title="SpotifyCares AI Support Agent")
st.title("SpotifyCares AI Support Agent")
st.caption(
    "Offline research prototype — classifies intent, retrieves similar historical "
    "cases, drafts a grounded reply, and decides AUTO_HANDLE vs ESCALATE. Not "
    "connected to real Twitter/X."
)

example_choice = st.selectbox("Optionally pick a built-in example to load below:", list(EXAMPLE_MESSAGES.keys()))
message = st.text_area("Customer message (edit or replace the text here)", value=EXAMPLE_MESSAGES[example_choice], height=80)

analyze_clicked = st.button("Analyze", type="primary")

if analyze_clicked and not message.strip():
    st.warning("Enter a customer message first.")
elif analyze_clicked:
    with st.spinner("Classifying, retrieving evidence, and deciding..."):
        agent = get_agent()
        result = agent.handle(message.strip())

    st.divider()

    col1, col2 = st.columns(2)
    col1.metric("Intent", result["intent"]["label"])
    col2.metric("Confidence", f"{result['intent']['confidence']:.2f}")
    if result["intent"]["model"]:
        st.caption(f"Classified by: {result['intent']['model']}")

    st.subheader("Similar historical cases")
    if result["retrieved_cases"]:
        case_metadata = get_case_metadata()
        for case in result["retrieved_cases"]:
            full = case_metadata.get(case["case_id"], {})
            with st.expander(f"{case['case_id']} (similarity={case['similarity']:.2f})"):
                st.write(f"**Customer:** {full.get('customer_message', '(not found)')}")
                st.write(f"**Brand:** {full.get('brand_response', '(not found)')}")
    else:
        st.write("No cases retrieved.")

    st.subheader("Draft reply")
    if result["draft_reply"]:
        st.info(result["draft_reply"])
        if result["evidence_ids"]:
            st.caption(f"Grounded in: {', '.join(result['evidence_ids'])}")
        if result["grounding_note"]:
            st.caption(result["grounding_note"])
        if result["generation_model"]:
            st.caption(f"Drafted by: {result['generation_model']}")
    else:
        st.write("*(no draft — escalated before generation was attempted)*")

    st.subheader("Decision")
    action = result["decision"]["action"]
    if action == "AUTO_HANDLE":
        st.success(action)
    else:
        st.error(action)
    st.write(f"**Reason:** {result['decision']['reason']}")
