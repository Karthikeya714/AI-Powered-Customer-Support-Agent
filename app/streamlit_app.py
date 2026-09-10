"""Phase 18 — simple Streamlit demo.

Thin UI over SupportAgent (Phase 12) — kept intentionally minimal per the
plan ("do not over-engineer the frontend"). The core functionality
remains fully usable without Streamlit — see src/agent.py's CLI
(`python -m src.agent "message"`).

Usage:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import streamlit as st

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

example_choice = st.selectbox("Try an example, or write your own message below:", list(EXAMPLE_MESSAGES.keys()))
message = st.text_area("Customer message", value=EXAMPLE_MESSAGES[example_choice], height=80)

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
    else:
        st.write("*(no draft — escalated before generation was attempted)*")

    st.subheader("Decision")
    action = result["decision"]["action"]
    if action == "AUTO_HANDLE":
        st.success(action)
    else:
        st.error(action)
    st.write(f"**Reason:** {result['decision']['reason']}")
