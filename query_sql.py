from langchain_community.llms import AzureOpenAI
from langchain_experimental.sql import SQLDatabaseChain
from langchain.sql_database import SQLDatabase
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text
import json
import argparse
import re

load_dotenv()

# Read DATABASE_URI from environment; fall back to a local sqlite file for testing
DATABASE_URI = os.environ.get("DATABASE_URI")
USE_SQLITE_FALLBACK = False
# Allow an explicit opt-in to sqlite fallback for local/dev use
ALLOW_SQLITE_FALLBACK = os.environ.get("ALLOW_SQLITE_FALLBACK", "0") == "1"
if not DATABASE_URI:
    if ALLOW_SQLITE_FALLBACK:
        # explicit opt-in: use file-backed sqlite for local testing
        DATABASE_URI = "sqlite:///./local_test.db"
        USE_SQLITE_FALLBACK = True
        print("Warning: DATABASE_URI not set. Using sqlite fallback because ALLOW_SQLITE_FALLBACK=1.")
    else:
        print("ERROR: DATABASE_URI is not set. To use Postgres set the env var DATABASE_URI, e.g.:")
        print("  export DATABASE_URI=\"postgresql://postgres:admin@localhost:5432/mydb\"")
        print("If you are developing locally and want to allow the sqlite fallback, set:\n  export ALLOW_SQLITE_FALLBACK=1")
        raise SystemExit(1)

# Initialize DB wrapper (lazy / best-effort). Wrap in try/except so failures don't stop simple SQL runs.
db = None
try:
    db = SQLDatabase.from_uri(DATABASE_URI)
except Exception as e:
    print(f"Warning: SQLDatabase.from_uri failed (this is non-fatal). DB URI: {DATABASE_URI}. Error: {e}")

if USE_SQLITE_FALLBACK:
    engine = create_engine(DATABASE_URI)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY, name TEXT);"))
        # Ensure enroll_date column exists; if not, add it
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info('students');")).fetchall()]
        if 'enroll_date' not in cols:
            conn.execute(text("ALTER TABLE students ADD COLUMN enroll_date INTEGER DEFAULT 0;"))

        res = conn.execute(text("SELECT COUNT(*) as c FROM students;"))
        count = res.fetchone()[0]


# Azure OpenAI Configuration
AZURE_KEY = os.environ.get("AZURE_OPENAI_API_KEY")
AZURE_API_VERSION = os.environ.get("OPENAI_API_VERSION", "2025-04-01-preview")
AZURE_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", os.environ.get("AZURE_OPENAI_API_ENDPOINT", ""))
DEFAULT_MODEL = os.environ.get("MODEL", "gpt-4o")

# Database helpers
IS_SQLITE = DATABASE_URI.startswith("sqlite")


def _call_llm_with_fallback(client, messages, model=None, tools=None, tool_choice=None):
    """Call an LLM client and tolerate different client APIs.

    Tries OpenAI-style `.chat.completions.create(...)` first. If that
    attribute doesn't exist (e.g. langchain-style LLMs), falls back to
    calling the client with a single concatenated prompt and returns an
    object with a compatible minimal interface used below.
    """
    # Try OpenAI-like API first
    try:
        return client.chat.completions.create(model=model, messages=messages, tools=tools, tool_choice=tool_choice)
    except AttributeError:
        # LangChain or other client style: convert messages into a plain prompt
        prompt_text = "\n".join([f"{m.get('role','user').upper()}: {m.get('content','')}" for m in messages])
        try:
            # Some LLM wrappers return a string, others return an object with .text
            raw = client(prompt_text)
            if isinstance(raw, str):
                text_out = raw
            else:
                text_out = getattr(raw, 'text', str(raw))
        except Exception as e:
            raise RuntimeError(
                "LLM client does not support OpenAI-style chat and is not callable. "
                "Install a compatible OpenAI client or use the OpenAI Azure client, or unset AZURE_OPENAI_API_KEY to use the local fallback. "
                f"(inner error: {e})"
            )

        # Build a minimal response object compatible with the OpenAI-style access used below
        class _Msg:
            def __init__(self, content):
                self.content = content

        class _Choice:
            def __init__(self, message):
                self.message = message

        class _Resp:
            def __init__(self, choice):
                self.choices = [choice]

        return _Resp(_Choice(_Msg(text_out)))

# Choose appropriate SQL expression for filtering by year depending on DB dialect
YEAR_FILTER_EXPR = "enroll_date >= 2020" if IS_SQLITE else "EXTRACT(YEAR FROM enroll_date) >= 2020"


def execute_sql(sql: str, params: dict | None = None):
    """Execute a read-only SQL query and return (columns, rows).

    `params` is a dict passed to SQLAlchemy `text()` for safe parameterization.
    """
    engine = create_engine(DATABASE_URI)
    with engine.connect() as conn:
        stmt = text(sql)
        res = conn.execute(stmt, params or {})
        try:
            cols = res.keys()
        except Exception:
            cols = []
        rows = res.fetchall()
    return list(cols), rows


# --- Helper functions ---
def _add_year_filter(clauses: list, params: dict, year: int, param_name: str, operator: str = ">="):
    """Add year filter clause based on database type."""
    if IS_SQLITE:
        clauses.append(f"enroll_date {operator} :{param_name}")
    else:
        clauses.append(f"EXTRACT(YEAR FROM enroll_date) {operator} :{param_name}")
    params[param_name] = year

def _check_column_exists(conn, column_name: str, table_name: str = 'students') -> bool:
    """Check if a column exists in the table."""
    if IS_SQLITE:
        return False  # Skip check for sqlite
    try:
        col_res = [r[0] for r in conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = :t;"),
            {"t": table_name}
        ).fetchall()]
        return column_name in col_res
    except Exception:
        return False

def _get_table_schema_description(table_name: str) -> str:
    """Get table schema as formatted string."""
    schema = []
    try:
        engine = create_engine(DATABASE_URI)
        with engine.connect() as conn:
            if IS_SQLITE:
                res = conn.execute(text(f"PRAGMA table_info('{table_name}');")).fetchall()
                schema = [(r[1], r[2]) for r in res]
            else:
                res = conn.execute(
                    text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = :t;"),
                    {"t": table_name}
                ).fetchall()
                schema = [(r[0], r[1]) for r in res]
    except Exception:
        pass
    
    return '\n'.join([f"- {c}: {t}" for c, t in schema]) if schema else "(schema unavailable)"

def _build_select_query(table: str, columns: list[str] = None, where_clauses: list[str] = None, 
                       params: dict = None, order_by: str = None, limit: int = None) -> tuple[str, dict]:
    """Build a SELECT SQL query dynamically.
    
    Args:
        table: Table name
        columns: List of column names to select (default: all columns)
        where_clauses: List of WHERE conditions
        params: Dictionary of parameters for parameterized query
        order_by: ORDER BY clause (e.g., "enroll_date DESC")
        limit: LIMIT value
    
    Returns:
        Tuple of (sql_string, params_dict)
    """
    params = params or {}
    
    # SELECT clause
    select_cols = ', '.join(columns) if columns else '*'
    sql_parts = [f"SELECT {select_cols} FROM {table}"]
    
    # WHERE clause
    if where_clauses:
        sql_parts.append(f"WHERE {' AND '.join(where_clauses)}")
    
    # ORDER BY clause
    if order_by:
        sql_parts.append(f"ORDER BY {order_by}")
    
    # LIMIT clause
    if limit is not None:
        sql_parts.append(f"LIMIT {limit}")
    
    return ' '.join(sql_parts), params

# --- Function-tool integration: define query functions that the LLM can call ---
def count_students(enroll_after_year: int = None, enroll_before_year: int = None, is_active: bool = None):
    """Function tool: Count students matching the criteria.
    
    This function is exposed as a tool to the LLM for COUNT queries.
    Use this when the user asks "how many", "count", "total number", etc.

    Parameters:
      - enroll_after_year: optional - count students enrolled in or after this year
      - enroll_before_year: optional - count students enrolled before this year
      - is_active: optional boolean to filter active students (if column exists)
      
    Returns: JSON string with count result
    """
    engine = create_engine(DATABASE_URI)
    with engine.connect() as conn:
        clauses = []
        params = {}
        
        if enroll_after_year is not None:
            _add_year_filter(clauses, params, enroll_after_year, "year_after", ">=")
        
        if enroll_before_year is not None:
            _add_year_filter(clauses, params, enroll_before_year, "year_before", "<")

        if is_active is not None and _check_column_exists(conn, 'is_active'):
            clauses.append("is_active = :is_active")
            params['is_active'] = is_active

        where_clause = " AND ".join(clauses) if clauses else "1=1"
        sql = text(f"SELECT COUNT(*) as count FROM students WHERE {where_clause};")
        result = conn.execute(sql, params).fetchone()
        return json.dumps({"count": result[0]}, ensure_ascii=False)


def query_students(enroll_after_year: int = None, is_active: bool = None, limit: int = 100):
    """Function tool: Query students from the database and return JSON results.
    
    This function is exposed as a tool to the LLM for LIST queries.
    Use this when the user asks to "list", "show", "get details", etc.

    Parameters:
      - enroll_after_year: optional - include students enrolled in or after this year
      - is_active: optional boolean to filter active students (if column exists)
      - limit: maximum number of rows to return
      
    Returns: JSON string of list of student objects (consumed by LLM to generate natural language response)
    """
    engine = create_engine(DATABASE_URI)
    with engine.connect() as conn:
        clauses = []
        params = {}
        
        if enroll_after_year is not None:
            _add_year_filter(clauses, params, enroll_after_year, "year", ">=")

        if is_active is not None and _check_column_exists(conn, 'is_active'):
            clauses.append("is_active = :is_active")
            params['is_active'] = is_active

        where_clause = " AND ".join(clauses) if clauses else "1=1"
        sql = text(f"SELECT id, name, enroll_date FROM students WHERE {where_clause} ORDER BY enroll_date LIMIT :limit;")
        params['limit'] = limit
        rows = conn.execute(sql, params).fetchall()
        
        result = [{
            'id': r[0],
            'name': r[1],
            'enroll_date': r[2].isoformat() if hasattr(r[2], 'isoformat') else r[2]
        } for r in rows]
        
        return json.dumps(result, ensure_ascii=False)


def run_function_tool_flow(prompt: str, model: str | None = None):
    """Main workflow function: accepts NL prompt, uses function tool + NL generation to produce results.
    
    This is the core method called by main.py's Streamlit interface.
    
    Flow:
    1. Receives natural language prompt from main.py
    2. Uses LLM with function calling capability to invoke query_students
    3. query_students executes SQL query and returns JSON data
    4. LLM generates natural language response based on query results
    5. Returns (assistant_text, tool_output) to main.py for display

    Returns a tuple: (assistant_text: str, tool_response_json: str|None)
    - assistant_text: Natural language response explaining the results
    - tool_response_json: Raw JSON output from query_students function (or None if no function called)
    """
    if not AZURE_KEY:
        raise RuntimeError("AZURE_OPENAI_API_KEY is not set; cannot run LLM function-tool flow")

    # Prepare client
    try:
        from openai import AzureOpenAI as OpenAIClient
    except Exception:
        OpenAIClient = AzureOpenAI

    client = OpenAIClient(
        api_key=AZURE_KEY,
        api_version=AZURE_API_VERSION,
        azure_endpoint=AZURE_ENDPOINT,
    )

    tools = [
        {
            "type": "function",
            "function": {
                "name": "count_students",
                "description": "Count the number of students matching the criteria. Use this for 'how many', 'count', 'total number' queries.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "enroll_after_year": {"type": "integer", "description": "Filter students enrolled in or after this year"},
                        "enroll_before_year": {"type": "integer", "description": "Filter students enrolled before this year"},
                        "is_active": {"type": ["boolean", "null"], "description": "Filter by active status if column exists"}
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "query_students",
                "description": "Query and list students from the students table. Use this for 'list', 'show', 'get details' queries.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "enroll_after_year": {"type": "integer", "description": "Filter students enrolled in or after this year"},
                        "is_active": {"type": ["boolean", "null"], "description": "Filter by active status if column exists"},
                        "limit": {"type": "integer", "description": "Maximum number of rows to return", "default": 100}
                    },
                    "required": []
                }
            }
        }
    ]

    # Get table schema
    schema_lines = _get_table_schema_description('students')

    system = (
        "You are a SQL-aware assistant with access to a students database via function tools. "
        "Available table schema:\n" + schema_lines + "\n"
        "You have two function tools available:\n"
        "1. count_students: Use when user asks 'how many', 'count', 'total number' - returns just the count\n"
        "2. query_students: Use when user asks to 'list', 'show', 'get details' - returns student records\n"
        "Choose the appropriate function tool based on what the user is asking for."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt}
    ]

    model = model or DEFAULT_MODEL

    # first call
    response = _call_llm_with_fallback(client, messages, model=model, tools=tools, tool_choice="auto")
    response_message = response.choices[0].message

    tool_calls = getattr(response_message, 'tool_calls', None)
    if not tool_calls:
        # no function call; return assistant reply
        return response_message.content, None

    # Append the assistant message with tool_calls first (required by OpenAI API)
    messages.append({
        "role": "assistant",
        "content": response_message.content,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments
                }
            } for tc in tool_calls
        ]
    })

    # execute tool calls
    function_response = None
    for tool_call in tool_calls:
        func_obj = getattr(tool_call, 'function', None)
        if not func_obj:
            continue
            
        function_args = json.loads(func_obj.arguments)
        
        if func_obj.name == 'count_students':
            enroll_after_year = function_args.get('enroll_after_year', None)
            enroll_before_year = function_args.get('enroll_before_year', None)
            is_active = function_args.get('is_active', None)
            function_response = count_students(enroll_after_year=enroll_after_year, enroll_before_year=enroll_before_year, is_active=is_active)
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": "count_students",
                "content": function_response
            })
        elif func_obj.name == 'query_students':
            enroll_after_year = function_args.get('enroll_after_year', None)
            is_active = function_args.get('is_active', None)
            limit = function_args.get('limit', 100)
            function_response = query_students(enroll_after_year=enroll_after_year, is_active=is_active, limit=limit)
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": "query_students",
                "content": function_response
            })

    # final assistant call with tool outputs
    final_response = _call_llm_with_fallback(client, messages, model=model, tools=tools)
    final_text = final_response.choices[0].message.content
    # return final assistant text and the raw tool output (function_response)
    return final_text, function_response


def generate_sql_from_prompt(prompt: str, table: str = 'students', dialect: str = "postgresql") -> tuple[str, dict]:
    """Generate SQL from natural language using LLM text-to-SQL capability.

    This function uses Azure OpenAI's LLM to intelligently convert natural language
    to SQL queries. The LLM understands the table schema and generates appropriate
    SQL statements.

    Args:
        prompt: Natural language prompt (e.g., "Show me students enrolled after 2020")
        table: Target table name (default: 'students')
        dialect: SQL dialect (default: 'postgresql')

    Returns:
        Tuple of (sql_string, params_dict)
        
    The function validates the generated SQL and only allows single SELECT statements.
    
    Examples:
        >>> generate_sql_from_prompt("How many students enrolled in 2023?")
        ("SELECT COUNT(*) FROM students WHERE ...", {})
        
        >>> generate_sql_from_prompt("List top 10 students by enrollment date")
        ("SELECT * FROM students ORDER BY enroll_date LIMIT 10", {})
    """
    if not AZURE_KEY:
        raise ValueError(
            "Text-to-SQL requires Azure OpenAI LLM capability. "
            "Please set AZURE_OPENAI_API_KEY environment variable to enable intelligent natural language to SQL conversion. "
            f"Prompt received: '{prompt}'"
        )
    
    # Use LLM for intelligent text-to-SQL conversion
    try:
        # Get table schema for context
        schema_lines = _get_table_schema_description(table)

        # Enhanced system prompt for better text-to-SQL conversion
        system = (
            f"You are an expert SQL query generator. Your task is to convert natural language questions into valid SQL queries.\n\n"
            f"Target Database: {dialect}\n"
            f"Target Table: `{table}`\n\n"
            f"Table Schema:\n{schema_lines}\n\n"
            "Instructions:\n"
            "1. Generate ONLY a single SELECT SQL statement\n"
            "2. Use appropriate WHERE, ORDER BY, LIMIT clauses based on the question\n"
            "3. For date filtering, use appropriate functions for the database dialect\n"
            f"4. For {dialect}, use EXTRACT(YEAR FROM date_column) for year comparisons\n"
            "5. Return ONLY the SQL query without explanations, markdown, or semicolons\n"
            "6. If the question cannot be answered with a SELECT query, respond with: CANNOT_IMPLEMENT\n\n"
            "Examples:\n"
            f"Question: 'How many records?' -> SELECT COUNT(*) FROM {table}\n"
            f"Question: 'Show latest 10' -> SELECT * FROM {table} ORDER BY enroll_date DESC LIMIT 10\n"
            f"Question: 'Find entries from 2023' -> SELECT * FROM {table} WHERE EXTRACT(YEAR FROM enroll_date) = 2023"
        )
        
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Convert this question to SQL: {prompt}"}
        ]
        
        llm_client = AzureOpenAI(
            api_key=AZURE_KEY,
            api_version=AZURE_API_VERSION,
            azure_endpoint=AZURE_ENDPOINT
        )
        
        resp = _call_llm_with_fallback(llm_client, messages, model=DEFAULT_MODEL)
        sql_text = resp.choices[0].message.content.strip()
        
        # Check if LLM couldn't convert
        if "CANNOT_IMPLEMENT" in sql_text.upper():
            raise ValueError("The question cannot be converted to a SELECT query")
            
    except Exception as e:
        raise RuntimeError(f"LLM text-to-SQL conversion failed: {e}")
    
    # Validate generated SQL
    sql_clean = sql_text.strip().rstrip(";")
    upper = sql_clean.upper()
    
    # Security checks
    forbidden = ["INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "CREATE ", "TRUNCATE ", "GRANT ", "REVOKE "]
    if any(tok in upper for tok in forbidden):
        raise ValueError("Generated SQL contains forbidden write/DDL operations")
    
    # Disallow comments or multiple statements
    if ";" in sql_text or "--" in sql_text or "/*" in sql_text:
        raise ValueError("Generated SQL appears to contain multiple statements or comments")
    
    if not upper.strip().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    # Return SQL without parameters (LLM generates inline values)
    return sql_clean, {}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--nl', help='Natural language prompt to generate SQL for')
    args = parser.parse_args()
    if args.nl:
        try:
            sql, params = generate_sql_from_prompt(args.nl)
            print("Generated SQL:\n", sql)
            if params:
                print("Parameters:", params)
        except Exception as e:
            print("Failed to generate SQL:", e)