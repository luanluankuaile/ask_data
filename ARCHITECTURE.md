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
│    - Prepares function tool definitions:                        │
│      • count_students() - for COUNT queries                     │
│      • query_students() - for LIST queries                      │
│    - Gets table schema from database                            │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. First LLM Call: Analyze prompt and select function          │
│    Input:                                                        │
│    - System: "You have count_students and query_students..."   │
│    - User: "How many students enrolled after 2020?"            │
│    Output:                                                       │
│    - LLM decides: call count_students(enroll_after_year=2020)  │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. Execute Function Tool: count_students(enroll_after_year=2020)│
│    - Builds SQL: SELECT COUNT(*) FROM students                 │
│                  WHERE EXTRACT(YEAR FROM enroll_date) >= 2020  │
│    - Executes query via SQLAlchemy                              │
│    - Returns: {"count": 42}                                     │
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
LLM selects: query_students(enroll_after_year=2020, limit=100)
    ↓
Executes SQL: SELECT id, name, enroll_date FROM students 
              WHERE EXTRACT(YEAR FROM enroll_date) >= 2020 
              ORDER BY enroll_date LIMIT 100
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
   - Retrieves table schema from database
   - Defines function tool specifications (JSON schema)

2. **First LLM Interaction**:
   - Sends prompt with system context and available functions
   - LLM analyzes user intent
   - LLM selects appropriate function and parameters
   - Returns `tool_calls` object

3. **Function Execution Phase**:
   - Parses `tool_calls` to get function name and arguments
   - Routes to either `count_students()` or `query_students()`
   - Executes database query
   - Collects JSON result

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

#### 3a. **count_students()** - COUNT Query Tool

**Purpose**: Returns statistical counts matching criteria

**Parameters**:
- `enroll_after_year` (int, optional): Filter ≥ year
- `enroll_before_year` (int, optional): Filter < year  
- `is_active` (bool, optional): Filter by active status

**SQL Generated**:
```sql
SELECT COUNT(*) as count FROM students 
WHERE EXTRACT(YEAR FROM enroll_date) >= :year
```

**Return Format**:
```json
{"count": 42}
```

#### 3b. **query_students()** - LIST Query Tool

**Purpose**: Returns detailed student records

**Parameters**:
- `enroll_after_year` (int, optional): Filter ≥ year
- `is_active` (bool, optional): Filter by active status
- `limit` (int, default=100): Max rows to return

**SQL Generated**:
```sql
SELECT id, name, enroll_date FROM students 
WHERE EXTRACT(YEAR FROM enroll_date) >= :year 
ORDER BY enroll_date 
LIMIT :limit
```

**Return Format**:
```json
[
  {"id": 1, "name": "Alice", "enroll_date": "2021-09-01"},
  {"id": 2, "name": "Bob", "enroll_date": "2022-01-15"}
]
```

### 4. **Helper Functions**

- `_add_year_filter()`: Builds year-based WHERE clauses (handles SQLite vs PostgreSQL differences)
- `_check_column_exists()`: Checks if column exists before filtering
- `_get_table_schema_description()`: Retrieves table schema for LLM context
- `_build_select_query()`: Dynamic SQL builder (currently unused, available for future enhancements)

## Key Design Principles

### 1. **LLM-Driven Intelligence**
- No hardcoded SQL patterns or regex matching
- LLM understands user intent naturally
- Automatically selects appropriate function tool
- Generates contextual, human-friendly responses

### 2. **Function Calling Architecture**
- Two specialized function tools:
  - `count_students()`: For statistical queries
  - `query_students()`: For detailed data retrieval
- LLM automatically chooses the right tool based on question type
- Clear separation between query logic and presentation

### 3. **Two-Phase LLM Interaction**
- **Phase 1**: Intent analysis → Function selection
- **Phase 2**: Result interpretation → Natural language generation
- This approach ensures both accuracy and user-friendliness

### 4. **Flexible Result Display**
- Statistics (count): Displayed as single-value metrics
- Details (list): Displayed as interactive DataFrames
- Always shows both AI explanation and raw data

## Technical Details

### Database Abstraction
- Supports both PostgreSQL and SQLite
- Automatic dialect detection via `IS_SQLITE` flag
- Helper functions handle SQL differences:
  - PostgreSQL: `EXTRACT(YEAR FROM date)`
  - SQLite: String date comparison

### Security Features
- All function tools use parameterized queries (SQLAlchemy `text()`)
- SQL injection protection via parameter binding
- Read-only operations enforced (SELECT only)

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
3. LLM (1st call) analyzes intent: "This is a COUNT query"
4. LLM decides: `count_students(enroll_after_year=2020)`
5. count_students() executes:
   ```sql
   SELECT COUNT(*) as count FROM students 
   WHERE EXTRACT(YEAR FROM enroll_date) >= 2020
   ```
6. Returns: `{"count": 42}`
7. LLM (2nd call) generates: "There are 42 students who enrolled after 2020."
8. UI displays:
   - 🤖 AI Response: "There are 42 students who enrolled after 2020."
   - 📊 Query Results: Table showing `count: 42`

### Example 2: List Query

**User**: "Show me students enrolled in 2023"

**System Processing**:
1. main.py receives: `"Show me students enrolled in 2023"`
2. run_function_tool_flow() starts
3. LLM (1st call) analyzes: "This is a LIST query with year filter"
4. LLM decides: `query_students(enroll_after_year=2023, limit=100)`
5. query_students() executes:
   ```sql
   SELECT id, name, enroll_date FROM students 
   WHERE EXTRACT(YEAR FROM enroll_date) >= 2023 
   ORDER BY enroll_date LIMIT 100
   ```
6. Returns: `[{"id": 10, "name": "Charlie", "enroll_date": "2023-01-15"}, ...]`
7. LLM (2nd call) generates: "Here are the students who enrolled in 2023. I found 15 students..."
8. UI displays:
   - 🤖 AI Response: Natural language summary
   - 📊 Query Results: Interactive DataFrame with 15 rows

### Example 3: Complex Query

**User**: "How many active students enrolled before 2022?"

**System Processing**:
1. LLM analyzes: "COUNT query with TWO filters"
2. LLM decides: `count_students(enroll_before_year=2022, is_active=True)`
3. Executes with compound WHERE clause
4. Returns contextual response

## Advantages of This Architecture

### ✅ **User Experience**
- Natural language input (no SQL knowledge required)
- Conversational AI responses
- Visual data tables
- Handles variations in phrasing automatically

### ✅ **Developer Experience**
- Easy to add new function tools
- LLM handles parameter extraction
- Clear separation of concerns
- Type-safe with Python type hints

### ✅ **Scalability**
- Can add more tables by creating new function tools
- Schema changes automatically reflected via `_get_table_schema_description()`
- LLM adapts to new functions without code changes

### ✅ **Maintainability**
- No regex patterns to maintain
- No hardcoded SQL strings (except in function tools)
- Self-documenting via function docstrings
- Comprehensive error handling

## Tech Stack

- **Frontend**: Streamlit
- **AI**: Azure OpenAI (GPT-4o) with Function Calling
- **Database**: PostgreSQL / SQLite
- **ORM**: SQLAlchemy
- **Language**: Python 3.10+
