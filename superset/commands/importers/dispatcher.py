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

import logging
from collections.abc import Sequence
from typing import Any, Callable

from marshmallow.exceptions import ValidationError

from superset.commands.base import BaseCommand
from superset.commands.exceptions import CommandInvalidError
from superset.commands.importers.exceptions import IncorrectVersionError

logger = logging.getLogger(__name__)


class ImportDispatcherCommand(BaseCommand):
    """
    Base command that dispatches an import to versioned import commands.

    Subclasses declare ``command_versions`` with the import command classes to
    try, ordered from most to least specific. Unversioned (``v0``) commands
    should come last because their files are not versioned. The first version
    that handles the contents wins.
    """

    # ordered list of versioned import commands to attempt
    command_versions: Sequence[Callable[..., BaseCommand]] = ()

    def __init__(self, contents: dict[str, str], *args: Any, **kwargs: Any):
        self.contents = contents
        self.args = args
        self.kwargs = kwargs

    def run(self) -> None:
        # iterate over all commands until we find a version that can
        # handle the contents
        for version in self.command_versions:
            command = version(self.contents, *self.args, **self.kwargs)
            try:
                command.run()
                return
            except IncorrectVersionError:
                logger.debug("File not handled by command, skipping")
            except (CommandInvalidError, ValidationError):
                # found right version, but file is invalid
                logger.info("Command failed validation")
                raise
            except Exception:
                # validation succeeded but something went wrong
                logger.exception("Error running import command")
                raise

        raise CommandInvalidError("Could not find a valid command to import file")

    def validate(self) -> None:
        pass
