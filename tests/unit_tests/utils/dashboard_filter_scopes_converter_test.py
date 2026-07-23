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

from typing import Any

from superset.models.slice import Slice
from superset.utils import json
from superset.utils.dashboard_filter_scopes_converter import (
    convert_filter_scopes,
    copy_filter_scopes,
)


def make_filter_box(slice_id: int, params: dict[str, Any]) -> Slice:
    return Slice(id=slice_id, params=json.dumps(params))


def test_convert_filter_scopes_time_fields() -> None:
    filter_box = make_filter_box(
        1,
        {
            "date_filter": True,
            "show_sqla_time_column": True,
            "show_sqla_time_granularity": True,
        },
    )
    scopes = convert_filter_scopes({}, [filter_box])

    assert set(scopes[1]) == {"__time_range", "__time_col", "__time_grain"}
    for field in scopes[1].values():
        assert field == {"scope": ["ROOT_ID"], "immune": []}


def test_convert_filter_scopes_from_filter_configs() -> None:
    filter_box = make_filter_box(
        2,
        {"filter_configs": [{"column": "gender"}, {"column": "name"}]},
    )
    scopes = convert_filter_scopes({}, [filter_box])

    assert set(scopes[2]) == {"gender", "name"}
    assert scopes[2]["gender"] == {"scope": ["ROOT_ID"], "immune": []}


def test_convert_filter_scopes_immune_by_id() -> None:
    filter_box = make_filter_box(3, {"filter_configs": [{"column": "gender"}]})
    scopes = convert_filter_scopes({"filter_immune_slices": [10, 11]}, [filter_box])

    assert sorted(scopes[3]["gender"]["immune"]) == [10, 11]


def test_convert_filter_scopes_immune_by_column() -> None:
    filter_box = make_filter_box(4, {"filter_configs": [{"column": "gender"}]})
    scopes = convert_filter_scopes(
        {"filter_immune_slice_fields": {"20": ["gender"], "21": ["name"]}},
        [filter_box],
    )

    # only the slice immune to the "gender" column is included
    assert scopes[4]["gender"]["immune"] == [20]


def test_convert_filter_scopes_combines_immune_sources() -> None:
    filter_box = make_filter_box(5, {"filter_configs": [{"column": "gender"}]})
    scopes = convert_filter_scopes(
        {
            "filter_immune_slices": [30],
            "filter_immune_slice_fields": {"31": ["gender"]},
        },
        [filter_box],
    )

    assert sorted(scopes[5]["gender"]["immune"]) == [30, 31]


def test_convert_filter_scopes_invalid_field_is_skipped() -> None:
    # a non-string column (e.g. ``None``) should not produce a scope entry
    filter_box = make_filter_box(6, {"filter_configs": [{"column": None}]})
    scopes = convert_filter_scopes({}, [filter_box])

    assert scopes == {}


def test_convert_filter_scopes_empty_params() -> None:
    filter_box = make_filter_box(7, {})
    scopes = convert_filter_scopes({}, [filter_box])

    # no filter fields -> the slice is omitted entirely
    assert scopes == {}


def test_convert_filter_scopes_handles_null_params() -> None:
    filter_box = Slice(id=8, params=None)
    scopes = convert_filter_scopes({}, [filter_box])

    assert scopes == {}


def test_copy_filter_scopes_remaps_ids() -> None:
    old_filter_scopes = {
        1: {"gender": {"scope": ["ROOT_ID"], "immune": [2, 3]}},
    }
    new_filter_scopes = copy_filter_scopes(
        {1: 100, 2: 200, 3: 300},
        old_filter_scopes,
    )

    assert set(new_filter_scopes) == {"100"}
    assert new_filter_scopes["100"]["gender"]["immune"] == [200, 300]


def test_copy_filter_scopes_drops_unmapped_filter() -> None:
    old_filter_scopes = {
        1: {"gender": {"scope": ["ROOT_ID"], "immune": []}},
    }
    # slice 1 has no mapping, so it is dropped entirely
    new_filter_scopes = copy_filter_scopes({99: 999}, old_filter_scopes)

    assert new_filter_scopes == {}


def test_copy_filter_scopes_drops_unmapped_immune_ids() -> None:
    old_filter_scopes = {
        1: {"gender": {"scope": ["ROOT_ID"], "immune": [2, 3]}},
    }
    # only slice 2 has a mapping; unmapped immune id 3 is filtered out
    new_filter_scopes = copy_filter_scopes({1: 100, 2: 200}, old_filter_scopes)

    assert new_filter_scopes["100"]["gender"]["immune"] == [200]
