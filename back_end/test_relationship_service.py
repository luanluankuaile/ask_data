import unittest

from sqlalchemy import create_engine, text

from back_end.relationship_service import (
    delete_relationship_edge,
    find_relationship_paths,
    merge_user_edited_relationships,
    load_mapping,
    load_relationship_catalog,
    load_schema_catalog,
    normalize_known_relationships,
    parse_llm_relationship_catalog,
    parse_llm_path_options,
    replace_relationship_edge,
    save_mapping,
    save_relationship_catalog,
    validate_path_option,
    validate_sql_joins,
)


class RelationshipServiceTests(unittest.TestCase):
    def setUp(self):
        self.schema = {
            "tables": {
                "student": {
                    "columns": {
                        "id": {"type": "VARCHAR", "primary_key": True},
                        "class_id": {"type": "INTEGER"},
                    },
                    "foreign_keys": [{
                        "constrained_columns": ["class_id"],
                        "referred_table": "class",
                        "referred_columns": ["id"],
                    }],
                },
                "class": {
                    "columns": {
                        "id": {"type": "SERIAL", "primary_key": True},
                        "course_id": {"type": "INTEGER"},
                    },
                    "foreign_keys": [],
                },
                "course_enrollment": {
                    "columns": {
                        "student_id": {"type": "VARCHAR"},
                        "course_id": {"type": "INTEGER"},
                    },
                    "foreign_keys": [],
                },
                "course": {
                    "columns": {"id": {"type": "INTEGER", "primary_key": True}},
                    "foreign_keys": [],
                },
            }
        }

    def test_normalizes_physical_and_valid_metadata_relationships(self):
        metadata = [
            {
                "table_name": "course_enrollment",
                "column_name": "student_id",
                "is_foreign_key": True,
                "foreign_key_reference": "student.id",
                "business_description": "Student taking the course",
            },
            {
                "table_name": "course_enrollment",
                "column_name": "student_id",
                "is_foreign_key": True,
                "foreign_key_reference": "students.id",
                "business_description": "Stale table name",
            },
        ]

        edges, warnings = normalize_known_relationships(self.schema, metadata)

        self.assertEqual(len(edges), 2)
        self.assertTrue(any("physical_fk" in edge["provenance"] for edge in edges))
        metadata_edge = next(edge for edge in edges if edge["left_table"] == "course_enrollment")
        self.assertEqual(metadata_edge["right_table"], "student")
        self.assertEqual(metadata_edge["provenance"], ["metadata_hint"])
        self.assertEqual(warnings, [])

    def test_validates_user_edited_mapping_columns(self):
        option = {
            "tables": ["course_enrollment", "student"],
            "joins": [{
                "left_table": "course_enrollment",
                "left_column": "student_id",
                "right_table": "student",
                "right_column": "id",
            }],
        }

        validated = validate_path_option(
            option, self.schema, "course_enrollment", "student"
        )

        self.assertEqual(validated["joins"][0]["left_column"], "student_id")

    def test_rejects_sql_expressions_and_incompatible_columns(self):
        option = {
            "tables": ["student", "course"],
            "joins": [{
                "left_table": "student",
                "left_column": "id OR 1=1",
                "right_table": "course",
                "right_column": "id",
            }],
        }

        with self.assertRaisesRegex(ValueError, "simple database identifiers"):
            validate_path_option(option, self.schema, "student", "course")

        option["joins"][0]["left_column"] = "id"
        with self.assertRaisesRegex(ValueError, "incompatible"):
            validate_path_option(option, self.schema, "student", "course")

    def test_loads_live_schema_and_metadata_from_sqlite(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE student (id VARCHAR PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE course_enrollment (student_id VARCHAR REFERENCES student(id))"))
            connection.execute(text(
                "CREATE TABLE schema_metadata (table_name TEXT, column_name TEXT, "
                "business_name TEXT, business_description TEXT, data_type TEXT, "
                "is_primary_key BOOLEAN, is_foreign_key BOOLEAN, "
                "foreign_key_reference TEXT, sample_values TEXT)"
            ))
            connection.execute(text(
                "CREATE TABLE semantic_relationship_catalog (catalog_id INTEGER PRIMARY KEY, "
                "relationships_json TEXT NOT NULL, schema_fingerprint TEXT NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO schema_metadata VALUES "
                "('course_enrollment', 'student_id', 'Student ID', 'Student key', "
                "'VARCHAR', 0, 1, 'students.id', NULL)"
            ))

        catalog = load_schema_catalog(engine)

        self.assertIn("student", catalog["schema"]["tables"])
        self.assertNotIn("schema_metadata", catalog["schema"]["tables"])
        self.assertNotIn("semantic_relationship_catalog", catalog["schema"]["tables"])
        self.assertEqual(catalog["warnings"], [])
        self.assertTrue(any(
            "physical_fk" in edge["provenance"]
            for edge in catalog["known_relationships"]
        ))

    def test_ai_options_are_validated_and_persisted_mapping_goes_stale(self):
        engine = create_engine("sqlite:///:memory:")
        schema = {
            "tables": {
                "student": {"columns": {"id": {"type": "VARCHAR", "unique": True}}, "foreign_keys": []},
                "course_enrollment": {"columns": {"student_id": {"type": "VARCHAR", "unique": False}}, "foreign_keys": []},
            }
        }
        catalog = {
            "schema": schema,
            "metadata": [],
            "known_relationships": [],
            "fingerprint": "initial",
        }
        content = '{"options": [' \
            '{"tables":["course_enrollment","student"],"joins":[{"left_table":"course_enrollment","left_column":"student_id","right_table":"student","right_column":"id"}],"confidence":0.8},' \
            '{"tables":["course_enrollment","student"],"joins":[{"left_table":"course_enrollment","left_column":"missing","right_table":"student","right_column":"id"}]}' \
            ']}'

        options = parse_llm_path_options(content, catalog, "course_enrollment", "student")
        self.assertEqual(len(options), 1)

        save_mapping(engine, "course_enrollment", "student", options[0], "initial")
        saved = load_mapping(engine, "course_enrollment", "student", catalog)
        self.assertFalse(saved["stale"])
        catalog["fingerprint"] = "changed"
        stale = load_mapping(engine, "course_enrollment", "student", catalog)
        self.assertTrue(stale["stale"])

    def test_sql_joins_must_match_saved_mapping(self):
        mapping = [{"joins": [{
            "left_table": "student",
            "left_column": "id",
            "right_table": "course_enrollment",
            "right_column": "student_id",
        }]}]

        valid, reason = validate_sql_joins(
            "SELECT s.id FROM student s JOIN course_enrollment ce "
            "ON s.id = ce.student_id",
            mapping,
        )
        self.assertTrue(valid, reason)

        valid, reason = validate_sql_joins(
            "SELECT s.id FROM student s JOIN course_enrollment ce "
            "ON s.id = ce.course_id",
            mapping,
        )
        self.assertFalse(valid)
        self.assertIn("not in the saved mapping", reason)

        valid, reason = validate_sql_joins(
            "SELECT s.id FROM student s JOIN course_enrollment ce "
            "ON s.id = ce.student_id OR s.id > ce.student_id",
            mapping,
        )
        self.assertFalse(valid)
        self.assertIn("combined with AND", reason)

        valid, reason = validate_sql_joins("SELECT 1;; SELECT 2", mapping)
        self.assertFalse(valid)
        self.assertIn("single SQL statement", reason)

    def test_global_model_builds_multiple_paths_and_rejects_unknown_edges(self):
        catalog = {
            "schema": self.schema,
            "known_relationships": [{
                "left_table": "student",
                "left_column": "class_id",
                "right_table": "class",
                "right_column": "id",
                "provenance": ["physical_fk"],
                "description": "Student is assigned to a class",
            }],
        }
        response = '{"relationships": [' \
            '{"left_table":"student","left_column":"id","right_table":"course_enrollment","right_column":"student_id","confidence":0.9,"rationale":"Enrollment belongs to a student"},' \
            '{"left_table":"course_enrollment","left_column":"course_id","right_table":"course","right_column":"id","confidence":0.9,"rationale":"Enrollment points to its course"},' \
            '{"left_table":"class","left_column":"course_id","right_table":"course","right_column":"id","confidence":0.6,"rationale":"Class curriculum"},' \
            '{"left_table":"student","left_column":"missing","right_table":"course","right_column":"id","confidence":1.0}' \
            ']}'

        relationships = parse_llm_relationship_catalog(response, catalog)
        paths = find_relationship_paths(catalog, relationships, "student", "course")

        self.assertEqual(len(paths), 2)
        self.assertTrue(all(len(path["joins"]) == 2 for path in paths))
        self.assertEqual(paths[0]["tables"], ["student", "course_enrollment", "course"])
        self.assertTrue(all(edge["provenance"] == "ai_inferred" for edge in relationships))

    def test_global_relationship_catalog_persists_with_staleness(self):
        engine = create_engine("sqlite:///:memory:")
        relationships = [{
            "left_table": "student",
            "left_column": "class_id",
            "right_table": "class",
            "right_column": "id",
            "provenance": "physical_fk",
        }]

        save_relationship_catalog(engine, relationships, "version-1")

        current = load_relationship_catalog(engine, "version-1")
        stale = load_relationship_catalog(engine, "version-2")
        self.assertFalse(current["stale"])
        self.assertTrue(stale["stale"])
        self.assertEqual(current["relationships"][0]["provenance"], "ai_inferred")

    def test_relationship_edge_can_be_manually_edited_and_validated(self):
        edges = [{
            "left_table": "student",
            "left_column": "class_id",
            "right_table": "class",
            "right_column": "id",
            "provenance": "physical_fk",
            "confidence": 1.0,
        }]
        original = {
            "left_table": "student",
            "left_column": "class_id",
            "right_table": "class",
            "right_column": "id",
        }
        edited = replace_relationship_edge(
            edges,
            self.schema,
            original,
            {"left_column": "class_id", "right_column": "course_id"},
        )

        self.assertEqual(len(edited), 1)
        self.assertEqual(edited[0]["provenance"], "user_edited")
        self.assertEqual(edited[0]["right_column"], "course_id")
        with self.assertRaisesRegex(ValueError, "incompatible"):
            replace_relationship_edge(
                edges,
                self.schema,
                original,
                {"left_column": "id", "right_column": "id"},
            )

    def test_manual_relationship_survives_ai_refresh(self):
        generated = [{
            "left_table": "student",
            "left_column": "class_id",
            "right_table": "class",
            "right_column": "id",
            "provenance": "ai_inferred",
            "confidence": 1.0,
        }]
        previous = [{
            "left_table": "student",
            "left_column": "class_id",
            "right_table": "class",
            "right_column": "course_id",
            "provenance": "user_edited",
            "confidence": 0.9,
        }]

        merged, warnings = merge_user_edited_relationships(generated, previous, self.schema)

        self.assertEqual(warnings, [])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["provenance"], "user_edited")
        self.assertEqual(merged[0]["right_column"], "course_id")

        previous[0]["right_column"] = "missing"
        merged, warnings = merge_user_edited_relationships(generated, previous, self.schema)
        self.assertTrue(any(edge["provenance"] == "ai_inferred" for edge in merged))
        self.assertEqual(len(warnings), 1)

    def test_deleted_relationship_is_hidden_and_suppressed_during_merge(self):
        edge = {
            "left_table": "student",
            "left_column": "class_id",
            "right_table": "class",
            "right_column": "id",
            "provenance": "ai_inferred",
            "confidence": 1.0,
        }
        deleted = delete_relationship_edge([edge], edge)
        self.assertEqual(deleted[0]["provenance"], "user_deleted")

        catalog = {"schema": self.schema}
        paths = find_relationship_paths(
            catalog,
            deleted,
            "student",
            "class",
        )
        self.assertEqual(paths, [])

        refreshed, warnings = merge_user_edited_relationships([edge], deleted, self.schema)
        self.assertEqual(warnings, [])
        self.assertEqual(len(refreshed), 1)
        self.assertEqual(refreshed[0]["provenance"], "user_deleted")

    def test_deleting_manual_override_suppresses_original_and_edited_edges(self):
        manual_edge = {
            "left_table": "student",
            "left_column": "class_id",
            "right_table": "class",
            "right_column": "course_id",
            "provenance": "user_edited",
            "overrides": {
                "left_table": "student",
                "left_column": "class_id",
                "right_table": "class",
                "right_column": "id",
            },
        }
        tombstone = delete_relationship_edge([manual_edge], manual_edge)
        ai_candidates = [
            {"left_table": "student", "left_column": "class_id", "right_table": "class", "right_column": "id", "provenance": "ai_inferred"},
            {"left_table": "student", "left_column": "class_id", "right_table": "class", "right_column": "course_id", "provenance": "ai_inferred"},
        ]

        merged, _ = merge_user_edited_relationships(ai_candidates, tombstone, self.schema)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["provenance"], "user_deleted")


if __name__ == "__main__":
    unittest.main()