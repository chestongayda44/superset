# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from superset.constants import TimeGrain
from superset.db_engine_specs.base import BaseEngineSpec, DatabaseCategory
from superset.db_engine_specs.lib import (
    ADVANCED_FEATURES,
    BASIC_FEATURES,
    calculate_support_level,
    DATABASE_DETAILS,
    diagnose,
    format_markdown_table,
    generate_feature_tables,
    generate_focused_table,
    generate_table,
    generate_yaml_docs,
    get_documentation_metadata,
    get_name,
    has_custom_method,
    infer_category,
    NICE_TO_HAVE_FEATURES,
)


class CustomSpec(BaseEngineSpec):
    """A spec that overrides a couple of methods for ``has_custom_method``."""

    engine = "custom"
    engine_name = "Custom DB"

    @classmethod
    def mask_encrypted_extra(cls, encrypted_extra: str | None) -> str | None:
        return encrypted_extra


class NamelessSpec(BaseEngineSpec):
    """A spec without an ``engine_name`` so ``get_name`` falls back to engine."""

    engine = "nameless"
    engine_name = None


def test_has_custom_method_detects_override() -> None:
    assert has_custom_method(CustomSpec, "mask_encrypted_extra") is True


def test_has_custom_method_false_when_inherited() -> None:
    # ``BaseEngineSpec`` itself does not override its own method.
    assert has_custom_method(BaseEngineSpec, "mask_encrypted_extra") is False


def test_has_custom_method_false_when_missing() -> None:
    assert has_custom_method(CustomSpec, "not_a_real_method") is False


def test_get_name_prefers_engine_name() -> None:
    assert get_name(CustomSpec) == "Custom DB"


def test_get_name_falls_back_to_engine() -> None:
    assert get_name(NamelessSpec) == "nameless"


def test_format_markdown_table() -> None:
    table = format_markdown_table(["A", "B"], [[1, 2], ["x", "y"]])
    assert table == ("| A | B |\n| --- | --- |\n| 1 | 2 |\n| x | y |")


def test_format_markdown_table_no_rows() -> None:
    table = format_markdown_table(["A", "B"], [])
    assert table == "| A | B |\n| --- | --- |"


def test_generate_focused_table_basic() -> None:
    info: dict[str, dict[str, Any]] = {
        "Beta DB": {"joins": True},
        "Alpha DB": {"joins": False},
    }
    table, excluded = generate_focused_table(info, ["joins"], ["JOINs"])
    assert excluded == []
    # databases are sorted alphabetically by default
    assert table == (
        "| Database | JOINs |\n| --- | --- |\n| Alpha DB | False |\n| Beta DB | True |"
    )


def test_generate_focused_table_missing_key_defaults_to_empty() -> None:
    info: dict[str, dict[str, Any]] = {"DB": {}}
    table, _ = generate_focused_table(info, ["joins"], ["JOINs"])
    assert table == "| Database | JOINs |\n| --- | --- |\n| DB |  |"


def test_generate_focused_table_preserve_order() -> None:
    info: dict[str, dict[str, Any]] = {
        "Zeta": {"joins": True},
        "Alpha": {"joins": True},
    }
    table, _ = generate_focused_table(info, ["joins"], ["JOINs"], preserve_order=True)
    rows = table.splitlines()
    assert rows[2] == "| Zeta | True |"
    assert rows[3] == "| Alpha | True |"


def test_generate_focused_table_filter_fn_excludes() -> None:
    info: dict[str, dict[str, Any]] = {
        "Keep": {"joins": True},
        "Drop": {"joins": False},
    }
    table, excluded = generate_focused_table(
        info,
        ["joins"],
        ["JOINs"],
        filter_fn=lambda db_info: db_info["joins"],
    )
    assert excluded == ["Drop"]
    assert "Keep" in table
    assert "Drop" not in table


def test_generate_focused_table_all_filtered_out() -> None:
    info: dict[str, dict[str, Any]] = {"Drop": {"joins": False}}
    table, excluded = generate_focused_table(
        info,
        ["joins"],
        ["JOINs"],
        filter_fn=lambda db_info: db_info["joins"],
    )
    assert table == ""
    assert excluded == ["Drop"]


def test_generate_focused_table_value_extractor() -> None:
    info: dict[str, dict[str, Any]] = {"DB": {"joins": True}}
    table, _ = generate_focused_table(
        info,
        ["joins"],
        ["JOINs"],
        value_extractor=lambda db_info, key: "yes" if db_info[key] else "no",
    )
    assert "| DB | yes |" in table


def test_calculate_support_level_empty_keys() -> None:
    assert calculate_support_level({}, []) == "Not supported"


def test_calculate_support_level_none() -> None:
    assert calculate_support_level({"a": False, "b": False}, ["a", "b"]) == (
        "Not supported"
    )


def test_calculate_support_level_partial() -> None:
    assert calculate_support_level({"a": True, "b": False}, ["a", "b"]) == "Partial"


def test_calculate_support_level_full() -> None:
    assert calculate_support_level({"a": True, "b": True}, ["a", "b"]) == "Supported"


def test_calculate_support_level_time_grains() -> None:
    db_info = {"time_grains": {"DAY": True, "WEEK": False}}
    keys = ["time_grains.DAY", "time_grains.WEEK"]
    assert calculate_support_level(db_info, keys) == "Partial"


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Amazon Redshift", DatabaseCategory.CLOUD_AWS),
        ("AWS Athena", DatabaseCategory.CLOUD_AWS),
        ("Google BigQuery", DatabaseCategory.CLOUD_GCP),
        ("Azure Synapse", DatabaseCategory.CLOUD_AZURE),
        ("Microsoft SQL Server", DatabaseCategory.CLOUD_AZURE),
        ("Snowflake", DatabaseCategory.CLOUD_DATA_WAREHOUSES),
        ("Databricks", DatabaseCategory.CLOUD_DATA_WAREHOUSES),
        ("Apache Druid", DatabaseCategory.APACHE_PROJECTS),
        ("Apache Hive", DatabaseCategory.APACHE_PROJECTS),
        ("PostgreSQL", DatabaseCategory.TRADITIONAL_RDBMS),
        ("MySQL", DatabaseCategory.TRADITIONAL_RDBMS),
        ("ClickHouse", DatabaseCategory.ANALYTICAL_DATABASES),
        ("Vertica", DatabaseCategory.ANALYTICAL_DATABASES),
        ("Elasticsearch", DatabaseCategory.SEARCH_NOSQL),
        ("Couchbase", DatabaseCategory.SEARCH_NOSQL),
        ("Trino", DatabaseCategory.QUERY_ENGINES),
        ("Presto", DatabaseCategory.QUERY_ENGINES),
        ("Something Unknown", DatabaseCategory.OTHER),
    ],
)
def test_infer_category(name: str, expected: str) -> None:
    assert infer_category(name) == expected


def test_get_documentation_metadata_with_metadata_and_category() -> None:
    class SpecWithMeta(BaseEngineSpec):
        engine = "withmeta"
        metadata = {  # type: ignore[typeddict-unknown-key]
            "category": "Custom Category",
            "pypi_packages": ["foo"],
        }

    result = get_documentation_metadata(SpecWithMeta, "With Meta")
    assert result["category"] == "Custom Category"
    assert result["pypi_packages"] == ["foo"]
    # a copy is returned, not the class attribute itself
    assert result is not SpecWithMeta.metadata


def test_get_documentation_metadata_infers_missing_category() -> None:
    class SpecNoCategory(BaseEngineSpec):
        engine = "nocategory"
        metadata = {"pypi_packages": ["bar"]}

    result = get_documentation_metadata(SpecNoCategory, "Amazon Redshift")
    assert result["category"] == DatabaseCategory.CLOUD_AWS
    assert result["pypi_packages"] == ["bar"]


def test_get_documentation_metadata_fallback() -> None:
    class SpecNoMeta(BaseEngineSpec):
        engine = "nometa"
        sqlalchemy_uri_placeholder = "nometa://user:password@host/db"

    result = get_documentation_metadata(SpecNoMeta, "Foo Bar")
    assert result["pypi_packages"] == []
    assert result["connection_string"] == "nometa://user:password@host/db"
    assert result["category"] == DatabaseCategory.OTHER


def test_diagnose_structure() -> None:
    from superset.db_engine_specs.sqlite import SqliteEngineSpec

    output = diagnose(SqliteEngineSpec)

    # every time grain has a boolean flag
    assert set(output["time_grains"]) == {tg.name for tg in TimeGrain}
    assert all(isinstance(v, bool) for v in output["time_grains"].values())

    # descriptive/feature keys are all present
    for key in DATABASE_DETAILS:
        assert key in output
    for key in {**BASIC_FEATURES, **NICE_TO_HAVE_FEATURES, **ADVANCED_FEATURES}:
        assert key in output

    assert output["module"] == SqliteEngineSpec.__module__
    assert output["limit_method"] == SqliteEngineSpec.limit_method.value
    assert 0 <= output["score"] <= output["max_score"]


def test_diagnose_max_score_is_stable() -> None:
    from superset.db_engine_specs.sqlite import SqliteEngineSpec

    output = diagnose(SqliteEngineSpec)
    expected_max = len(TimeGrain) + 10 * (
        len(BASIC_FEATURES) + len(NICE_TO_HAVE_FEATURES) + len(ADVANCED_FEATURES)
    )
    assert output["max_score"] == expected_max


def test_generate_table() -> None:
    rows = generate_table()
    assert rows[0][0] == "Feature"
    assert rows[1][0] == "Module"
    # the last row is the aggregated score for each database
    assert rows[-1][0] == "Score"
    # every row has the same number of columns as the header
    width = len(rows[0])
    assert all(len(row) == width for row in rows)


def test_generate_feature_tables() -> None:
    output = generate_feature_tables()
    assert "### Feature Overview" in output
    assert "### Database Information" in output
    assert "### SQL Capabilities" in output
    assert "### Time Grains – Common" in output
    # markdown separator row is present
    assert "| --- |" in output


def test_generate_yaml_docs_returns_dict() -> None:
    docs = generate_yaml_docs()
    assert isinstance(docs, dict)
    assert docs, "expected at least one documented engine spec"
    for name, data in docs.items():
        assert data["engine_name"] == name
        assert "documentation" in data
        assert "score" in data
        break


def test_generate_yaml_docs_writes_files(tmp_path: Path) -> None:
    docs = generate_yaml_docs(str(tmp_path))

    index_file = tmp_path / "_index.yaml"
    assert index_file.exists()

    written = list(tmp_path.glob("*.yaml"))
    # one file per engine spec, plus the combined index
    assert len(written) == len(docs) + 1

    with open(index_file) as f:
        loaded = yaml.safe_load(f)
    assert set(loaded) == set(docs)
