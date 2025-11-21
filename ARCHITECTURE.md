# Architecture Documentation

## Method Call Relationships

### Main Flow

```
User Input (Streamlit UI)
    ↓
main.py: Receives prompt
    ↓
query_sql.py: run_function_tool_flow(prompt)
    ↓
    ├── LLM analyzes prompt and decides which function tool to call
    ↓
query_sql.py: query_students(enroll_after_year, enroll_before_year, is_active, limit)
    ↓
    ├── Executes SQL query
    ├── Returns JSON-formatted query results
    ↓
run_function_tool_flow: LLM generates natural language response based on query results
    ↓
    ├── assistant_text: Natural language response
    ├── tool_output: Raw JSON query results
    ↓
main.py: Streamlit displays results
    ├── Shows AI assistant response
    └── Shows data table
```

### Detailed Explanation

#### 1. **main.py** - Streamlit UI Layer

**Responsibilities**: 
- Receives user's natural language prompt
- Calls `run_function_tool_flow()` to process the request
- Displays results in Streamlit interface

**Key Code**:
```python
# Receive prompt
prompt = st.text_input("Enter a question about the `students` table", key='nl_prompt')

# Call main processing function
assistant_text, tool_output = run_function_tool_flow(prompt)

# Display results
st.write(assistant_text)  # AI-generated natural language response
st.json(tool_output)      # Raw query data
st.dataframe(df)          # Table display
```

#### 2. **query_sql.py: run_function_tool_flow()** - Main Workflow Function

**Responsibilities**:
- Acts as bridge between main.py and underlying query functions
- Uses LLM's function calling capability
- Converts prompt to function tool calls
- Generates final natural language response

**Workflow**:
1. Receives natural language prompt
2. Configures LLM client (Azure OpenAI)
3. Defines function tool schema (describes query_students function)
4. First LLM call: Analyzes prompt and decides which function to call with what parameters
5. Executes function tool: Calls `query_students()`
6. Second LLM call: Generates natural language response based on query results
7. Returns (assistant_text, tool_output)

**Return Values**:
- `assistant_text`: LLM-generated natural language response explaining the results
- `tool_output`: Raw JSON data returned by `query_students()`

#### 3. **query_sql.py: query_students()** - Function Tool

**Responsibilities**:
- Acts as an LLM-callable function tool
- Executes actual SQL queries
- Returns JSON-formatted data

**Parameters**:
- `enroll_after_year`: Filter by enrollment year (optional)
- `is_active`: Filter by active status (optional)
- `limit`: Limit number of rows returned (default: 100)

**Return Value**:
- JSON string containing list of student data

**Key Features**:
- LLM automatically decides when to call this function
- LLM infers parameter values from prompt
- Query results are used by LLM to generate final response

### Fallback Flow

If `AZURE_OPENAI_API_KEY` is not configured:

```
main.py: Receives prompt
    ↓
query_sql.py: generate_sql_from_prompt(prompt)
    ↓
    ├── Uses simple rules to generate SQL
    └── Returns SQL statement and parameters
    ↓
main.py: Displays SQL code
```

## Core Advantages

1. **Intelligence**: LLM automatically understands user intent without manual SQL writing
2. **Flexibility**: Function calling allows LLM to invoke arbitrary function tools
3. **Extensibility**: Easy to add more function tools
4. **User-Friendly**: Natural language input/output with automatic table formatting

## Example Dialog Flow

**User**: "How many students enrolled after 2020?"

1. `main.py` receives prompt
2. `run_function_tool_flow()` starts
3. LLM analyzes: "Need to query students enrolled after 2020"
4. LLM decides to call: `query_students(enroll_after_year=2020, limit=100)`
5. `query_students()` executes SQL query, returns JSON data
6. LLM analyzes returned data, generates response: "There are 25 students who enrolled after 2020."
7. `main.py` displays:
   - AI response: "There are 25 students who enrolled after 2020."
   - Data table: Shows detailed information of all 25 students

## Tech Stack

- **Frontend**: Streamlit
- **AI**: Azure OpenAI (GPT-4o) with Function Calling
- **Database**: PostgreSQL / SQLite
- **ORM**: SQLAlchemy
- **Language**: Python 3.10+
