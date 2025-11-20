import streamlit as st
import os
from query_sql import generate_sql_from_prompt, execute_sql, DATABASE_URI

st.set_page_config(page_title="NL→SQL (students)", layout="wide")
st.title("Ask your `students` table (NL → SQL)")

st.write(f"Using `DATABASE_URI`: `{DATABASE_URI}`")

if 'nl_prompt' not in st.session_state:
    st.session_state['nl_prompt'] = "How many students do you have?"
prompt = st.text_input("Enter a question about the `students` table", key='nl_prompt')

col1, col2 = st.columns([2, 1])
with col1:
    if st.button("Generate SQL"):
        try:
            sql, params = generate_sql_from_prompt(prompt)
            st.code(sql, language="sql")
            if params:
                st.write("Parameters:", params)
            st.session_state['last_sql'] = sql
            st.session_state['last_params'] = params
        except Exception as e:
            st.error(f"Failed to generate SQL: {e}")

    execute = st.checkbox("Execute generated SQL", value=False)
    if execute:
        if st.button("Run SQL"):
            sql_to_run = st.session_state.get('last_sql')
            if not sql_to_run:
                st.warning("No generated SQL found. Click 'Generate SQL' first.")
            else:
                try:
                    params = st.session_state.get('last_params') or {}
                    cols, rows = execute_sql(sql_to_run, params)
                    import pandas as pd
                    df = pd.DataFrame(rows, columns=cols)
                    st.success(f"Query returned {len(df)} rows")
                    st.dataframe(df)
                except Exception as e:
                    st.error(f"Failed to execute SQL: {e}")

with col2:
    st.header("Quick prompts")
    def _set_prompt(val: str):
        # callback to update the prompt before rerun
        st.session_state['nl_prompt'] = val

    if st.button("Count students", on_click=_set_prompt, args=("How many students do you have?",)):
        pass
    if st.button("List recent students", on_click=_set_prompt, args=("List students",)):
        pass

st.markdown("---")
st.caption("This app translates a natural language prompt into a safe SELECT SQL statement targeting the `students` table. Execution is optional and runs against the configured DATABASE_URI.")
