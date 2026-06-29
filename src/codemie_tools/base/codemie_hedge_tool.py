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

from __future__ import annotations

from abc import abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from codemie_tools.base.codemie_tool import CodeMieTool


class HedgeToolInput(BaseModel):
    query: str = Field(description="The user query to search or retrieve")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional context for the tool")


class HedgeToolResult(BaseModel):
    empty: bool
    data: Any = None


class CodeMieHedgeTool(CodeMieTool):
    is_hedgeable: ClassVar[bool] = True
    args_schema: type[BaseModel] = HedgeToolInput

    def _limit_output_content(self, output: Any) -> tuple[Any, int]:
        if not isinstance(output, HedgeToolResult) or output.empty or output.data is None:
            return (output, 0)
        limited_data, token_count = super()._limit_output_content(output.data)
        return (HedgeToolResult(empty=False, data=limited_data), token_count)

    def _post_process_output_content(self, output: Any, *args, **kwargs) -> str:
        if isinstance(output, HedgeToolResult):
            return output.model_dump_json()
        return HedgeToolResult(empty=False, data=output).model_dump_json()

    @abstractmethod
    def execute(self, query: str, metadata: dict[str, Any] | None = None) -> HedgeToolResult:
        pass
