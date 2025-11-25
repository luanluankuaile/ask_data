import streamlit as st
import os
import json
from query_sql import run_function_tool_flow, DATABASE_URI

st.set_page_config(page_title="NL→SQL (students)", layout="wide")
st.title("Ask your `students` table")

st.write(f"Using `DATABASE_URI`: `{DATABASE_URI}`")

if 'nl_prompt' not in st.session_state:
    st.session_state['nl_prompt'] = "How many students do you have?"
prompt = st.text_input("Enter a question about the `students` table", key='nl_prompt')

if st.button("Generate and Query"):
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
st.caption("This app translates a natural language prompt into a safe SELECT SQL statement targeting the `students` table. Execution is optional and runs against the configured DATABASE_URI.")
