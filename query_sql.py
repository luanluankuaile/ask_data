from langchain_community.llms import AzureOpenAI
from langchain.sql_database import SQLDatabase
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text
import json
from typing import Optional


load_dotenv()

# Read DATABASE_URI from environment
DATABASE_URI = os.environ.get("DATABASE_URI")
if not DATABASE_URI:
    print("ERROR: DATABASE_URI is not set. Please set the environment variable:")
    print("  export DATABASE_URI=\"postgresql://postgres:admin@localhost:5432/mydb\"")
    raise SystemExit(1)

# Initialize DB wrapper (lazy / best-effort). Wrap in try/except so failures don't stop simple SQL runs.
db = None
try:
    db = SQLDatabase.from_uri(DATABASE_URI)
except Exception as e:
    print(f"Warning: SQLDatabase.from_uri failed (this is non-fatal). DB URI: {DATABASE_URI}. Error: {e}")


# Azure OpenAI Configuration
AZURE_KEY = os.environ.get("AZURE_OPENAI_API_KEY")
AZURE_API_VERSION = os.environ.get("OPENAI_API_VERSION", "2025-04-01-preview")
AZURE_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT","https://ai-proxy.lab.epam.com")
DEFAULT_MODEL = os.environ.get("MODEL", "gpt-4o")

# Create a single shared engine instance
_engine = None

def get_engine():
    """Get or create the shared database engine instance.
    
    This ensures we reuse the same engine across all database operations
    instead of creating a new one each time.
    """
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URI, pool_pre_ping=True)
    return _engine


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



def execute_sql(sql: str, params: Optional[dict] = None):
    """Execute a read-only SQL query and return (columns, rows).

    `params` is a dict passed to SQLAlchemy `text()` for safe parameterization.
    """
    engine = get_engine()
    with engine.connect() as conn:
        stmt = text(sql)
        res = conn.execute(stmt, params or {})
        try:
            cols = res.keys()
        except Exception:
            cols = []
        rows = res.fetchall()
    return list(cols), rows


def get_all_table_names() -> list[str]:
    """Get all table names from schema_metadata.
    
    Returns:
        List of table names that have metadata
    """
    engine = get_engine()
    try:
        with engine.connect() as conn:
            sql = text("""
                SELECT DISTINCT table_name 
                FROM schema_metadata 
                WHERE column_name IS NULL
                ORDER BY table_name
            """)
            rows = conn.execute(sql).fetchall()
            return [r[0] for r in rows]
    except Exception as e:
        print(f"Warning: Failed to get table names from schema_metadata: {e}")
        return []


def get_table_summaries() -> list[dict]:
    """Get table names with their business descriptions for fuzzy matching.
    
    Returns:
        List of dicts with table_name, business_name, and business_description
    """
    engine = get_engine()
    try:
        with engine.connect() as conn:
            sql = text("""
                SELECT table_name, business_name, business_description 
                FROM schema_metadata 
                WHERE column_name IS NULL
                ORDER BY table_name
            """)
            rows = conn.execute(sql).fetchall()
            return [
                {
                    'table_name': r[0],
                    'business_name': r[1],
                    'business_description': r[2]
                }
                for r in rows
            ]
    except Exception as e:
        print(f"Warning: Failed to get table summaries from schema_metadata: {e}")
        return []


def get_schema_metadata(table_name: Optional[str] = None) -> list[dict]:
    """Query schema metadata table for business descriptions.
    
    Args:
        table_name: Optional table name to filter by. If None, returns all metadata.
    
    Returns:
        List of metadata dictionaries containing business descriptions
    """
    engine = get_engine()
    try:
        with engine.connect() as conn:
            if table_name:
                sql = text("""
                    SELECT table_name, column_name, business_name, business_description, 
                           data_type, is_primary_key, is_foreign_key, foreign_key_reference, sample_values
                    FROM schema_metadata 
                    WHERE table_name = :table_name
                    ORDER BY 
                        CASE WHEN column_name IS NULL THEN 0 ELSE 1 END,
                        column_name
                """)
                rows = conn.execute(sql, {"table_name": table_name}).fetchall()
            else:
                sql = text("""
                    SELECT table_name, column_name, business_name, business_description,
                           data_type, is_primary_key, is_foreign_key, foreign_key_reference, sample_values
                    FROM schema_metadata 
                    ORDER BY table_name, 
                        CASE WHEN column_name IS NULL THEN 0 ELSE 1 END,
                        column_name
                """)
                rows = conn.execute(sql).fetchall()
            
            return [{
                'table_name': r[0],
                'column_name': r[1],
                'business_name': r[2],
                'business_description': r[3],
                'data_type': r[4],
                'is_primary_key': r[5],
                'is_foreign_key': r[6],
                'foreign_key_reference': r[7],
                'sample_values': r[8]
            } for r in rows]
    except Exception as e:
        # If schema_metadata table doesn't exist, return empty list
        print(f"Warning: Failed to query schema_metadata table: {e}")
        return []


def format_schema_metadata_for_llm(metadata: list[dict]) -> str:
    """Format schema metadata into a readable string for LLM.
    
    Args:
        metadata: List of metadata dictionaries from get_schema_metadata()
    
    Returns:
        Formatted string with business descriptions
    """
    if not metadata:
        return "(No schema metadata available)"
    
    result = []
    current_table = None
    
    for item in metadata:
        # Table-level description
        if item['column_name'] is None:
            if current_table:
                result.append("")  # Empty line between tables
            current_table = item['table_name']
            result.append(f"Table: {item['table_name']}")
            result.append(f"Business Name: {item['business_name']}")
            result.append(f"Description: {item['business_description']}")
            result.append("Columns:")
        # Column-level description
        else:
            pk_marker = " [PRIMARY KEY]" if item['is_primary_key'] else ""
            fk_info = f" -> {item['foreign_key_reference']}" if item['is_foreign_key'] else ""
            sample_info = f" (Examples: {item['sample_values']})" if item['sample_values'] else ""
            
            result.append(f"  - {item['column_name']} ({item['data_type']}){pk_marker}{fk_info}")
            result.append(f"    Business Name: {item['business_name']}")
            result.append(f"    Description: {item['business_description']}{sample_info}")
    
    return '\n'.join(result)


def _get_table_schema_description(table_name: str) -> str:
    """Get table schema as formatted string (fallback method).
    
    This is used as a fallback when schema_metadata table is not available.
    """
    schema = []
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # Use PostgreSQL information_schema
            res = conn.execute(
                text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = :t;"),
                {"t": table_name}
            ).fetchall()
            schema = [(r[0], r[1]) for r in res]
    except Exception:
        pass
    
    return '\n'.join([f"- {c}: {t}" for c, t in schema]) if schema else "(schema unavailable)"

# --- Function-tool integration: define query functions that the LLM can call ---
def execute_query(user_prompt: str, sql_query: str):
    """Function tool: Execute a generated SQL query and return results.
    
    This function is exposed as a tool to the LLM. The LLM should:
    1. Analyze the user prompt and schema metadata
    2. Generate appropriate SQL query
    3. Call this function with the generated SQL

    Parameters:
      - user_prompt: The original user question for context
      - sql_query: The SQL SELECT query to execute (generated by LLM)
      
    Returns: JSON string with query results
    
    Security: Only SELECT queries are allowed. Query is validated before execution.
    """
    # Security validation
    sql_upper = sql_query.strip().upper()
    if not sql_upper.startswith('SELECT'):
        return json.dumps({"error": "Only SELECT queries are allowed"}, ensure_ascii=False)
    
    # Check for dangerous keywords
    forbidden = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE', 'TRUNCATE', 'GRANT', 'REVOKE']
    if any(keyword in sql_upper for keyword in forbidden):
        return json.dumps({"error": "Query contains forbidden operations"}, ensure_ascii=False)
    
    # Check for multiple statements
    if ';' in sql_query.strip().rstrip(';'):
        return json.dumps({"error": "Multiple statements not allowed"}, ensure_ascii=False)
    
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text(sql_query))
            
            # Check if it's a COUNT query
            if 'COUNT(*)' in sql_upper or 'COUNT(' in sql_upper:
                row = result.fetchone()
                return json.dumps({"count": row[0]}, ensure_ascii=False)
            
            # Otherwise, return rows
            columns = result.keys()
            rows = result.fetchall()
            
            # Convert to list of dicts
            data = []
            for row in rows:
                record = {}
                for i, col in enumerate(columns):
                    value = row[i]
                    # Handle date/datetime objects
                    if hasattr(value, 'isoformat'):
                        value = value.isoformat()
                    record[col] = value
                data.append(record)
            
            return json.dumps(data, ensure_ascii=False)
            
    except Exception as e:
        return json.dumps({"error": f"Query execution failed: {str(e)}"}, ensure_ascii=False)


def run_function_tool_flow(prompt: str, model: Optional[str] = None):
    """Main workflow function: accepts NL prompt, uses function tool + NL generation to produce results.
    
    This is the core method called by app.py's Streamlit interface.
    
    Flow:
    1. Receives natural language prompt from app.py
    2. First LLM call: Analyze prompt and identify relevant tables
    3. Query schema_metadata only for identified tables (token optimization)
    4. Second LLM call: Generate SQL based on relevant schema
    5. Execute SQL and return results

    Returns a tuple: (assistant_text: str, tool_response_json: str|None)
    - assistant_text: Natural language response explaining the results
    - tool_response_json: Raw JSON output from execute_query function (or None if no function called)
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

    model = model or DEFAULT_MODEL

    # Step 1: Get table summaries (names + business descriptions) for fuzzy matching
    table_summaries = get_table_summaries()
    
    if not table_summaries:
        # Fallback: schema_metadata table doesn't exist or is empty
        metadata = get_schema_metadata()
        if metadata:
            schema_info = format_schema_metadata_for_llm(metadata)
        else:
            schema_info = _get_table_schema_description('students')
    else:
        # Step 2: Use LLM to fuzzy match relevant tables based on prompt
        # Build table info string with business descriptions for better matching
        table_info_lines = []
        for t in table_summaries:
            table_info_lines.append(
                f"- {t['table_name']}: {t['business_name']} - {t['business_description']}"
            )
        table_info_str = "\n".join(table_info_lines)
        
        identification_prompt = (
            f"Available database tables with descriptions:\n{table_info_str}\n\n"
            f"User question: {prompt}\n\n"
            "Analyze the user's question and identify which tables are relevant or related to answer it. "
            "Consider:\n"
            "1. Direct mentions (e.g., 'students' → students table)\n"
            "2. Business concepts (e.g., 'enrollment' → students table, 'climate data' → weather table)\n"
            "3. Related tables that might be needed for joins\n\n"
            "Return ONLY the table names as a comma-separated list, nothing else.\n"
            "If unsure, include potentially relevant tables rather than exclude them.\n"
            "Example output: students, courses"
        )
        
        identification_messages = [
            {"role": "system", "content": "You are a database schema analyzer. Analyze user questions and identify relevant tables based on semantic meaning and business context. Return only table names."},
            {"role": "user", "content": identification_prompt}
        ]
        
        try:
            identification_response = _call_llm_with_fallback(client, identification_messages, model=model)
            identified_tables_str = identification_response.choices[0].message.content.strip()
            
            # Parse identified tables
            identified_tables = [t.strip() for t in identified_tables_str.split(',') if t.strip()]
            
            # Validate and filter to only existing tables
            all_table_names = [t['table_name'] for t in table_summaries]
            identified_tables = [t for t in identified_tables if t in all_table_names]
            
            # Log identified tables
            print(f"\n[Table Fuzzy Match] Found {len(identified_tables)} relevant tables: {', '.join(identified_tables) if identified_tables else '(none)'}")
            
            if not identified_tables:
                # If no tables identified, use all tables as fallback
                print(f"[Fallback] No tables matched, loading all {len(all_table_names)} tables\n")
                identified_tables = all_table_names
            else:
                print(f"[Token Optimization] Loading {len(identified_tables)}/{len(all_table_names)} tables\n")
                
        except Exception as e:
            print(f"Warning: Table identification failed: {e}. Using all tables as fallback.")
            identified_tables = [t['table_name'] for t in table_summaries]
        
        # Step 3: Get detailed schema metadata only for identified tables
        metadata = []
        for table in identified_tables:
            table_metadata = get_schema_metadata(table)
            metadata.extend(table_metadata)
        
        if metadata:
            schema_info = format_schema_metadata_for_llm(metadata)
        else:
            schema_info = _get_table_schema_description('students')

    # Step 4: Prepare tools for SQL generation
    tools = [
        {
            "type": "function",
            "function": {
                "name": "execute_query",
                "description": "Execute a SQL SELECT query against the database. Use this to answer user questions by generating appropriate SQL based on the schema metadata provided.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_prompt": {
                            "type": "string", 
                            "description": "The original user question for context"
                        },
                        "sql_query": {
                            "type": "string",
                            "description": "The SQL SELECT query to execute. Must be a valid SELECT statement. Use the schema metadata to determine correct table and column names. Examples: 'SELECT COUNT(*) FROM students WHERE enroll_date >= 2020' or 'SELECT id, name, enroll_date FROM students WHERE is_active = true LIMIT 10'"
                        }
                    },
                    "required": ["user_prompt", "sql_query"]
                }
            }
        }
    ]

    system = (
        "You are a SQL expert assistant. Your task is to:\n"
        "1. Analyze the user's question\n"
        "2. Use the schema metadata below to understand table and column names\n"
        "3. Generate a valid SQL SELECT query\n"
        "4. Call the execute_query function with your generated SQL\n\n"
        "Database Schema with Business Descriptions:\n"
        f"{schema_info}\n\n"
        "Important Guidelines:\n"
        "- Only generate SELECT queries (no INSERT/UPDATE/DELETE)\n"
        "- Use exact table and column names from the schema above\n"
        "- Use business descriptions to understand user intent and table relationships\n"
        "- Pay attention to foreign key relationships mentioned in descriptions for JOIN operations\n"
        "- For COUNT queries: SELECT COUNT(*) FROM table WHERE ...\n"
        "- For LIST queries: SELECT columns FROM table WHERE ... LIMIT 100\n"
        "- Always use proper WHERE clauses based on user filters\n"
        "- For date comparisons in PostgreSQL, use EXTRACT(YEAR FROM date_column) or date comparisons\n"
        "- Pay attention to data types when building WHERE clauses\n"
        "- Use table aliases for better readability in JOIN queries\n\n"
        "Example 1 (Simple): User asks 'How many students enrolled after 2020?'\n"
        "SQL: SELECT COUNT(*) FROM student WHERE EXTRACT(YEAR FROM enroll_date) >= 2020\n\n"
        "Example 2 (Simple): User asks 'List active students'\n"
        "SQL: SELECT id, name, enroll_date, is_active FROM student WHERE is_active = true LIMIT 100\n\n"
        "Example 3 (JOIN): User asks 'How many students in Grade1-ClassA?'\n"
        "SQL: SELECT COUNT(*) FROM student s JOIN class c ON s.class_id = c.id WHERE c.class_name = 'Grade1-ClassA'\n\n"
        "Example 4 (Multiple JOINs): User asks 'Which courses did Tom take?'\n"
        "SQL: SELECT c.course_name, ce.score, ce.semester \n"
        "     FROM student s \n"
        "     JOIN course_enrollment ce ON s.id = ce.student_id \n"
        "     JOIN course c ON ce.course_id = c.id \n"
        "     WHERE s.name = 'Tom' LIMIT 100\n\n"
        "Example 5 (Aggregation with JOIN): User asks 'How many students enrolled in Computer Science courses?'\n"
        "SQL: SELECT COUNT(DISTINCT ce.student_id) \n"
        "     FROM course_enrollment ce \n"
        "     JOIN course c ON ce.course_id = c.id \n"
        "     WHERE c.department = 'Computer Science'"
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt}
    ]

    # Step 5: SQL generation call
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

    # Step 6: Execute tool calls
    function_response = None
    for tool_call in tool_calls:
        func_obj = getattr(tool_call, 'function', None)
        if not func_obj:
            continue
            
        function_args = json.loads(func_obj.arguments)
        
        if func_obj.name == 'execute_query':
            user_prompt = function_args.get('user_prompt', prompt)
            sql_query = function_args.get('sql_query', '')
            
            # Log the generated SQL for debugging
            print(f"\n[Generated SQL] {sql_query}\n")
            
            function_response = execute_query(user_prompt=user_prompt, sql_query=sql_query)
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": "execute_query",
                "content": function_response
            })

    # Step 7: Final assistant call with tool outputs
    final_response = _call_llm_with_fallback(client, messages, model=model, tools=tools)
    final_text = final_response.choices[0].message.content
    # return final assistant text and the raw tool output (function_response)
    return final_text, function_response