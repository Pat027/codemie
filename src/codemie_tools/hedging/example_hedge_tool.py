# Copyright 2026 EPAM Systems, Inc. ("EPAM")
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import random
from typing import Any

from codemie_tools.base.codemie_hedge_tool import CodeMieHedgeTool, HedgeToolResult


class ExampleHedgeTool(CodeMieHedgeTool):
    name: str = "example_hedge_tool"
    description: str = "Example hedgeable tool for testing. Randomly returns an empty or non-empty result."

    def execute(self, query: str, metadata: dict[str, Any] | None = None) -> HedgeToolResult:
        if random.random() < 0.5:
            return HedgeToolResult(empty=True)
        return HedgeToolResult(empty=False, data=f"Fast response for query: {query!r}")
