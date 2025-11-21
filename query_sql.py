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


AZURE_KEY = os.environ.get("AZURE_OPENAI_API_KEY")


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
if DATABASE_URI.startswith("sqlite"):
    # sqlite fallback stores year as integer in this script; use >= for 2020 inclusive
    YEAR_FILTER_EXPR = "enroll_date >= 2020"
else:
    # For Postgres and most SQL DBs that support EXTRACT
    YEAR_FILTER_EXPR = "EXTRACT(YEAR FROM enroll_date) >= 2020"


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


# --- Function-tool integration: define a query function that the LLM can call ---
def query_students(enroll_after_year: int = 2020, is_active: bool = None, limit: int = 100):
    """Query students from the configured database and return a JSON array of rows.

    Parameters:
      - enroll_after_year: include students enrolled in or after this year
      - is_active: optional boolean to filter active students (if column exists)
      - limit: maximum number of rows to return
    Returns: JSON string of list of student objects
    """
    engine = create_engine(DATABASE_URI)
    with engine.connect() as conn:
        # Build WHERE clauses safely
        clauses = []
        params = {}
        if DATABASE_URI.startswith("sqlite"):
            clauses.append("enroll_date >= :year")
            params["year"] = enroll_after_year
        else:
            clauses.append("EXTRACT(YEAR FROM enroll_date) >= :year")
            params["year"] = enroll_after_year

        if is_active is not None:
            # add filter only if column exists - check columns
            col_res = [r[0] for r in conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='students';")).fetchall()]
            if 'is_active' in col_res:
                clauses.append("is_active = :is_active")
                params['is_active'] = is_active

        where_clause = " AND ".join(clauses) if clauses else "1=1"
        sql = text(f"SELECT id, name, enroll_date FROM students WHERE {where_clause} ORDER BY enroll_date LIMIT :limit;")
        params['limit'] = limit
        rows = conn.execute(sql, params).fetchall()
        result = []
        for r in rows:
            # convert row to dict
            row_dict = {
                'id': r[0],
                'name': r[1],
                'enroll_date': r[2].isoformat() if getattr(r[2], 'isoformat', None) else r[2]
            }
            result.append(row_dict)
        return json.dumps(result, ensure_ascii=False)


def run_function_tool_flow(prompt: str, model: str | None = None):
    """Run a function-tool LLM flow for `query_students` and return the final assistant text and tool output.

    Returns a tuple: (assistant_text: str, tool_response_json: str|None)
    - If the model calls the `query_students` function, this will execute it and include the function output.
    - If the model does not call the function, tool_response_json will be None and assistant_text contains the assistant reply.
    """
    if not AZURE_KEY:
        raise RuntimeError("AZURE_OPENAI_API_KEY is not set; cannot run LLM function-tool flow")

    # prepare client class
    try:
        from openai import AzureOpenAI as OpenAIAzureClient
    except Exception:
        OpenAIAzureClient = None

    client_cls = OpenAIAzureClient if OpenAIAzureClient is not None else AzureOpenAI

    client = client_cls(
        api_key=AZURE_KEY,
        api_version=os.environ.get("OPENAI_API_VERSION", "2025-04-01-preview"),
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", os.environ.get("AZURE_OPENAI_API_ENDPOINT", "")),
    )

    tools = [
        {
            "type": "function",
            "function": {
                "name": "query_students",
                "description": "Query students from the students table and return JSON list of rows",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "enroll_after_year": {"type": "integer"},
                        "is_active": {"type": ["boolean", "null"]},
                        "limit": {"type": "integer"}
                    },
                    "required": ["enroll_after_year"]
                }
            }
        }
    ]

    # schema-aware system prompt
    students_schema = []
    try:
        engine = create_engine(DATABASE_URI)
        with engine.connect() as conn:
            if DATABASE_URI.startswith("sqlite"):
                res = conn.execute(text("PRAGMA table_info('students');")).fetchall()
                for r in res:
                    students_schema.append((r[1], r[2]))
            else:
                res = conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = :t;"), {"t": 'students'}).fetchall()
                for r in res:
                    students_schema.append((r[0], r[1]))
    except Exception:
        pass

    schema_lines = '\n'.join([f"- {c}: {t}" for c, t in students_schema]) if students_schema else "(schema unavailable)"

    system = (
        "You are a SQL-aware assistant with access to a students database via a function tool. "
        "Available table schema:\n" + schema_lines + "\n"
        "When appropriate you may call the function tool `query_students` to fetch rows."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt}
    ]

    model = model or os.environ.get("MODEL", "gpt-4o")

    # first call
    response = _call_llm_with_fallback(client, messages, model=model, tools=tools, tool_choice="auto")
    response_message = response.choices[0].message

    tool_calls = getattr(response_message, 'tool_calls', None)
    if not tool_calls:
        # no function call; return assistant reply
        return response_message.content, None

    # execute tool calls
    function_response = None
    for tool_call in tool_calls:
        if getattr(tool_call, 'function', None) and tool_call.function.name == 'query_students':
            function_args = json.loads(tool_call.function.arguments)
            enroll_after_year = function_args.get('enroll_after_year', 2020)
            is_active = function_args.get('is_active', None)
            limit = function_args.get('limit', 100)
            function_response = query_students(enroll_after_year=enroll_after_year, is_active=is_active, limit=limit)
            # append tool output and continue
            messages.append({
                "tool_call_id": getattr(tool_call, 'id', None),
                "role": "tool",
                "name": "query_students",
                "content": function_response
            })

    # final assistant call with tool outputs
    final_response = _call_llm_with_fallback(client, messages, model=model, tools=tools)
    final_text = final_response.choices[0].message.content
    # return final assistant text and the raw tool output (function_response)
    return final_text, function_response


def _simple_fallback_nl_to_sql(prompt: str) -> tuple[str, dict]:
    """Very small rule-based fallback for common simple prompts.

    This only covers trivial patterns (counts, selects) and is used when no
    AZURE OpenAI key is configured. Extend as needed.
    """
    p = prompt.lower().strip()
    # Map common words to the `students` table for this project
    # How many students do you have? -> count
    if re.search(r"how many .*student|how many students", p):
        return "SELECT COUNT(1) FROM students", {}
    # List students -> select *
    if re.search(r"list .*student|show .*student|list all students|recent students", p):
        return "SELECT id, name, enroll_date FROM students ORDER BY enroll_date DESC LIMIT 100", {}

    # Year-based enrollment questions, e.g. "enrolled in 2022", "enrolled on 2022", "enrolled after 2020"
    year_match = re.search(r"(?<!\d)(20\d{2}|19\d{2})(?!\d)", p)
    if year_match and re.search(r"enroll|enrolled|enrollment|入学", p):
        year = int(year_match.group(1))
        # If DB is sqlite, use date-range string comparison which works for 'YYYY-MM-DD'
        if DATABASE_URI.startswith("sqlite"):
            start = f"{year}-01-01"
            end = f"{year+1}-01-01"
            if re.search(r"after|>=|on or after|on or after|onwards", p):
                return ("SELECT COUNT(1) FROM students WHERE enroll_date >= :start", {"start": start})
            if re.search(r"before|<|until", p):
                return ("SELECT COUNT(1) FROM students WHERE enroll_date < :start", {"start": start})
            # default: exact year
            return ("SELECT COUNT(1) FROM students WHERE enroll_date >= :start AND enroll_date < :end", {"start": start, "end": end})
        else:
            # For Postgres and other DBs supporting EXTRACT
            if re.search(r"after|>=|on or after|on or after|onwards", p):
                return ("SELECT COUNT(1) FROM students WHERE EXTRACT(YEAR FROM enroll_date) >= :year", {"year": year})
            if re.search(r"before|<|until", p):
                return ("SELECT COUNT(1) FROM students WHERE EXTRACT(YEAR FROM enroll_date) < :year", {"year": year})
            return ("SELECT COUNT(1) FROM students WHERE EXTRACT(YEAR FROM enroll_date) = :year", {"year": year})
    # fallback: raise so caller can handle
    raise ValueError("No fallback rule matched the prompt; enable AZURE_OPENAI_API_KEY to generate SQL via LLM.")


def generate_sql_from_prompt(prompt: str, dialect: str = "postgresql") -> tuple[str, dict]:
    """Generate a single read-only SQL statement from a natural language prompt.

    - Uses Azure OpenAI LLM when `AZURE_OPENAI_API_KEY` is set.
    - Otherwise uses a conservative rule-based fallback for a few simple prompts.

    The function validates the generated SQL and only allows single SELECT statements.
    """
    # If we have an Azure key, try LLM generation
    if AZURE_KEY:
        try:
            # Introspect the students table schema to give the model concrete context
            def get_table_schema(table_name: str):
                engine = create_engine(DATABASE_URI)
                cols = []
                try:
                    with engine.connect() as conn:
                        if DATABASE_URI.startswith("sqlite"):
                            res = conn.execute(text(f"PRAGMA table_info('{table_name}');")).fetchall()
                            # PRAGMA returns (cid, name, type, notnull, dflt_value, pk)
                            for r in res:
                                cols.append((r[1], r[2]))
                        else:
                            res = conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = :t;"), {"t": table_name}).fetchall()
                            for r in res:
                                cols.append((r[0], r[1]))
                except Exception:
                    pass
                return cols

            students_schema = get_table_schema('students')
            schema_lines = '\n'.join([f"- {c}: {t}" for c, t in students_schema]) if students_schema else "(schema unavailable)"

            # construct a deterministic system prompt guiding the model and include schema
            system = (
                "You are a SQL generator specialized for a database with a single relevant table `students`. "
                "Available table schema:\n" + schema_lines + "\n"
                "Translate the user's natural language request into a single, syntactically valid SQL SELECT statement only. "
                "Do NOT include any explanatory text or markdown. Return a single SQL statement without trailing semicolon. "
                "The SQL must be read-only (SELECT). If the request cannot be expressed as a SELECT, respond with the single token: CANNOT_IMPLEMENT."
            )
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ]
            model = os.environ.get("MODEL", "gpt-4o")
            llm_client = AzureOpenAI(api_key=AZURE_KEY,
                                    api_version=os.environ.get("OPENAI_API_VERSION", "2025-04-01-preview"),
                                    azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", os.environ.get("AZURE_OPENAI_API_ENDPOINT", "")))
            resp = _call_llm_with_fallback(llm_client, messages, model=model)
            sql_text = resp.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError(f"LLM generation failed: {e}")
    else:
        # no key: use simple fallback rules
        sql_text, params = _simple_fallback_nl_to_sql(prompt)
        return sql_text, params
    # Basic validation: must be a single SELECT statement
    sql_clean = sql_text.strip().rstrip(";")
    upper = sql_clean.upper()
    forbidden = ["INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "CREATE ", "TRUNCATE ", "GRANT ", "REVOKE "]
    if any(tok in upper for tok in forbidden):
        raise ValueError("Generated SQL contains forbidden write/DDL operations")
    # Disallow comments or multiple statements
    if ";" in sql_text or "--" in sql_text or "/*" in sql_text:
        raise ValueError("Generated SQL appears to contain multiple statements or comments; refusing to run")
    if not upper.strip().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    # If we reached here from the LLM path, return SQL with empty params dict (no paramization attempted).
    return sql_clean, {}


def _cli_generate_and_print(prompt: str):
    try:
        sql, params = generate_sql_from_prompt(prompt)
        print("Generated SQL:\n", sql)
        if params:
            print("Parameters:", params)
    except Exception as e:
        print("Failed to generate SQL:", e)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--nl', help='Natural language prompt to generate SQL for')
    args = parser.parse_args()
    if args.nl:
        _cli_generate_and_print(args.nl)