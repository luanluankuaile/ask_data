import json
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .query_sql import (
    DATABASE_URI,
    generate_relationship_model,
    generate_relationship_options,
    get_engine,
    run_function_tool_flow,
)
from .relationship_service import (
    delete_relationship_edge,
    load_mapping,
    load_relationship_catalog,
    load_schema_catalog,
    replace_relationship_edge,
    save_mapping,
    save_relationship_catalog,
    validate_path_option,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_FILE = PROJECT_ROOT / "front_end" / "index.html"
RELATIONSHIPS_FILE = PROJECT_ROOT / "front_end" / "relationships.html"

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


class RelationshipOptionsRequest(BaseModel):
    source_table: str = Field(..., min_length=1, max_length=255)
    target_table: str = Field(..., min_length=1, max_length=255)


class SaveMappingRequest(BaseModel):
    source_table: str = Field(..., min_length=1, max_length=255)
    target_table: str = Field(..., min_length=1, max_length=255)
    fingerprint: str = Field(..., min_length=64, max_length=64)
    mapping: dict[str, Any]
    confirm_non_unique: bool = False


class EditRelationshipEdgeRequest(BaseModel):
    fingerprint: str = Field(..., min_length=64, max_length=64)
    left_table: str = Field(..., min_length=1, max_length=255)
    left_column: str = Field(..., min_length=1, max_length=255)
    right_table: str = Field(..., min_length=1, max_length=255)
    right_column: str = Field(..., min_length=1, max_length=255)
    updated_left_column: str = Field(..., min_length=1, max_length=255)
    updated_right_column: str = Field(..., min_length=1, max_length=255)


class DeleteRelationshipEdgeRequest(BaseModel):
    fingerprint: str = Field(..., min_length=64, max_length=64)
    left_table: str = Field(..., min_length=1, max_length=255)
    left_column: str = Field(..., min_length=1, max_length=255)
    right_table: str = Field(..., min_length=1, max_length=255)
    right_column: str = Field(..., min_length=1, max_length=255)


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


@app.get("/relationships", include_in_schema=False)
def relationships_page() -> FileResponse:
    return FileResponse(RELATIONSHIPS_FILE)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/info", response_model=InfoResponse)
def info() -> InfoResponse:
    return InfoResponse(database_uri=mask_database_uri(DATABASE_URI))


@app.get("/api/relationships/tables")
def relationship_tables() -> dict[str, Any]:
    try:
        catalog = load_schema_catalog(get_engine())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to inspect schema: {exc}") from exc
    descriptions = {
        item["table_name"]: {
            "business_name": item.get("business_name"),
            "description": item.get("business_description"),
        }
        for item in catalog["metadata"]
        if item.get("column_name") is None
    }
    return {
        "tables": [
            {
                "name": name,
                **descriptions.get(name, {}),
                "columns": [
                    {"name": column_name, **column}
                    for column_name, column in sorted(table["columns"].items())
                ],
            }
            for name, table in sorted(catalog["schema"]["tables"].items())
        ],
        "warnings": catalog["warnings"],
    }


@app.get("/api/relationships/model")
def get_relationship_model() -> dict[str, Any]:
    try:
        catalog = load_schema_catalog(get_engine())
        model = load_relationship_catalog(get_engine(), catalog["fingerprint"])
        return {
            "model": model,
            "tables": sorted(catalog["schema"]["tables"]),
            "fingerprint": catalog["fingerprint"],
            "warnings": catalog["warnings"],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load relationship model: {exc}") from exc


@app.post("/api/relationships/model/refresh")
def refresh_relationship_model() -> dict[str, Any]:
    try:
        return generate_relationship_model()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to generate relationship model: {exc}") from exc


@app.put("/api/relationships/model/edge")
def edit_relationship_edge(body: EditRelationshipEdgeRequest) -> dict[str, Any]:
    try:
        engine = get_engine()
        catalog = load_schema_catalog(engine)
        if body.fingerprint != catalog["fingerprint"]:
            raise HTTPException(status_code=409, detail="Schema changed; refresh the relationship model first")
        stored = load_relationship_catalog(engine, catalog["fingerprint"])
        if not stored or stored["stale"]:
            raise HTTPException(status_code=409, detail="The relationship model is missing or stale")
        relationships = replace_relationship_edge(
            stored["relationships"],
            catalog["schema"],
            {
                "left_table": body.left_table,
                "left_column": body.left_column,
                "right_table": body.right_table,
                "right_column": body.right_column,
            },
            {
                "left_column": body.updated_left_column,
                "right_column": body.updated_right_column,
            },
        )
        save_relationship_catalog(engine, relationships, catalog["fingerprint"])
        return {"relationships": relationships, "fingerprint": catalog["fingerprint"]}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to edit relationship: {exc}") from exc


@app.delete("/api/relationships/model/edge")
def remove_relationship_edge(body: DeleteRelationshipEdgeRequest) -> dict[str, Any]:
    try:
        engine = get_engine()
        catalog = load_schema_catalog(engine)
        if body.fingerprint != catalog["fingerprint"]:
            raise HTTPException(status_code=409, detail="Schema changed; refresh the relationship model first")
        stored = load_relationship_catalog(engine, catalog["fingerprint"])
        if not stored or stored["stale"]:
            raise HTTPException(status_code=409, detail="The relationship model is missing or stale")
        relationships = delete_relationship_edge(
            stored["relationships"],
            {
                "left_table": body.left_table,
                "left_column": body.left_column,
                "right_table": body.right_table,
                "right_column": body.right_column,
            },
        )
        save_relationship_catalog(engine, relationships, catalog["fingerprint"])
        return {"relationships": relationships, "fingerprint": catalog["fingerprint"]}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete relationship: {exc}") from exc


@app.post("/api/relationships/options")
def relationship_options(body: RelationshipOptionsRequest) -> dict[str, Any]:
    try:
        return generate_relationship_options(body.source_table, body.target_table)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to generate relationship options: {exc}") from exc


@app.get("/api/relationships/mapping")
def get_relationship_mapping(
    source_table: str = Query(..., min_length=1, max_length=255),
    target_table: str = Query(..., min_length=1, max_length=255),
) -> dict[str, Any]:
    try:
        catalog = load_schema_catalog(get_engine())
        if source_table not in catalog["schema"]["tables"] or target_table not in catalog["schema"]["tables"]:
            raise HTTPException(status_code=404, detail="Unknown source or target table")
        return {
            "saved": load_mapping(get_engine(), source_table, target_table, catalog),
            "fingerprint": catalog["fingerprint"],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load mapping: {exc}") from exc


@app.put("/api/relationships/mapping")
def put_relationship_mapping(body: SaveMappingRequest) -> dict[str, Any]:
    try:
        catalog = load_schema_catalog(get_engine())
        if body.source_table not in catalog["schema"]["tables"] or body.target_table not in catalog["schema"]["tables"]:
            raise HTTPException(status_code=404, detail="Unknown source or target table")
        if body.fingerprint != catalog["fingerprint"]:
            raise HTTPException(status_code=409, detail="Schema changed; generate options again before saving")
        mapping = validate_path_option(
            body.mapping,
            catalog["schema"],
            body.source_table,
            body.target_table,
        )
        non_unique_join = any(
            not catalog["schema"]["tables"][join["left_table"]]["columns"][join["left_column"]]["unique"]
            and not catalog["schema"]["tables"][join["right_table"]]["columns"][join["right_column"]]["unique"]
            for join in mapping["joins"]
        )
        if non_unique_join and not body.confirm_non_unique:
            raise HTTPException(
                status_code=422,
                detail="Confirm that non-unique join columns may multiply result rows.",
            )
        save_mapping(
            get_engine(),
            body.source_table,
            body.target_table,
            mapping,
            catalog["fingerprint"],
        )
        return {"saved": True, "mapping": mapping}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save mapping: {exc}") from exc


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
