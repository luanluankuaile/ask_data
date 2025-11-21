import streamlit as st
import os
import json
from query_sql import generate_sql_from_prompt, execute_sql, DATABASE_URI, run_function_tool_flow

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
            # If an Azure key is configured use the LLM function-tool flow and show assistant output
            if os.environ.get('AZURE_OPENAI_API_KEY'):
                assistant_text, tool_output = run_function_tool_flow(prompt)
                st.subheader("Assistant response")
                st.write(assistant_text)
                if tool_output:
                    st.subheader("Tool output (raw)")
                    try:
                        st.json(json.loads(tool_output))
                    except Exception:
                        st.text(tool_output)
                # store for reference
                st.session_state['last_assistant'] = assistant_text
                st.session_state['last_tool_output'] = tool_output
                # Try to extract a SQL SELECT statement from the assistant reply so the Execute flow can use it.
                def _extract_sql_from_text(text: str) -> str | None:
                    import re
                    if not text:
                        return None
                    # look for a SELECT ...; block (greedy until first semicolon)
                    m = re.search(r"(?is)(select\b.+?;)", text)
                    if m:
                        return m.group(1).strip().rstrip(';')
                    # fallback: if text starts with SELECT, take the first paragraph
                    m2 = re.search(r"(?is)^(select\b.+)$", text.strip())
                    if m2:
                        return m2.group(1).strip().rstrip(';')
                    return None

                extracted_sql = _extract_sql_from_text(assistant_text)
                if extracted_sql:
                    st.session_state['last_sql'] = extracted_sql
                    st.session_state['last_params'] = {}
                    st.info("Extracted SQL from assistant reply and stored to run (see 'Run SQL').")
                else:
                    # provide a manual action to copy assistant text into last_sql if desired
                    if st.button("Use assistant text as SQL"):
                        st.session_state['last_sql'] = assistant_text
                        st.session_state['last_params'] = {}
                        st.success("Assistant text saved to 'last_sql'. You can now Run SQL.")
            else:
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
