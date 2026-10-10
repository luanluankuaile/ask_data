import json
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .query_sql import DATABASE_URI, run_function_tool_flow

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_FILE = PROJECT_ROOT / "front_end" / "index.html"

app = FastAPI(
    title="Ask Data",
    description=(
        "Translate a natural-language question into a read-only SQL query "
        "and return the assistant reply plus query results."
    ),
)


class QueryRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        examples=["How many students enrolled after 2020?"],
    )


class QueryResponse(BaseModel):
    assistant_text: str
    result: Optional[Any] = None


class InfoResponse(BaseModel):
    database_uri: str


def mask_database_uri(uri: str) -> str:
    """Hide the password before returning the connection string."""
    parsed = urlparse(uri)
    if not parsed.password:
        return uri
    username = parsed.username or ""
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    userinfo = f"{username}:****@" if username else "****@"
    return urlunparse(parsed._replace(netloc=f"{userinfo}{host}{port}"))


def parse_tool_output(tool_output: Optional[str]) -> Optional[Any]:
    if not tool_output:
        return None
    try:
        return json.loads(tool_output)
    except json.JSONDecodeError:
        return tool_output


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(INDEX_FILE)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/info", response_model=InfoResponse)
def info() -> InfoResponse:
    return InfoResponse(database_uri=mask_database_uri(DATABASE_URI))


@app.post("/api/query", response_model=QueryResponse)
def query(body: QueryRequest) -> QueryResponse:
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt must not be empty")
    try:
        assistant_text, tool_output = run_function_tool_flow(prompt)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process query: {exc}",
        ) from exc
    return QueryResponse(
        assistant_text=assistant_text or "",
        result=parse_tool_output(tool_output),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
