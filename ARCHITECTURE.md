# Architecture Documentation

## System Overview

This is a Natural Language to SQL application that uses LLM (Azure OpenAI or Deepseek) with function calling capability to intelligently query a multi-table database (students, classes, teachers, courses, course_enrollment). The system features **token-optimized fuzzy table matching** that identifies relevant tables before loading detailed schemas, reducing token consumption by 70-90% for large databases. Users input natural language questions through the FastAPI page or `POST /api/query`, and the system automatically generates SQL queries, executes them, and returns results in both natural language and table format.

### Supported LLM Providers

- **Azure OpenAI** (default): GPT-4o with function calling via Azure endpoint
- **Deepseek**: deepseek-chat model via Deepseek API endpoint

Both providers support the same workflow with automatic client fallback and response normalization.

## Method Call Relationships

### Main Flow (with Azure OpenAI and Token Optimization)

```
┌─────────────────────────────────────────────────────────────────┐
│ User Input: "How many students enrolled after 2020?"           │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 1. app.py: FastAPI receives prompt                            │
│    - User enters a question on the web page, or calls           │
│      POST /api/query                                            │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. app.py calls: run_function_tool_flow(prompt)               │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. run_function_tool_flow: Initialize LLM client               │
│    - Provider selection based on LLM_PROVIDER env var           │
│    - Azure: Creates AzureOpenAI client (official or langchain) │
│    - Deepseek: Creates DeepseekClient (HTTP-based wrapper)     │
│    STEP 1: Get table summaries (fuzzy matching)                │
│    - Calls get_table_summaries() → returns:                    │
│      [{'table_name': 'students',                               │
│        'business_name': 'Students Table',                      │
│        'business_description': 'Stores student info...'},      │
│       {'table_name': 'weather', ...},                          │
│       {'table_name': 'teacher', ...}]                          │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. First LLM Call (_call_llm_with_fallback): Table Identification│
│    STEP 2: Fuzzy match relevant tables                         │
│    Input:                                                        │
│    - System: "You are a database schema analyzer..."            │
│    - Available tables:                                           │
│      "- students: Students Table - Stores student info          │
│       - weather: Weather Records - Stores weather data          │
│       - teacher: Teachers Table - Stores faculty info"          │
│    - User: "How many students enrolled after 2020?"            │
│    Output:                                                       │
│    - LLM identifies: "students"                                 │
│    Log: "[Table Fuzzy Match] Found 1 relevant tables: students"│
│         "[Token Optimization] Loading 1/3 tables"               │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. Load Detailed Schema for Identified Tables Only             │
│    STEP 3: Query detailed metadata only for 'students'         │
│    - Calls get_schema_metadata('students')                     │
│    - Format with format_schema_metadata_for_llm()              │
│    - Result: Full column details ONLY for students table       │
│    - Token saved: ~67% (loaded 1/3 tables instead of all)      │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. Second LLM Call (_call_llm_with_fallback): Generate SQL    │
│    STEP 4: Analyze schema and generate SQL                     │
│    Input:                                                        │
│    - System: Full schema metadata (students table only)         │
│      "Table: students                                           │
│       Business Name: Students Table                             │
│       Columns: id, name, enroll_date, is_active..."            │
│    - User: "How many students enrolled after 2020?"            │
│    - Tools: [execute_query function definition]                │
│    Output:                                                       │
│    - LLM generates function call:                               │
│      execute_query(user_prompt="How many students...",         │
│                    sql_query="SELECT COUNT(*) FROM students    │
│                     WHERE EXTRACT(YEAR FROM enroll_date) >= 2020")│
│    Log: "[Generated SQL] SELECT COUNT(*) FROM students..."     │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. Execute Function Tool: execute_query(sql_query=...)         │
│    STEP 5: Validate and execute SQL                            │
│    - Security validation: Check SELECT only, no dangerous ops   │
│    - Execute generated SQL via SQLAlchemy                       │
│    - Auto-detect query type (COUNT vs LIST)                     │
│    - Returns: {"count": 42} or [{...}, {...}]                  │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 8. Third LLM Call (_call_llm_with_fallback): Generate Response│
│    STEP 6: Generate natural language response                  │
│    Input:                                                        │
│    - Previous conversation context                              │
│    - Tool result: {"count": 42}                                 │
│    Output:                                                       │
│    - assistant_text: "There are 42 students who enrolled       │
│                       after 2020."                              │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 9. Return to app.py:                                           │
│    - assistant_text: "There are 42 students..."                │
│    - tool_output: '{"count": 42}'                              │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 10. app.py: Return JSON and render the page                   │
│    - assistant_text and parsed result go back as JSON           │
│    - The page shows the reply and a results table               │
└─────────────────────────────────────────────────────────────────┘
```

### Alternative Flow: Weather Query Example

```
User: "How is the weather in Shanghai?"
    ↓
STEP 1: Get table summaries
    → Returns: students, weather, teacher
    ↓
STEP 2: LLM identifies relevant tables (fuzzy matching)
    → Analyzes: "weather in Shanghai" → semantic match
    → Identifies: weather table
    → Log: "[Table Fuzzy Match] Found 1 relevant tables: weather"
    → Log: "[Token Optimization] Loading 1/3 tables"
    ↓
STEP 3: Load detailed schema only for weather table
    → get_schema_metadata('weather')
    → Saves: ~67% tokens (loads 1 table instead of 3)
    ↓
STEP 4: LLM generates SQL with weather schema
    execute_query(sql_query="SELECT * FROM weather WHERE location = 'Shanghai'")
    ↓
STEP 5: execute_query() validates and executes SQL
    ↓
Returns: [{"id": 2, "location": "Shanghai", "date": "2025-12-01", "weather": "Cloudy"}, ...]
    ↓
STEP 6: LLM generates: "In Shanghai, the weather is Cloudy on 2025-12-01..."
    ↓
Display: Natural language + DataFrame table
```

### Alternative Flow: Teacher Query Example

```
User: "List professors with more than 15 years experience"
    ↓
STEP 1: Get table summaries
    ↓
STEP 2: LLM fuzzy match
    → Analyzes: "professors" + "experience" → teacher table
    → Identifies: teacher
    → Log: "[Table Fuzzy Match] Found 1 relevant tables: teacher"
    ↓
STEP 3: Load teacher table schema only
    ↓
STEP 4: LLM generates SQL
    execute_query(sql_query="SELECT * FROM teacher 
                             WHERE title = 'Professor' 
                             AND teach_years > 15 
                             LIMIT 100")
    ↓
Returns: List of professors with experience details
```

### Fallback Flow (without Azure OpenAI)

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. app.py: Checks AZURE_OPENAI_API_KEY not set               │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. app.py calls: generate_sql_from_prompt(prompt)            │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. generate_sql_from_prompt: Error!                           │
│    - Raises ValueError: "Text-to-SQL requires Azure OpenAI"   │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. app.py: Display error message                              │
│    - Shows: "Please set AZURE_OPENAI_API_KEY"                 │
└─────────────────────────────────────────────────────────────────┘
```

## Detailed Component Explanation

### 1. **app.py** - FastAPI Layer

**Responsibilities**: 
- Serves the web page and the query API
- Receives natural language prompts
- Routes requests to the query workflow
- Returns results as JSON for the page to render

**Key endpoints**:
- `GET /` serves `front_end/index.html`
- `POST /api/query` accepts `{ "prompt": "..." }` and calls `run_function_tool_flow(prompt)`
- Parses tool JSON before returning it
- Handles two result types:
  - **Statistics** (dict): `{"count": 42}` → displayed as a single-row table
  - **Student details** (list): `[{id, name, date}, ...]` → displayed as a multi-row table

### 2. **query_sql.py: run_function_tool_flow()** - Orchestrator

**Responsibilities**:
- Acts as the main orchestrator of the LLM-based workflow
- Implements three-phase token optimization strategy
- Manages Azure OpenAI client and function calling
- Coordinates between LLM and database functions
- Generates natural language responses

**Detailed Workflow with Token Optimization**:

1. **Setup Phase**:
   - Creates Azure OpenAI client with credentials

2. **Phase 1: Get Table Summaries (Fuzzy Matching Preparation)**:
   - Calls `get_table_summaries()` to retrieve:
     - table_name
     - business_name  
     - business_description
   - Returns lightweight summaries for ALL tables (no column details)
   - Example: `[{'table_name': 'students', 'business_name': 'Students Table', 'business_description': 'Stores student info...'}, ...]`

3. **Phase 2: LLM Table Identification (First LLM Call via _call_llm_with_fallback)**:
   - Builds identification prompt with table summaries
   - Sends to LLM with system role: "You are a database schema analyzer"
   - LLM performs semantic matching based on:
     - Direct mentions (e.g., "students" → students table)
     - Business concepts (e.g., "enrollment" → students, "weather" → weather)
     - Related tables for potential joins
   - LLM returns: comma-separated table names (e.g., "students, teacher")
   - System parses and validates identified tables
   - **Logs**: `[Table Fuzzy Match] Found N relevant tables: xxx`
   - **Logs**: `[Token Optimization] Loading N/M tables` 
   - **Fallback**: If no tables matched, loads all tables

4. **Phase 3: Load Detailed Schemas for Identified Tables Only**:
   - For each identified table:
     - Calls `get_schema_metadata(table_name)`
     - Retrieves full column-level metadata
   - Calls `format_schema_metadata_for_llm()` to format with business descriptions
   - **Token Savings**: 70-90% reduction for large schemas

5. **Phase 4: SQL Generation (Second LLM Call via _call_llm_with_fallback)**:
   - Sends prompt with:
     - System context: "You are a SQL expert assistant..."
     - Schema metadata (ONLY identified tables, not all tables)
     - Guidelines for SQL generation
     - Function tool definition: `execute_query(user_prompt, sql_query)`
   - LLM analyzes user intent and relevant schema metadata
   - LLM generates appropriate SQL SELECT query
   - Returns `tool_calls` with `sql_query` parameter
   - **Logs**: `[Generated SQL] SELECT ...`

6. **Phase 5: Function Execution**:
   - Parses `tool_calls` to get SQL query string
   - Calls `execute_query(user_prompt, sql_query)`
   - SQL is validated (security checks)
   - Query is executed via SQLAlchemy
   - Collects JSON result (auto-detects COUNT vs LIST format)

7. **Phase 6: Natural Language Response (Third LLM Call via _call_llm_with_fallback)**:
   - Sends conversation history + tool results back to LLM
   - LLM generates human-friendly explanation
   - Returns final assistant text

8. **Return Phase**:
   - Returns tuple: `(assistant_text, tool_output)`
   - Both values are used by app.py for display

**Return Values**:
- `assistant_text` (str): Natural language explanation from LLM
- `tool_output` (str|None): Raw JSON from function tool

**LLM Call Wrapper**:
- All LLM calls use `_call_llm_with_fallback(client, messages, model, tools, tool_choice)`
- Provides compatibility with different LLM client APIs
- Ensures consistent error handling across all phases

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

#### 4a. **get_table_summaries()**

**Purpose**: Get lightweight table summaries for fuzzy matching (Phase 1)

**Returns**: List of dicts with:
- table_name (str)
- business_name (str)
- business_description (str)

**SQL Query**:
```sql
SELECT table_name, business_name, business_description 
FROM schema_metadata 
WHERE column_name IS NULL  -- Table-level records only
ORDER BY table_name
```

**Usage**: First phase of token optimization - provides LLM with table options without loading all column details

#### 4b. **get_schema_metadata(table_name)**

**Purpose**: Query detailed schema metadata for specific tables (Phase 3)

**Parameters**:
- `table_name` (str, optional): Filter by specific table, or None for all tables

**Returns**: List of metadata dictionaries with:
- table_name, column_name (None for table-level)
- business_name, business_description
- data_type, is_primary_key, is_foreign_key
- foreign_key_reference, sample_values

**Usage**: After table identification, loads full column details only for relevant tables

#### 4c. **format_schema_metadata_for_llm()**

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

**Usage**: Converts metadata dictionaries into structured text for LLM prompt

## Key Design Principles

### 1. **Token-Optimized Fuzzy Table Matching**
- **Three-Phase Workflow**:
  - Phase 1: Get all table summaries (lightweight)
  - Phase 2: LLM identifies relevant tables via semantic matching
  - Phase 3: Load detailed schemas only for identified tables
- **Semantic Matching**: LLM understands business concepts
  - "enrollment" → students table
  - "weather" or "climate" → weather table
  - "professors" or "faculty" → teacher table
- **Token Savings**: 70-90% reduction for databases with 10+ tables
- **Fallback**: If no tables identified, loads all tables (safe default)

### 2. **Metadata-Driven Schema Understanding**
- Central `schema_metadata` table stores business descriptions
- **Two-level metadata**:
  - Table-level (column_name IS NULL): For fuzzy matching
  - Column-level: For SQL generation
- LLM receives rich context: table purposes, column meanings, sample values
- Bridges gap between technical column names and business terminology
- Supports multi-language: users can query in natural language, LLM maps to technical schema

### 3. **LLM-Generated SQL**
- No hardcoded SQL patterns or predefined function parameters
- LLM dynamically generates SQL based on user intent and schema metadata
- Single universal function tool: `execute_query(user_prompt, sql_query)`
- Maximum flexibility: handles any SELECT query structure
- All LLM calls unified through `_call_llm_with_fallback()` wrapper

### 4. **Security-First Design**
- Multi-layer SQL validation before execution
- Whitelist approach: only SELECT allowed
- Blacklist dangerous operations: INSERT, UPDATE, DELETE, DROP, etc.
- Single statement enforcement prevents injection attacks

### 5. **Three-Phase LLM Interaction**
- **Phase 1**: Table identification → Fuzzy matching (1st LLM call)
- **Phase 2**: Schema analysis + SQL generation → Function call (2nd LLM call)
- **Phase 3**: Result interpretation → Natural language generation (3rd LLM call)
- This approach ensures accuracy, token efficiency, and user-friendliness

## Technical Details

### Database Support
- Primary: PostgreSQL (recommended)
- Schema metadata stored in `schema_metadata` table
- Three main data tables:
  - `students`: Student enrollment and graduation data
  - `weather`: Weather observations by location and date
  - `teacher`: Faculty information with teaching experience

### LLM Integration
- **Client Wrapper**: `_call_llm_with_fallback(client, messages, model, tools, tool_choice)`
  - Primary: OpenAI-style API (`client.chat.completions.create()`)
  - Fallback: LangChain or callable LLM clients
  - Ensures compatibility across different LLM providers
- **Three LLM Calls per Query**:
  1. Table identification (fuzzy matching)
  2. SQL generation (with function calling)
  3. Natural language response generation

### Token Optimization Strategy
- **Baseline (no optimization)**: Load all 3 tables with all columns
- **With optimization**: Load 1-2 relevant tables only
- **Savings**: 
  - 3 tables → 1 table = ~67% token reduction
  - 10 tables → 2 tables = ~80% token reduction
  - 50 tables → 3 tables = ~94% token reduction

### Security Features
- Multi-layer SQL validation in `execute_query()`:
  1. Query type check (must start with SELECT)
  2. Dangerous keyword detection (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE)
  3. Multiple statement prevention (no semicolons except trailing)
- Read-only operations enforced
- Parameterized queries via SQLAlchemy `text()` where applicable

### Error Handling
- Graceful fallback when Azure OpenAI is not configured
- Clear error messages guide users to correct setup
- The page shows the latest response returned by `POST /api/query`

## Example Dialog Flows

### Example 1: Count Query with Token Optimization

**User**: "How many students enrolled after 2020?"

**System Processing**:
1. app.py receives: `"How many students enrolled after 2020?"`
2. run_function_tool_flow() starts
3. **Phase 1**: Get table summaries → `[students, weather, teacher]`
4. **Phase 2**: LLM identifies relevant tables
   - Prompt: "Available tables: students (student info), weather (weather data), teacher (faculty info)"
   - User question: "How many students enrolled after 2020?"
   - LLM analyzes: "This is about students"
   - LLM returns: "students"
   - Log: `[Table Fuzzy Match] Found 1 relevant tables: students`
   - Log: `[Token Optimization] Loading 1/3 tables`
5. **Phase 3**: Load detailed schema only for students table (saves 67% tokens)
6. **Phase 4**: LLM (2nd call) generates SQL: 
   ```sql
   SELECT COUNT(*) FROM students 
   WHERE EXTRACT(YEAR FROM enroll_date) >= 2020
   ```
   - Log: `[Generated SQL] SELECT COUNT(*) FROM students WHERE...`
7. execute_query() validates and executes:
   - Security check: ✓ SELECT only
   - Runs query via SQLAlchemy
   - Detects COUNT query type
   - Returns: `{"count": 42}`
8. **Phase 5**: LLM (3rd call) generates: "There are 42 students who enrolled after 2020."
9. UI displays:
   - 🤖 AI Response: "There are 42 students who enrolled after 2020."
   - 📊 Query Results: Table showing `count: 42`

### Example 2: Weather Query with Fuzzy Matching

**User**: "What's the weather like in Beijing?"

**System Processing**:
1. app.py receives: `"What's the weather like in Beijing?"`
2. **Phase 1**: Get table summaries → `[students, weather, teacher]`
3. **Phase 2**: LLM fuzzy match
   - Analyzes: "weather" keyword + "Beijing" location
   - Semantic match: weather table
   - LLM returns: "weather"
   - Log: `[Table Fuzzy Match] Found 1 relevant tables: weather`
   - Log: `[Token Optimization] Loading 1/3 tables`
4. **Phase 3**: Load weather table schema only
5. **Phase 4**: LLM generates SQL:
   ```sql
   SELECT * FROM weather WHERE location = 'Beijing'
   ```
6. execute_query() executes and returns:
   ```json
   [{"id": 1, "location": "Beijing", "date": "2025-12-01", "weather": "Sunny"},
    {"id": 4, "location": "Beijing", "date": "2025-12-02", "weather": "Snowy"}]
   ```
7. **Phase 5**: LLM generates: "In Beijing, the weather was Sunny on 2025-12-01 and Snowy on 2025-12-02."
8. UI displays natural language summary + weather records table

### Example 3: Teacher Query with Business Concept Matching

**User**: "List professors with over 15 years of experience"

**System Processing**:
1. **Phase 1**: Get summaries → `[students, weather, teacher]`
2. **Phase 2**: LLM semantic matching
   - Analyzes: "professors" (business concept) + "experience" (teaching_years)
   - Maps: "professors" → teacher table
   - LLM returns: "teacher"
   - Log: `[Table Fuzzy Match] Found 1 relevant tables: teacher`
3. **Phase 3**: Load teacher schema only
4. **Phase 4**: LLM generates:
   ```sql
   SELECT * FROM teacher 
   WHERE title = 'Professor' AND teach_years > 15 
   LIMIT 100
   ```
5. Returns list of professors with their courses and experience
6. Display: Natural language + teacher records table

### Example 4: Ambiguous Query with Fallback

**User**: "Show me all the data"

**System Processing**:
1. **Phase 1**: Get summaries
2. **Phase 2**: LLM identifies: (empty or unclear)
   - Log: `[Table Fuzzy Match] Found 0 relevant tables: (none)`
   - Log: `[Fallback] No tables matched, loading all 3 tables`
3. **Phase 3**: Load all tables as fallback (safe default)
4. Continue with SQL generation using all available schemas

## Advantages of This Architecture

### ✅ **Token Efficiency**
- **Fuzzy Table Matching**: Identifies relevant tables before loading schemas
- **70-90% Token Savings**: Only loads necessary table metadata
- **Scalable**: Handles databases with 50+ tables without token overflow
- **Smart Fallback**: Loads all tables if identification fails (safe default)

### ✅ **User Experience**
- Natural language input (no SQL knowledge required)
- Conversational AI responses
- Visual data tables
- Handles variations in phrasing automatically
- Business terminology understanding via metadata
- Multi-table support (students, weather, teacher)

### ✅ **Developer Experience**
- Easy to extend: just add new tables to schema_metadata
- LLM handles SQL generation dynamically
- No need to create new function tools for each table
- Type-safe with Python type hints
- Single point of SQL execution and validation
- Unified LLM calling pattern via `_call_llm_with_fallback()`

### ✅ **Scalability**
- Add new tables: just insert metadata, no code changes
- Add new columns: update metadata only
- Support complex queries without predefined patterns
- LLM adapts to schema changes automatically
- Multi-table joins possible (just describe relationships in metadata)
- Token optimization enables large-scale databases

### ✅ **Maintainability**
- No regex patterns to maintain
- No hardcoded SQL (only LLM-generated)
- Self-documenting via schema_metadata table
- Comprehensive security validation in one place
- Clear separation: summaries → identification → detailed schemas → SQL → results
- Consistent LLM client wrapper for all API calls

### ✅ **Security**
- Centralized SQL validation
- Multiple security layers
- Read-only by design
- Injection attack prevention
- Audit trail via SQL logging

## Tech Stack

- **API / UI**: FastAPI, with a static page at `/`
- **AI**: Azure OpenAI (GPT-4o) with Function Calling
- **Database**: PostgreSQL / SQLite
- **ORM**: SQLAlchemy
- **Language**: Python 3.10+
