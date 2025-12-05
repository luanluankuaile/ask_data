import streamlit as st
import os
import json
from query_sql import run_function_tool_flow, DATABASE_URI

st.set_page_config(page_title="Ask Data", layout="wide")
st.title("Ask Your Data")

st.write(f"Using `DATABASE_URI`: `{DATABASE_URI}`")

if 'nl_prompt' not in st.session_state:
    st.session_state['nl_prompt'] = ""

col1, col2 = st.columns([9, 1])
with col1:
    prompt = st.text_input("Enter your question about data you have in database", 
                           key='nl_prompt',
                           placeholder="What data can I ask about?",
                           label_visibility="visible")
with col2:
    st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
    submit_clicked = st.button("➜", help="Submit your question")

if submit_clicked:
    try:
        # Main workflow: main.py receives prompt → run_function_tool_flow (uses function_tool + NL generation) → display results
        assistant_text, tool_output = run_function_tool_flow(prompt)
        
        st.subheader("🤖 AI Assistant Response")
        st.write(assistant_text)
        
        if tool_output:
            st.subheader("📊 Query Results")
            try:
                data = json.loads(tool_output)
                # Two types of results:
                # 1. Statistics (dict with single value like count) - displayed as simple metric
                # 2. Student details (list of records) - displayed as table
                if isinstance(data, dict):
                    # Statistics result (e.g., {"count": 42})
                    import pandas as pd
                    df = pd.DataFrame([data])
                    st.dataframe(df)
                elif isinstance(data, list) and len(data) > 0:
                    # Student details result (list of student objects)
                    import pandas as pd
                    df = pd.DataFrame(data)
                    st.dataframe(df)
                else:
                    st.json(data)
            except Exception:
                st.text(tool_output)
        
        # Store for reference
        st.session_state['last_assistant'] = assistant_text
        st.session_state['last_tool_output'] = tool_output
    except Exception as e:
        st.error(f"Failed to process query: {e}")

st.markdown("---")
st.caption("This app translates natural language questions into SQL queries. It intelligently identifies relevant tables based on your question and generates secure SELECT statements. Supports multi-table queries with automatic schema detection.")
