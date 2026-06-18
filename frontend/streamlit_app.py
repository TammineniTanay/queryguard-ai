import streamlit as st
import requests
import json
import pandas as pd

API_URL = "http://localhost:8000"

st.set_page_config(page_title="QueryGuard AI", page_icon="🛡️", layout="wide")

st.title("🛡️ QueryGuard AI")
st.caption("Natural Language to SQL with Hallucination Prevention & PHI/PII Access Control")

# sidebar
with st.sidebar:
    st.header("Settings")
    role = st.selectbox("User Role", ["analyst", "admin"], index=0)
    st.divider()
    st.subheader("Role Permissions")
    if role == "analyst":
        st.warning("⚠️ PHI/PII columns blocked")
        st.code("customers.email → BLOCKED")
    else:
        st.success("✅ Full data access")

    st.divider()
    if st.button("View Schema"):
        try:
            r = requests.get(f"{API_URL}/schema", params={"role": role})
            st.json(r.json())
        except:
            st.error("API not running")

# sample questions
st.subheader("Try a question")
sample_questions = [
    "What is the total revenue from completed orders?",
    "Which product category has the highest average order amount?",
    "How many orders were placed by customers in Texas?",
    "What is the average rating for Electronics products?",
    "Show me customer emails",  # this should be blocked for analyst
]

cols = st.columns(len(sample_questions))
for i, q in enumerate(sample_questions):
    if cols[i].button(q[:30] + "...", key=f"q{i}"):
        st.session_state["question"] = q

# main query input
question = st.text_input(
    "Ask a question about your data",
    value=st.session_state.get("question", ""),
    placeholder="e.g. What is the total revenue by state?"
)

if st.button("Run Query", type="primary") and question:
    with st.spinner("Running pipeline..."):
        try:
            response = requests.post(
                f"{API_URL}/query",
                json={"question": question, "role": role}
            )
            result = response.json()

            # status
            if result["status"] == "error":
                st.error(f"❌ {result.get('message', 'Query failed')}")
                if result.get("flagged"):
                    st.warning("🚨 ACCESS DENIED: PHI/PII column blocked")
            else:
                # confidence badge
                confidence = result.get("confidence") or 0
                col1, col2, col3 = st.columns(3)
                col1.metric("Confidence", f"{confidence:.0%}")
                col2.metric("Tables Used", ", ".join(result.get("tables_used", [])))
                col3.metric("Source", "🌐 Web" if result.get("used_tavily") else "🗄️ Database")

                if result.get("flagged"):
                    st.warning("⚠️ Low confidence — answer may not be fully grounded in data")

                # answer
                st.subheader("Answer")
                st.write(result.get("answer", "No answer generated"))

                # SQL
                with st.expander("Generated SQL"):
                    st.code(result.get("sql", ""), language="sql")

                # results table
                rows = result.get("rows", [])
                if rows:
                    with st.expander(f"Raw Results ({len(rows)} rows)"):
                        st.dataframe(pd.DataFrame(rows))

        except requests.exceptions.ConnectionError:
            st.error("Cannot connect to API. Run: `uvicorn app.api:app --reload`")
        except Exception as e:
            st.error(f"Error: {str(e)}")
