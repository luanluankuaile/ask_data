# Architecture Documentation

## System Overview

This is a Natural Language to SQL application that uses Azure OpenAI's LLM with function calling capability to intelligently query a students database. Users input natural language questions, and the system automatically generates SQL queries, executes them, and returns results in both natural language and table format.

## Method Call Relationships

### Main Flow (with Azure OpenAI)

```
┌─────────────────────────────────────────────────────────────────┐
│ User Input: "How many students enrolled after 2020?"           │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 1. main.py: Streamlit receives prompt                          │
│    - User enters question in text input                         │
│    - Clicks "Generate and Query" button                         │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. main.py calls: run_function_tool_flow(prompt)               │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. run_function_tool_flow: Initialize LLM client               │
│    - Creates Azure OpenAI client                                │
│    - Query schema_metadata table for ALL tables                 │
│    - Format metadata with business descriptions                 │
│    - Prepares function tool definition:                         │
│      • execute_query() - executes LLM-generated SQL             │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. First LLM Call: Analyze prompt and generate SQL             │
│    Input:                                                        │
│    - System: Full schema metadata with business descriptions    │
│      Example: "Table: students                                  │
│                Business Name: Students Table                    │
│                Columns: id, name, enroll_date..."               │
│    - User: "How many students enrolled after 2020?"            │
│    Output:                                                       │
│    - LLM generates SQL:                                         │
│      execute_query(sql_query="SELECT COUNT(*) FROM students    │
│                     WHERE EXTRACT(YEAR FROM enroll_date) >= 2020")│
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. Execute Function Tool: execute_query(sql_query=...)         │
│    - Security validation: Check SELECT only, no dangerous ops   │
│    - Execute generated SQL via SQLAlchemy                       │
│    - Auto-detect query type (COUNT vs LIST)                     │
│    - Returns: {"count": 42} or [{...}, {...}]                  │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. Second LLM Call: Generate natural language response         │
│    Input:                                                        │
│    - Previous conversation context                              │
│    - Tool result: {"count": 42}                                 │
│    Output:                                                       │
│    - assistant_text: "There are 42 students who enrolled       │
│                       after 2020."                              │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. Return to main.py:                                           │
│    - assistant_text: "There are 42 students..."                │
│    - tool_output: '{"count": 42}'                              │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 8. main.py: Display results in Streamlit                       │
│    - Shows AI response text                                     │
│    - Parses JSON and displays as DataFrame table               │
│    - Stores in session_state for reference                      │
└─────────────────────────────────────────────────────────────────┘
```

### Alternative Flow: List Query Example

```
User: "List students enrolled after 2020"
    ↓
LLM analyzes schema metadata and generates SQL:
    execute_query(sql_query="SELECT id, name, enroll_date FROM students 
                             WHERE EXTRACT(YEAR FROM enroll_date) >= 2020 
                             LIMIT 100")
    ↓
execute_query() validates and executes SQL
    ↓
Returns: [{"id": 1, "name": "Alice", "enroll_date": "2021-09-01"}, ...]
    ↓
LLM generates: "Here are the students who enrolled after 2020..."
    ↓
Display: Natural language + DataFrame table
```

### Fallback Flow (without Azure OpenAI)

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. main.py: Checks AZURE_OPENAI_API_KEY not set               │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. main.py calls: generate_sql_from_prompt(prompt)            │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. generate_sql_from_prompt: Error!                           │
│    - Raises ValueError: "Text-to-SQL requires Azure OpenAI"   │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. main.py: Display error message                              │
│    - Shows: "Please set AZURE_OPENAI_API_KEY"                 │
└─────────────────────────────────────────────────────────────────┘
```

## Detailed Component Explanation

### 1. **main.py** - Streamlit UI Layer

**Responsibilities**: 
- Provides web interface for user interaction
- Receives natural language prompts
- Routes requests to appropriate backend functions
- Displays results in user-friendly format

**Key Functions**:
- Receives user input via `st.text_input()`
- Calls `run_function_tool_flow(prompt)` for main workflow
- Parses JSON results and displays as DataFrames
- Handles two result types:
  - **Statistics** (dict): `{"count": 42}` → displayed as single-row table
  - **Student details** (list): `[{id, name, date}, ...]` → displayed as multi-row table

### 2. **query_sql.py: run_function_tool_flow()** - Orchestrator

**Responsibilities**:
- Acts as the main orchestrator of the LLM-based workflow
- Manages Azure OpenAI client and function calling
- Coordinates between LLM and database functions
- Generates natural language responses

**Detailed Workflow**:

1. **Setup Phase**:
   - Creates Azure OpenAI client with credentials
   - Calls `get_schema_metadata()` to retrieve ALL table metadata
   - Calls `format_schema_metadata_for_llm()` to format with business descriptions
   - Defines function tool specification: `execute_query()` (JSON schema)

2. **First LLM Interaction**:
   - Sends prompt with:
     - System context: "You are a SQL expert assistant..."
     - Full schema metadata with business names and descriptions
     - Guidelines for SQL generation
   - LLM analyzes user intent and schema metadata
   - LLM generates appropriate SQL SELECT query
   - Returns `tool_calls` with `sql_query` parameter

3. **Function Execution Phase**:
   - Parses `tool_calls` to get SQL query string
   - Logs generated SQL for debugging: `[Generated SQL] SELECT ...`
   - Calls `execute_query(user_prompt, sql_query)`
   - SQL is validated (security checks)
   - Query is executed via SQLAlchemy
   - Collects JSON result (auto-detects COUNT vs LIST format)

4. **Second LLM Interaction**:
   - Sends conversation history + tool results back to LLM
   - LLM generates human-friendly explanation
   - Returns final assistant text

5. **Return Phase**:
   - Returns tuple: `(assistant_text, tool_output)`
   - Both values are used by main.py for display

**Return Values**:
- `assistant_text` (str): Natural language explanation from LLM
- `tool_output` (str|None): Raw JSON from function tool

### 3. **query_sql.py: Function Tools** - Database Access Layer

#### 3a. **execute_query()** - Dynamic SQL Execution Tool

**Purpose**: Execute LLM-generated SQL queries with security validation

**Parameters**:
- `user_prompt` (str): Original user question for context
- `sql_query` (str): SQL SELECT query generated by LLM

**Security Features**:
- Only allows SELECT queries
- Blocks dangerous keywords: INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE
- Prevents SQL injection via single statement enforcement
- No multiple queries allowed (checks for semicolons)

**Return Format** (auto-detected):

For COUNT queries:
```json
{"count": 42}
```

For LIST queries:
```json
[
  {"id": 1, "name": "Alice", "enroll_date": "2021-09-01"},
  {"id": 2, "name": "Bob", "enroll_date": "2022-01-15"}
]
```

For errors:
```json
{"error": "Query execution failed: ..."}
```

### 4. **Schema Metadata Functions**

#### 4a. **get_schema_metadata()**

**Purpose**: Query schema_metadata table for business descriptions

**Parameters**:
- `table_name` (str, optional): Filter by specific table, or None for all tables

**Returns**: List of metadata dictionaries with:
- table_name, column_name
- business_name, business_description
- data_type, is_primary_key, is_foreign_key
- foreign_key_reference, sample_values

#### 4b. **format_schema_metadata_for_llm()**

**Purpose**: Format metadata into readable text for LLM context

**Output Format**:
```
Table: students
Business Name: Students Table
Description: Stores all student basic information...
Columns:
  - id (INTEGER) [PRIMARY KEY]
    Business Name: Student ID
    Description: Unique identifier... (Examples: ["1", "2", "3"])
  - name (VARCHAR)
    Business Name: Student Name
    Description: Full name of the student
```

## Key Design Principles

### 1. **Metadata-Driven Schema Understanding**
- Central `schema_metadata` table stores business descriptions
- LLM receives rich context: table purposes, column meanings, sample values
- Bridges gap between technical column names and business terminology
- Supports multi-language: users can query in natural language, LLM maps to technical schema

### 2. **LLM-Generated SQL**
- No hardcoded SQL patterns or predefined function parameters
- LLM dynamically generates SQL based on user intent and schema metadata
- Single universal function tool: `execute_query()`
- Maximum flexibility: handles any SELECT query structure

### 3. **Security-First Design**
- Multi-layer SQL validation before execution
- Whitelist approach: only SELECT allowed
- Blacklist dangerous operations: INSERT, UPDATE, DELETE, DROP, etc.
- Single statement enforcement prevents injection attacks

### 4. **Two-Phase LLM Interaction**
- **Phase 1**: Schema analysis + SQL generation → Function call
- **Phase 2**: Result interpretation → Natural language generation
- This approach ensures both accuracy and user-friendliness

## Technical Details

### Database Abstraction
- Supports both PostgreSQL and SQLite
- Automatic dialect detection via `IS_SQLITE` flag
- Helper functions handle SQL differences:
  - PostgreSQL: `EXTRACT(YEAR FROM date)`
  - SQLite: String date comparison

### Security Features
- Multi-layer SQL validation in `execute_query()`:
  1. Query type check (must start with SELECT)
  2. Dangerous keyword detection
  3. Multiple statement prevention
- Read-only operations enforced
- Parameterized queries via SQLAlchemy `text()` where applicable

### Error Handling
- Graceful fallback when Azure OpenAI is not configured
- Clear error messages guide users to correct setup
- Session state preserves last successful results

## Example Dialog Flows

### Example 1: Count Query

**User**: "How many students enrolled after 2020?"

**System Processing**:
1. main.py receives: `"How many students enrolled after 2020?"`
2. run_function_tool_flow() starts
3. Queries schema_metadata, formats with business descriptions
4. LLM (1st call) analyzes schema and user intent: "This is a COUNT query on students table"
5. LLM generates SQL: `execute_query(sql_query="SELECT COUNT(*) FROM students WHERE EXTRACT(YEAR FROM enroll_date) >= 2020")`
6. execute_query() validates and executes:
   - Security check: ✓ SELECT only
   - Runs query via SQLAlchemy
   - Detects COUNT query type
7. Returns: `{"count": 42}`
8. LLM (2nd call) generates: "There are 42 students who enrolled after 2020."
9. UI displays:
   - 🤖 AI Response: "There are 42 students who enrolled after 2020."
   - 📊 Query Results: Table showing `count: 42`
   - 🔍 Debug: `[Generated SQL] SELECT COUNT(*) FROM students WHERE EXTRACT(YEAR FROM enroll_date) >= 2020`

### Example 2: List Query

**User**: "Show me students enrolled in 2023"

**System Processing**:
1. main.py receives: `"Show me students enrolled in 2023"`
2. run_function_tool_flow() starts
3. Queries schema_metadata with business descriptions
4. LLM (1st call) analyzes: "This is a LIST query with year filter"
5. LLM generates SQL: `execute_query(sql_query="SELECT id, name, enroll_date FROM students WHERE EXTRACT(YEAR FROM enroll_date) >= 2023 ORDER BY enroll_date LIMIT 100")`
6. execute_query() validates and executes:
   - Security check: ✓ SELECT only, no dangerous keywords
   - Runs query, gets 15 rows
   - Detects LIST query type (not COUNT)
7. Returns: `[{"id": 10, "name": "Charlie", "enroll_date": "2023-01-15"}, ...]`
8. LLM (2nd call) generates: "Here are the students who enrolled in 2023. I found 15 students..."
9. UI displays:
   - 🤖 AI Response: Natural language summary
   - 📊 Query Results: Interactive DataFrame with 15 rows

### Example 3: Complex Query

**User**: "How many active students enrolled before 2022?"

**System Processing**:
1. LLM analyzes schema_metadata: finds `is_active` column with boolean type
2. LLM generates SQL with multiple conditions:
   ```sql
   SELECT COUNT(*) FROM students 
   WHERE EXTRACT(YEAR FROM enroll_date) < 2022 
   AND is_active = true
   ```
3. execute_query() validates and executes
4. Returns contextual response with count

## Advantages of This Architecture

### ✅ **User Experience**
- Natural language input (no SQL knowledge required)
- Conversational AI responses
- Visual data tables
- Handles variations in phrasing automatically
- Business terminology understanding via metadata

### ✅ **Developer Experience**
- Easy to extend: just add new tables to schema_metadata
- LLM handles SQL generation dynamically
- No need to create new function tools for each table
- Type-safe with Python type hints
- Single point of SQL execution and validation

### ✅ **Scalability**
- Add new tables: just insert metadata, no code changes
- Add new columns: update metadata only
- Support complex queries without predefined patterns
- LLM adapts to schema changes automatically
- Multi-table joins possible (just describe relationships in metadata)

### ✅ **Maintainability**
- No regex patterns to maintain
- No hardcoded SQL (only LLM-generated)
- Self-documenting via schema_metadata table
- Comprehensive security validation in one place
- Clear separation: metadata → LLM → SQL → results

### ✅ **Security**
- Centralized SQL validation
- Multiple security layers
- Read-only by design
- Injection attack prevention
- Audit trail via SQL logging

## Tech Stack

- **Frontend**: Streamlit
- **AI**: Azure OpenAI (GPT-4o) with Function Calling
- **Database**: PostgreSQL / SQLite
- **ORM**: SQLAlchemy
- **Language**: Python 3.10+
