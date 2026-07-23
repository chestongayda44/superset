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
"""Tests for the shared import dispatcher base command."""

from typing import Any

import pytest
from marshmallow.exceptions import ValidationError

from superset.commands.base import BaseCommand
from superset.commands.exceptions import CommandInvalidError
from superset.commands.importers.dispatcher import ImportDispatcherCommand
from superset.commands.importers.exceptions import IncorrectVersionError


class _RecordingCommand(BaseCommand):
    """Versioned command stub that records the args it was built with."""

    instances: list["_RecordingCommand"] = []
    exc: Exception | None = None

    def __init__(self, contents: dict[str, str], *args: Any, **kwargs: Any) -> None:
        self.contents = contents
        self.args = args
        self.kwargs = kwargs
        self.ran = False
        type(self).instances.append(self)

    def run(self) -> None:
        self.ran = True
        if self.exc is not None:
            raise self.exc

    def validate(self) -> None:
        pass


def _make_version(exc: Exception | None = None) -> type[_RecordingCommand]:
    return type("Version", (_RecordingCommand,), {"instances": [], "exc": exc})


def test_first_matching_version_wins() -> None:
    """The dispatcher stops at the first version that handles the contents."""
    first = _make_version(exc=IncorrectVersionError("nope"))
    second = _make_version()
    third = _make_version()

    class Dispatcher(ImportDispatcherCommand):
        command_versions = [first, second, third]

    Dispatcher({"a.yaml": "x"}).run()

    assert len(first.instances) == 1
    assert first.instances[0].ran
    assert len(second.instances) == 1
    assert second.instances[0].ran
    assert third.instances == []  # never reached


def test_contents_and_extra_args_forwarded() -> None:
    """contents plus *args/**kwargs are forwarded to each version."""
    version = _make_version()

    class Dispatcher(ImportDispatcherCommand):
        command_versions = [version]

    contents = {"a.yaml": "x"}
    Dispatcher(contents, "extra", overwrite=True).run()

    built = version.instances[0]
    assert built.contents is contents
    assert built.args == ("extra",)
    assert built.kwargs == {"overwrite": True}


def test_no_version_handles_contents() -> None:
    """A CommandInvalidError is raised when no version handles the file."""
    version = _make_version(exc=IncorrectVersionError("nope"))

    class Dispatcher(ImportDispatcherCommand):
        command_versions = [version]

    with pytest.raises(CommandInvalidError, match="Could not find a valid command"):
        Dispatcher({"a.yaml": "x"}).run()


def test_empty_command_versions() -> None:
    """The default empty ``command_versions`` raises CommandInvalidError."""
    with pytest.raises(CommandInvalidError):
        ImportDispatcherCommand({"a.yaml": "x"}).run()


@pytest.mark.parametrize("exc", [CommandInvalidError("bad"), ValidationError("bad")])
def test_validation_errors_propagate(exc: Exception) -> None:
    """Validation failures from the matched version are re-raised as-is."""
    version = _make_version(exc=exc)

    class Dispatcher(ImportDispatcherCommand):
        command_versions = [version]

    with pytest.raises(type(exc)):
        Dispatcher({"a.yaml": "x"}).run()


def test_unexpected_errors_propagate() -> None:
    """Unexpected errors bubble up instead of being swallowed."""
    version = _make_version(exc=RuntimeError("boom"))

    class Dispatcher(ImportDispatcherCommand):
        command_versions = [version]

    with pytest.raises(RuntimeError, match="boom"):
        Dispatcher({"a.yaml": "x"}).run()
