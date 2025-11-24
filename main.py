import streamlit as st
import os
import json
from query_sql import run_function_tool_flow, generate_sql_from_prompt, execute_sql, DATABASE_URI

st.set_page_config(page_title="NL→SQL (students)", layout="wide")
st.title("Ask your `students` table")

st.write(f"Using `DATABASE_URI`: `{DATABASE_URI}`")

if 'nl_prompt' not in st.session_state:
    st.session_state['nl_prompt'] = "How many students do you have?"
prompt = st.text_input("Enter a question about the `students` table", key='nl_prompt')

if st.button("Generate and Query"):
    try:
        # Main workflow: main.py receives prompt → run_function_tool_flow (uses function_tool + NL generation) → display results
        if os.environ.get('AZURE_OPENAI_API_KEY'):
            # Use LLM function-tool flow: calls query_students function and generates natural language response
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
        else:
            # Fallback: use simple SQL generation without function tools
            sql, params = generate_sql_from_prompt(prompt)
            st.subheader("📝 Generated SQL")
            st.code(sql, language="sql")
            if params:
                st.write("Parameters:", params)
            
            # Execute the SQL directly and show results
            try:
                cols, rows = execute_sql(sql, params)
                import pandas as pd
                df = pd.DataFrame(rows, columns=cols)
                st.success(f"Query returned {len(df)} rows")
                st.dataframe(df)
            except Exception as e:
                st.error(f"Failed to execute SQL: {e}")
    except Exception as e:
        st.error(f"Failed to process query: {e}")

st.markdown("---")
st.caption("This app translates a natural language prompt into a safe SELECT SQL statement targeting the `students` table. Execution is optional and runs against the configured DATABASE_URI.")
