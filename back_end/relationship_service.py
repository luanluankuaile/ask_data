"""Pure validation helpers for metadata-derived relationship mappings."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_INTERNAL_TABLES = {
    "schema_metadata",
    "semantic_relationship_mappings",
    "semantic_relationship_catalog",
}
_MAX_PATH_HOPS = 5
_MAX_PATH_OPTIONS = 5
_MAX_MODEL_RELATIONSHIPS = 300


def _type_family(value: Any) -> str:
    name = str(value or "").strip().lower()
    name = re.sub(r"\([^)]*\)", "", name).strip()
    aliases = {
        "character varying": "string",
        "varchar": "string",
        "character": "string",
        "char": "string",
        "text": "string",
        "string": "string",
        "smallint": "integer",
        "integer": "integer",
        "int": "integer",
        "serial": "integer",
        "bigint": "integer",
        "bigserial": "integer",
        "numeric": "numeric",
        "decimal": "numeric",
        "real": "numeric",
        "float": "numeric",
        "double precision": "numeric",
        "boolean": "boolean",
        "bool": "boolean",
        "date": "date",
        "timestamp": "datetime",
        "timestamp without time zone": "datetime",
        "timestamp with time zone": "datetime",
        "datetime": "datetime",
        "uuid": "uuid",
    }
    return aliases.get(name, name)


def types_compatible(left: Any, right: Any) -> bool:
    """Return whether two live column types are safe equality-join candidates."""
    left_family = _type_family(left)
    right_family = _type_family(right)
    return bool(left_family and left_family == right_family)


def normalize_known_relationships(
    schema: dict[str, Any], metadata: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Normalize live foreign keys and valid metadata hints into relationship edges."""
    edges: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    warnings: list[str] = []

    def add_edge(
        left_table: str,
        left_column: str,
        right_table: str,
        right_column: str,
        provenance: str,
        description: str = "",
    ) -> None:
        tables = schema.get("tables", {})
        left = tables.get(left_table, {}).get("columns", {}).get(left_column)
        right = tables.get(right_table, {}).get("columns", {}).get(right_column)
        if not left or not right:
            warnings.append(
                f"Ignored {provenance} mapping {left_table}.{left_column} -> "
                f"{right_table}.{right_column}: column does not exist."
            )
            return
        if not types_compatible(left.get("type"), right.get("type")):
            warnings.append(
                f"Ignored {provenance} mapping {left_table}.{left_column} -> "
                f"{right_table}.{right_column}: incompatible column types."
            )
            return

        key = (left_table, left_column, right_table, right_column)
        edge = edges.get(key)
        if edge is None:
            edge = {
                "left_table": left_table,
                "left_column": left_column,
                "right_table": right_table,
                "right_column": right_column,
                "provenance": [],
                "description": description,
            }
            edges[key] = edge
        if provenance not in edge["provenance"]:
            edge["provenance"].append(provenance)
        if provenance == "physical_fk":
            edge["priority"] = 0
        else:
            edge.setdefault("priority", 1)

    def resolve_reference_table(table_name: str, column_name: str) -> str | None:
        if table_name in schema.get("tables", {}):
            if column_name in schema["tables"][table_name].get("columns", {}):
                return table_name
            return None
        lower_name = table_name.lower()
        aliases = set()
        if lower_name.endswith("ies") and len(lower_name) > 3:
            aliases.add(lower_name[:-3] + "y")
        if lower_name.endswith("es") and len(lower_name) > 2:
            aliases.add(lower_name[:-2])
        if lower_name.endswith("s") and len(lower_name) > 1:
            aliases.add(lower_name[:-1])
        matches = [
            candidate for candidate, table in schema.get("tables", {}).items()
            if candidate.lower() in aliases
            and column_name in table.get("columns", {})
        ]
        return matches[0] if len(matches) == 1 else None

    tables = schema.get("tables", {})
    for table_name, table in tables.items():
        for foreign_key in table.get("foreign_keys", []):
            left_columns = foreign_key.get("constrained_columns") or []
            right_columns = foreign_key.get("referred_columns") or []
            if len(left_columns) != 1 or len(right_columns) != 1:
                warnings.append(
                    f"Skipped composite foreign key on {table_name}; only single-column mappings are supported."
                )
                continue
            referred_table = foreign_key.get("referred_table")
            if not referred_table:
                continue
            add_edge(
                table_name,
                left_columns[0],
                referred_table,
                right_columns[0],
                "physical_fk",
            )

    for item in metadata:
        if not item.get("is_foreign_key") or not item.get("column_name"):
            continue
        reference = str(item.get("foreign_key_reference") or "")
        if "." not in reference:
            warnings.append(
                f"Ignored malformed metadata relationship for "
                f"{item.get('table_name')}.{item.get('column_name')}."
            )
            continue
        target_table, target_column = reference.rsplit(".", 1)
        resolved_table = resolve_reference_table(target_table, target_column)
        if resolved_table is None:
            add_edge(
                str(item.get("table_name")),
                str(item.get("column_name")),
                target_table,
                target_column,
                "metadata_hint",
                str(item.get("business_description") or ""),
            )
            continue
        add_edge(
            str(item.get("table_name")),
            str(item.get("column_name")),
            resolved_table,
            target_column,
            "metadata_hint",
            str(item.get("business_description") or ""),
        )

    ordered = sorted(
        edges.values(),
        key=lambda edge: (
            edge["priority"],
            edge["left_table"],
            edge["right_table"],
            edge["left_column"],
            edge["right_column"],
        ),
    )
    for edge in ordered:
        edge.pop("priority", None)
        edge["id"] = (
            f"{edge['left_table']}.{edge['left_column']}->"
            f"{edge['right_table']}.{edge['right_column']}"
        )
    return ordered, warnings


def validate_path_option(
    option: dict[str, Any],
    schema: dict[str, Any],
    source_table: str,
    target_table: str,
) -> dict[str, Any]:
    """Validate and sanitize a proposed or user-edited relationship path."""
    tables = option.get("tables")
    joins = option.get("joins")
    schema_tables = schema.get("tables", {})
    if not isinstance(tables, list) or not isinstance(joins, list):
        raise ValueError("A mapping option must contain tables and joins lists.")
    if len(tables) < 2 or len(joins) != len(tables) - 1:
        raise ValueError("A mapping path must have one join for every adjacent table pair.")
    if len(joins) > _MAX_PATH_HOPS:
        raise ValueError(f"Mapping paths cannot exceed {_MAX_PATH_HOPS} joins.")
    if tables[0] != source_table or tables[-1] != target_table:
        raise ValueError("The mapping path does not connect the selected endpoint tables.")
    if len(set(tables)) != len(tables):
        raise ValueError("Mapping paths cannot contain repeated tables.")
    if any(table not in schema_tables for table in tables):
        raise ValueError("The mapping path contains an unknown table.")

    clean_joins = []
    for index, join in enumerate(joins):
        left_table = tables[index]
        right_table = tables[index + 1]
        if join.get("left_table") != left_table or join.get("right_table") != right_table:
            raise ValueError("Join tables must follow the path order exactly.")
        left_column = join.get("left_column")
        right_column = join.get("right_column")
        if not isinstance(left_column, str) or not _IDENTIFIER.fullmatch(left_column):
            raise ValueError("Join columns must be simple database identifiers.")
        if not isinstance(right_column, str) or not _IDENTIFIER.fullmatch(right_column):
            raise ValueError("Join columns must be simple database identifiers.")

        left = schema_tables[left_table].get("columns", {}).get(left_column)
        right = schema_tables[right_table].get("columns", {}).get(right_column)
        if not left or not right:
            raise ValueError("A join column does not exist in the selected table.")
        if not types_compatible(left.get("type"), right.get("type")):
            raise ValueError("Join column types are incompatible.")

        clean_joins.append({
            "left_table": left_table,
            "left_column": left_column,
            "right_table": right_table,
            "right_column": right_column,
            "provenance": str(join.get("provenance") or "user_selected"),
            "rationale": str(join.get("rationale") or ""),
            "left_unique": bool(left.get("unique")),
            "right_unique": bool(right.get("unique")),
        })

    return {
        "tables": list(tables),
        "joins": clean_joins,
        "rationale": str(option.get("rationale") or ""),
    }


def schema_fingerprint(schema: dict[str, Any], metadata: list[dict[str, Any]]) -> str:
    """Create a stable hash for detecting stale saved mappings."""
    payload = {
        "tables": schema.get("tables", {}),
        "metadata": sorted(
            metadata,
            key=lambda item: (
                str(item.get("table_name")),
                str(item.get("column_name")),
            ),
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_schema_catalog(engine) -> dict[str, Any]:
    """Read live database structure and semantic descriptions into one catalog."""
    inspector = inspect(engine)
    tables: dict[str, Any] = {}
    for table_name in inspector.get_table_names():
        if table_name in _INTERNAL_TABLES:
            continue
        primary_columns = set(
            inspector.get_pk_constraint(table_name).get("constrained_columns") or []
        )
        unique_columns = set(primary_columns)
        for constraint in inspector.get_unique_constraints(table_name):
            columns = constraint.get("column_names") or []
            if len(columns) == 1:
                unique_columns.add(columns[0])
        for index in inspector.get_indexes(table_name):
            columns = index.get("column_names") or []
            if index.get("unique") and len(columns) == 1:
                unique_columns.add(columns[0])

        columns = {}
        for column in inspector.get_columns(table_name):
            column_name = column["name"]
            columns[column_name] = {
                "type": str(column["type"]),
                "primary_key": column_name in primary_columns,
                "unique": column_name in unique_columns,
                "nullable": bool(column.get("nullable", True)),
            }
        tables[table_name] = {
            "columns": columns,
            "foreign_keys": inspector.get_foreign_keys(table_name),
        }

    metadata: list[dict[str, Any]] = []
    try:
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT table_name, column_name, business_name, business_description, "
                "data_type, is_primary_key, is_foreign_key, foreign_key_reference, sample_values "
                "FROM schema_metadata ORDER BY table_name, column_name"
            )).mappings().all()
            metadata = [dict(row) for row in rows if row["table_name"] in tables]
    except SQLAlchemyError:
        metadata = []

    schema = {"tables": tables}
    edges, warnings = normalize_known_relationships(schema, metadata)
    return {
        "schema": schema,
        "metadata": metadata,
        "known_relationships": edges,
        "warnings": warnings,
        "fingerprint": schema_fingerprint(schema, metadata),
    }


def relationship_prompt(
    catalog: dict[str, Any],
    source_table: str | None = None,
    target_table: str | None = None,
) -> str:
    """Serialize the full metadata-backed schema for relationship discovery."""
    tables = catalog["schema"]["tables"]

    metadata_by_table: dict[str, list[dict[str, Any]]] = {}
    for item in catalog["metadata"]:
        metadata_by_table.setdefault(item["table_name"], []).append(item)

    schema_context = []
    for table_name, table in tables.items():
        descriptions = metadata_by_table.get(table_name, [])
        table_description = next(
            (item.get("business_description", "") for item in descriptions if not item.get("column_name")),
            "",
        )
        columns = []
        for column_name, column in table["columns"].items():
            description = next(
                (item.get("business_description", "") for item in descriptions if item.get("column_name") == column_name),
                "",
            )
            columns.append({
                "name": column_name,
                "type": column["type"],
                "primary_key": column["primary_key"],
                "unique": column.get("unique", False),
                "description": description,
            })
        schema_context.append({
            "table": table_name,
            "description": table_description,
            "columns": columns,
        })

    payload = {
        "schema": schema_context,
        "known_relationships": catalog["known_relationships"],
    }
    if source_table is not None or target_table is not None:
        payload["requested_endpoints"] = [source_table, target_table]
    return json.dumps(payload, ensure_ascii=True, default=str)


def parse_llm_relationship_catalog(
    content: str, catalog: dict[str, Any]
) -> list[dict[str, Any]]:
    """Validate and enrich LLM-proposed relationship edges for the full schema."""
    raw = (content or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("The model returned invalid JSON for the relationship model.") from exc
    candidates = payload.get("relationships") if isinstance(payload, dict) else None
    if not isinstance(candidates, list):
        raise ValueError("The model response must contain a relationships list.")

    known = {}
    for edge in catalog["known_relationships"]:
        forward = (
            edge["left_table"], edge["left_column"],
            edge["right_table"], edge["right_column"],
        )
        reverse = (forward[2], forward[3], forward[0], forward[1])
        known[forward] = edge["provenance"]
        known[reverse] = edge["provenance"]

    relationships: dict[tuple[tuple[str, str], tuple[str, str]], dict[str, Any]] = {}
    for candidate in candidates[:_MAX_MODEL_RELATIONSHIPS]:
        if not isinstance(candidate, dict):
            continue
        left_table = candidate.get("left_table")
        left_column = candidate.get("left_column")
        right_table = candidate.get("right_table")
        right_column = candidate.get("right_column")
        option = {
            "tables": [left_table, right_table],
            "joins": [{
                "left_table": left_table,
                "left_column": left_column,
                "right_table": right_table,
                "right_column": right_column,
            }],
            "rationale": candidate.get("rationale", ""),
        }
        try:
            clean = validate_path_option(
                option, catalog["schema"], left_table, right_table
            )
        except (TypeError, ValueError):
            continue
        join = clean["joins"][0]
        forward = (left_table, left_column, right_table, right_column)
        reverse = (right_table, right_column, left_table, left_column)
        try:
            confidence = float(candidate.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0
        evidence = known.get(forward) or known.get(reverse) or []
        if "physical_fk" in evidence:
            confidence = 1.0
        elif "metadata_hint" in evidence:
            confidence = max(confidence, 0.8)
        key = tuple(sorted(((left_table, left_column), (right_table, right_column))))
        relationships[key] = {
            **join,
            "provenance": "ai_inferred",
            "evidence": evidence,
            "rationale": str(candidate.get("rationale") or ""),
            "confidence": max(0.0, min(confidence, 1.0)),
        }

    for edge in catalog["known_relationships"]:
        key = tuple(sorted((
            (edge["left_table"], edge["left_column"]),
            (edge["right_table"], edge["right_column"]),
        )))
        relationships.setdefault(key, {
            "left_table": edge["left_table"],
            "left_column": edge["left_column"],
            "right_table": edge["right_table"],
            "right_column": edge["right_column"],
            "provenance": "ai_inferred",
            "evidence": edge["provenance"],
            "rationale": edge.get("description", ""),
            "confidence": 1.0 if "physical_fk" in edge["provenance"] else 0.8,
            "left_unique": catalog["schema"]["tables"][edge["left_table"]]["columns"][edge["left_column"]].get("unique", False),
            "right_unique": catalog["schema"]["tables"][edge["right_table"]]["columns"][edge["right_column"]].get("unique", False),
        })
    return sorted(relationships.values(), key=lambda edge: (
        edge["left_table"], edge["right_table"], edge["left_column"], edge["right_column"]
    ))


def merge_user_edited_relationships(
    generated: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    schema: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Preserve valid manual edge overrides across an AI model refresh."""
    merged = list(generated)
    warnings: list[str] = []
    for edge in previous:
        if edge.get("provenance") != "user_deleted":
            continue
        deleted_edges = edge.get("suppresses") or [
            edge.get("overrides") or {
                key: edge.get(key)
                for key in ("left_table", "left_column", "right_table", "right_column")
            }
        ]
        for deleted_edge in deleted_edges:
            merged = [
                candidate for candidate in merged
                if not all(candidate.get(key) == value for key, value in deleted_edge.items())
            ]
        merged.append(edge)

    for edge in previous:
        if edge.get("provenance") != "user_edited":
            continue
        option = {
            "tables": [edge.get("left_table"), edge.get("right_table")],
            "joins": [{
                "left_table": edge.get("left_table"),
                "left_column": edge.get("left_column"),
                "right_table": edge.get("right_table"),
                "right_column": edge.get("right_column"),
            }],
            "rationale": edge.get("rationale", "Manually edited in the relationship model."),
        }
        try:
            validated = validate_path_option(
                option, schema, edge.get("left_table"), edge.get("right_table")
            )["joins"][0]
        except (TypeError, ValueError):
            warnings.append(
                "A manually edited relationship was not preserved because its columns "
                "no longer exist or have incompatible types."
            )
            continue

        override = edge.get("overrides")
        if override:
            merged = [
                candidate for candidate in merged
                if not all(candidate.get(key) == value for key, value in override.items())
            ]
        else:
            table_pair = frozenset((edge["left_table"], edge["right_table"]))
            merged = [
                candidate for candidate in merged
                if frozenset((candidate["left_table"], candidate["right_table"])) != table_pair
            ]
        same_edge = next((
            candidate for candidate in merged
            if candidate["left_table"] == validated["left_table"]
            and candidate["left_column"] == validated["left_column"]
            and candidate["right_table"] == validated["right_table"]
            and candidate["right_column"] == validated["right_column"]
        ), None)
        if same_edge:
            same_edge["provenance"] = "user_edited"
            same_edge["overrides"] = override
            same_edge["rationale"] = "Manually confirmed; preserved during AI model refresh."
            continue
        validated.update({
            "provenance": "user_edited",
            "overrides": override,
            "rationale": "Manually edited; preserved during AI model refresh.",
            "confidence": edge.get("confidence", 1.0),
        })
        merged.append(validated)

    merged.sort(key=lambda edge: (
        edge["left_table"], edge["right_table"], edge["left_column"], edge["right_column"]
    ))
    return merged, warnings


def find_relationship_paths(
    catalog: dict[str, Any],
    relationships: list[dict[str, Any]],
    source_table: str,
    target_table: str,
) -> list[dict[str, Any]]:
    """Enumerate bounded simple paths from a generated full-schema model."""
    tables = catalog["schema"]["tables"]
    if source_table not in tables or target_table not in tables:
        raise ValueError("Source and target must be existing business tables.")
    if source_table == target_table:
        raise ValueError("Source and target tables must be different.")

    adjacency: dict[str, list[dict[str, Any]]] = {}
    for edge in relationships:
        if edge.get("provenance") == "user_deleted":
            continue
        adjacency.setdefault(edge["left_table"], []).append(edge)
        adjacency.setdefault(edge["right_table"], []).append(edge)

    paths: list[dict[str, Any]] = []
    expansions = 0

    def visit(table_name: str, visited: set[str], path_tables: list[str], path_joins: list[dict[str, Any]]) -> None:
        nonlocal expansions
        if table_name == target_table:
            confidence = sum(join.get("confidence", 0) for join in path_joins) / len(path_joins)
            paths.append({
                "tables": list(path_tables),
                "joins": list(path_joins),
                "confidence": confidence,
                "rationale": " ".join(dict.fromkeys(
                    join.get("rationale", "") for join in path_joins if join.get("rationale")
                )),
            })
            return
        if len(path_joins) >= _MAX_PATH_HOPS or expansions >= 10000:
            return
        for edge in adjacency.get(table_name, []):
            expansions += 1
            if edge["left_table"] == table_name:
                next_table = edge["right_table"]
                left_column, right_column = edge["left_column"], edge["right_column"]
            else:
                next_table = edge["left_table"]
                left_column, right_column = edge["right_column"], edge["left_column"]
            if next_table in visited:
                continue
            oriented = {
                "left_table": table_name,
                "left_column": left_column,
                "right_table": next_table,
                "right_column": right_column,
                "provenance": edge.get("provenance", "ai_inferred"),
                "rationale": edge.get("rationale", ""),
                "confidence": edge.get("confidence", 0),
                "left_unique": tables[table_name]["columns"][left_column].get("unique", False),
                "right_unique": tables[next_table]["columns"][right_column].get("unique", False),
            }
            visit(next_table, visited | {next_table}, path_tables + [next_table], path_joins + [oriented])

    visit(source_table, {source_table}, [source_table], [])
    def provenance_score(option):
        return sum(join.get("provenance") == "user_edited" for join in option["joins"])

    paths.sort(key=lambda option: (
        len(option["joins"]),
        -provenance_score(option),
        -option["confidence"],
    ))
    return paths[:_MAX_PATH_OPTIONS]


def parse_llm_path_options(
    content: str,
    catalog: dict[str, Any],
    source_table: str,
    target_table: str,
) -> list[dict[str, Any]]:
    """Parse, validate, deduplicate, and rank options returned by the LLM."""
    raw = (content or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("The model returned invalid JSON for relationship options.") from exc
    options = payload.get("options") if isinstance(payload, dict) else None
    if not isinstance(options, list):
        raise ValueError("The model response must contain an options list.")

    validated: list[dict[str, Any]] = []
    seen = set()
    for option in options:
        if not isinstance(option, dict):
            continue
        try:
            clean = validate_path_option(
                option, catalog["schema"], source_table, target_table
            )
        except (TypeError, ValueError):
            continue
        for join in clean["joins"]:
            key = (
                join["left_table"], join["left_column"],
                join["right_table"], join["right_column"],
            )
            join["provenance"] = "ai_inferred"
            join["left_unique"] = catalog["schema"]["tables"][join["left_table"]]["columns"][join["left_column"]].get("unique", False)
            join["right_unique"] = catalog["schema"]["tables"][join["right_table"]]["columns"][join["right_column"]].get("unique", False)
        signature = json.dumps(clean["joins"], sort_keys=True)
        if signature in seen:
            continue
        seen.add(signature)
        try:
            confidence = float(option.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0
        clean["confidence"] = max(0.0, min(confidence, 1.0))
        validated.append(clean)

    validated.sort(key=lambda item: (len(item["joins"]), -(item.get("confidence") or 0)))
    return validated[:_MAX_PATH_OPTIONS]


def ensure_mapping_store(engine) -> None:
    """Create the small mapping store when an existing database lacks it."""
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS semantic_relationship_mappings ("
            "source_table VARCHAR(255) NOT NULL, "
            "target_table VARCHAR(255) NOT NULL, "
            "mapping_json TEXT NOT NULL, "
            "schema_fingerprint VARCHAR(64) NOT NULL, "
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "PRIMARY KEY (source_table, target_table))"
        ))
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS semantic_relationship_catalog ("
            "catalog_id INTEGER PRIMARY KEY, "
            "relationships_json TEXT NOT NULL, "
            "schema_fingerprint VARCHAR(64) NOT NULL, "
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        ))


def save_relationship_catalog(engine, relationships: list[dict[str, Any]], fingerprint: str) -> None:
    ensure_mapping_store(engine)
    serialized = json.dumps(relationships, ensure_ascii=True, sort_keys=True)
    with engine.begin() as connection:
        existing = connection.execute(text(
            "SELECT 1 FROM semantic_relationship_catalog WHERE catalog_id = 1"
        )).first()
        values = {"relationships": serialized, "fingerprint": fingerprint}
        if existing:
            connection.execute(text(
                "UPDATE semantic_relationship_catalog SET relationships_json = :relationships, "
                "schema_fingerprint = :fingerprint, updated_at = CURRENT_TIMESTAMP "
                "WHERE catalog_id = 1"
            ), values)
        else:
            connection.execute(text(
                "INSERT INTO semantic_relationship_catalog "
                "(catalog_id, relationships_json, schema_fingerprint) "
                "VALUES (1, :relationships, :fingerprint)"
            ), values)
        
    
def load_relationship_catalog(engine, fingerprint: str) -> dict[str, Any] | None:
    ensure_mapping_store(engine)
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT relationships_json, schema_fingerprint, updated_at "
            "FROM semantic_relationship_catalog WHERE catalog_id = 1"
        )).mappings().first()
    if not row:
        return None
    try:
        relationships = json.loads(row["relationships_json"])
    except json.JSONDecodeError:
        relationships = []
        stale = True
    else:
        stale = row["schema_fingerprint"] != fingerprint
        for edge in relationships:
            provenance = edge.get("provenance", "")
            if provenance != "user_deleted":
                edge["provenance"] = (
                    "user_edited" if "user_edited" in provenance else "ai_inferred"
                )
    return {
        "relationships": relationships,
        "fingerprint": row["schema_fingerprint"],
        "updated_at": str(row["updated_at"]),
        "stale": stale,
    }


def replace_relationship_edge(
    relationships: list[dict[str, Any]],
    schema: dict[str, Any],
    original: dict[str, str],
    updated: dict[str, str],
) -> list[dict[str, Any]]:
    """Replace one relationship's column pair after live-schema validation."""
    match_index = next((
        index for index, edge in enumerate(relationships)
        if edge.get("left_table") == original.get("left_table")
        and edge.get("left_column") == original.get("left_column")
        and edge.get("right_table") == original.get("right_table")
        and edge.get("right_column") == original.get("right_column")
    ), None)
    if match_index is None:
        raise ValueError("The relationship edge is no longer in the model; refresh it before editing.")

    edge = relationships[match_index]
    option = {
        "tables": [edge["left_table"], edge["right_table"]],
        "joins": [{
            "left_table": edge["left_table"],
            "left_column": updated.get("left_column"),
            "right_table": edge["right_table"],
            "right_column": updated.get("right_column"),
        }],
    }
    clean = validate_path_option(
        option, schema, edge["left_table"], edge["right_table"]
    )["joins"][0]
    clean.update({
        "provenance": "user_edited",
        "overrides": {
            "left_table": edge["left_table"],
            "left_column": edge["left_column"],
            "right_table": edge["right_table"],
            "right_column": edge["right_column"],
        },
        "rationale": "Manually edited in the relationship model.",
        "confidence": edge.get("confidence", 1.0),
    })
    updated_relationships = list(relationships)
    updated_relationships[match_index] = clean
    return updated_relationships


def delete_relationship_edge(
    relationships: list[dict[str, Any]],
    original: dict[str, str],
) -> list[dict[str, Any]]:
    """Hide a graph edge and retain a tombstone until the model is regenerated."""
    match_index = next((
        index for index, edge in enumerate(relationships)
        if edge.get("left_table") == original.get("left_table")
        and edge.get("left_column") == original.get("left_column")
        and edge.get("right_table") == original.get("right_table")
        and edge.get("right_column") == original.get("right_column")
        and edge.get("provenance") != "user_deleted"
    ), None)
    if match_index is None:
        raise ValueError("The relationship edge no longer exists in the model.")

    edge = dict(relationships[match_index])
    edge["provenance"] = "user_deleted"
    current_edge = {
        key: edge[key]
        for key in ("left_table", "left_column", "right_table", "right_column")
    }
    original_edge = edge.get("overrides")
    edge["suppresses"] = [current_edge]
    if original_edge and original_edge != current_edge:
        edge["suppresses"].append(original_edge)
    edge["rationale"] = "Deleted by user; hidden until the full model is regenerated."
    updated_relationships = list(relationships)
    updated_relationships[match_index] = edge
    return updated_relationships


def save_mapping(engine, source_table: str, target_table: str, mapping: dict[str, Any], fingerprint: str) -> None:
    ensure_mapping_store(engine)
    serialized = json.dumps(mapping, ensure_ascii=True, sort_keys=True)
    with engine.begin() as connection:
        existing = connection.execute(text(
            "SELECT 1 FROM semantic_relationship_mappings "
            "WHERE source_table = :source AND target_table = :target"
        ), {"source": source_table, "target": target_table}).first()
        values = {
            "source": source_table,
            "target": target_table,
            "mapping": serialized,
            "fingerprint": fingerprint,
        }
        if existing:
            connection.execute(text(
                "UPDATE semantic_relationship_mappings SET mapping_json = :mapping, "
                "schema_fingerprint = :fingerprint, updated_at = CURRENT_TIMESTAMP "
                "WHERE source_table = :source AND target_table = :target"
            ), values)
        else:
            connection.execute(text(
                "INSERT INTO semantic_relationship_mappings "
                "(source_table, target_table, mapping_json, schema_fingerprint) "
                "VALUES (:source, :target, :mapping, :fingerprint)"
            ), values)


def load_mapping(engine, source_table: str, target_table: str, catalog: dict[str, Any]) -> dict[str, Any] | None:
    ensure_mapping_store(engine)
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT mapping_json, schema_fingerprint, updated_at "
            "FROM semantic_relationship_mappings "
            "WHERE source_table = :source AND target_table = :target"
        ), {"source": source_table, "target": target_table}).mappings().first()
    if not row:
        return None
    mapping = json.loads(row["mapping_json"])
    stale = row["schema_fingerprint"] != catalog["fingerprint"]
    if not stale:
        try:
            mapping = validate_path_option(
                mapping, catalog["schema"], source_table, target_table
            )
        except ValueError:
            stale = True
    return {
        "source_table": source_table,
        "target_table": target_table,
        "mapping": mapping,
        "stale": stale,
        "updated_at": str(row["updated_at"]),
    }


def list_applicable_mappings(engine, table_names: list[str], catalog: dict[str, Any]) -> list[dict[str, Any]]:
    ensure_mapping_store(engine)
    with engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT source_table, target_table, mapping_json, schema_fingerprint "
            "FROM semantic_relationship_mappings"
        )).mappings().all()

    selected = set(table_names)
    mappings = []
    for row in rows:
        if row["source_table"] not in selected or row["target_table"] not in selected:
            continue
        if row["schema_fingerprint"] != catalog["fingerprint"]:
            continue
        try:
            mapping = validate_path_option(
                json.loads(row["mapping_json"]), catalog["schema"],
                row["source_table"], row["target_table"],
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        mappings.append(mapping)
    return mappings


def validate_sql_joins(sql: str, mappings: list[dict[str, Any]]) -> tuple[bool, str | None]:
    """Require every explicit SQL join to match a saved equality mapping."""
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError as exc:
        raise RuntimeError("SQLGlot is required to validate relationship joins.") from exc

    try:
        statements = sqlglot.parse(sql, read="postgres")
    except Exception as exc:
        return False, f"Could not parse generated SQL: {exc}"
    if len(statements) != 1 or statements[0] is None:
        return False, "Only a single SQL statement is allowed."
    query = statements[0]
    if not isinstance(query, exp.Select):
        return False, "Only a single SELECT statement is allowed."
    if query.args.get("with_") or query.find(exp.Subquery):
        return False, "CTEs and nested queries are not supported with strict mapping validation."

    joins = query.args.get("joins") or []
    if not joins:
        return True, None
    if not mappings:
        return False, "No saved relationship mapping is available for this JOIN."

    from_clause = query.args.get("from") or query.args.get("from_")
    base_table = from_clause.this if from_clause is not None else None
    if not isinstance(base_table, exp.Table):
        return False, "The query must use a named base table."
    if len(getattr(from_clause, "expressions", []) or []) > 1:
        return False, "Comma-separated table joins are not supported."

    table_aliases: dict[str, str] = {}
    for table in query.find_all(exp.Table):
        if table.args.get("db") or table.args.get("catalog"):
            return False, "Schema-qualified table names are not supported by mapping validation."
        table_aliases[table.alias_or_name.lower()] = table.name.lower()
        table_aliases[table.name.lower()] = table.name.lower()

    allowed = set()
    for mapping in mappings:
        for join in mapping.get("joins", []):
            left = (join["left_table"].lower(), join["left_column"].lower())
            right = (join["right_table"].lower(), join["right_column"].lower())
            allowed.add(tuple(sorted((left, right))))

    def table_for_column(column) -> str | None:
        table_reference = (column.table or "").lower()
        return table_aliases.get(table_reference)

    def conjunction_terms(expression):
        if isinstance(expression, exp.And):
            return conjunction_terms(expression.this) + conjunction_terms(expression.expression)
        return [expression]

    joined_tables = {base_table.name.lower()}
    for join in joins:
        target = join.this
        on_clause = join.args.get("on")
        if not isinstance(target, exp.Table) or on_clause is None:
            return False, "Every JOIN must target a named table and have an ON predicate."
        target_name = target.name.lower()
        approved_edge_found = False
        cross_table_conditions = 0
        for condition in conjunction_terms(on_clause):
            columns = list(condition.find_all(exp.Column))
            condition_tables = {
                table_for_column(column)
                for column in columns
                if table_for_column(column)
            }
            if not isinstance(condition, exp.EQ):
                if len(condition_tables) > 1:
                    return False, "Cross-table JOIN conditions must be saved equality predicates combined with AND."
                continue
            left_column = condition.this
            right_column = condition.expression
            if not isinstance(left_column, exp.Column) or not isinstance(right_column, exp.Column):
                if len(condition_tables) > 1:
                    return False, "Cross-table JOIN conditions must compare mapped columns directly."
                continue
            left_table = table_for_column(left_column)
            right_table = table_for_column(right_column)
            if not left_table or not right_table:
                if len(columns) > 1:
                    return False, "JOIN columns must be qualified by their table name or alias."
                continue
            if left_table == right_table:
                continue
            cross_table_conditions += 1
            left_pair = (left_table, left_column.name.lower())
            right_pair = (right_table, right_column.name.lower())
            edge = tuple(sorted((left_pair, right_pair)))
            if edge not in allowed:
                return False, (
                    f"JOIN predicate {left_table}.{left_column.name} = "
                    f"{right_table}.{right_column.name} is not in the saved mapping."
                )
            if target_name not in (left_table, right_table):
                return False, "JOIN predicates must connect the new table to an already joined table."
            other_table = right_table if left_table == target_name else left_table
            if other_table not in joined_tables:
                return False, "JOIN path is not contiguous with the saved mapping."
            approved_edge_found = True
        if not cross_table_conditions or not approved_edge_found:
            return False, "Every JOIN must contain a saved cross-table equality predicate."
        joined_tables.add(target_name)

    return True, None