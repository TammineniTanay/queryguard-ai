from __future__ import annotations

import requests
import pandas as pd
import streamlit as st

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="QueryGuard AI", page_icon="🛡️", layout="wide")

st.title("🛡️ QueryGuard AI")
st.caption("Secure natural-language analytics over governed BigQuery-style tables")

with st.sidebar:
    st.header("Demo User")
    user_id = st.text_input("User ID", value="demo-user")
    role = st.selectbox("Role", ["executive", "finance_analyst", "clinical_analyst"], index=1)
    limit = st.slider("Row limit", 10, 500, 100, 10)
    st.divider()
    st.subheader("Try these")
    st.markdown("""
- Total claim amount by department
- Average claim amount by diagnosis for cardiology
- How many patients are in each region?
- Show denied claims by department
- List patient emails and claim amounts
""")

question = st.text_area("Ask a business question", value="What is the total claim amount by department?", height=100)

if st.button("Ask", type="primary"):
    payload = {"question": question, "user_id": user_id, "role": role, "limit": limit}
    try:
        resp = requests.post(f"{API_BASE}/ask", json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not reach backend: {exc}")
        st.stop()

    if data.get("blocked"):
        st.error(data.get("block_reason") or "Blocked by guardrails")
    else:
        st.success(data["explanation"])
        rows = data.get("rows", [])
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            st.info("No rows returned.")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Generated SQL")
        st.code(data.get("sql", ""), language="sql")
    with col2:
        st.subheader("Safe SQL after policy")
        st.code(data.get("safe_sql", ""), language="sql")

    with st.expander("Validation and audit"):
        st.json({
            "validation": data.get("validation"),
            "audit_id": data.get("audit_id"),
            "role": data.get("role"),
        })

st.divider()
st.markdown("""
### Demo story
This MVP shows how the system prevents hallucinations and protects sensitive data:
1. The assistant only uses approved catalog metrics, dimensions, tables, and joins.
2. The SQL validator blocks unsafe or unapproved queries before execution.
3. The policy layer masks or blocks PHI/PII based on role.
4. The audit log records every question and SQL decision.
""")
