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

from pydantic import BaseModel, Field, model_validator


class HedgingToolDetails(BaseModel):
    name: str


class HedgingProviderToolDetails(BaseModel):
    provider_name: str
    toolkit_name: str
    tool_name: str
    datasource_name: str | None = Field(
        default=None,
        description=(
            "Name of the ProviderIndexInfo datasource to load configuration parameters from. "
            "Required for datasource-backed provider tools that expect DatasourceConfig fields "
            "(e.g. confluenceUrl, targetIndex) in configuration.parameters. "
            "When set, the datasource's provider_fields.base_params are decrypted and forwarded."
        ),
    )
    result_condition: str | None = Field(
        default=None,
        description=(
            "Python boolean expression evaluated against the raw provider tool result "
            "to decide whether the fast-path response is used. "
            "If the result is a dict, its keys are available as variables. "
            "Supports JSON-style literals: false/true/null (as well as Python False/True/None). "
            "Example: 'empty == false'. If None, any non-null result is accepted."
        ),
    )


class HedgingConfig(BaseModel):
    tool: HedgingToolDetails | None = Field(
        default=None,
        description="Internal CodeMieHedgeTool to use as the fast path.",
    )
    provider_tool: HedgingProviderToolDetails | None = Field(
        default=None,
        description="External DSP/Provider tool to use as the fast path.",
    )
    timeout_ms: int = Field(default=200, gt=0, description="Max ms to wait for fast path before falling through")
    input_mapping: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Maps tool parameter names to Jinja2 template strings resolved at request time. "
            "Available variables: {{query}}, {{conversation_id}}, {{user.id}}, {{user.name}}, "
            "{{user.username}}, {{user.email}}, {{user.token}}, {{headers.<name>}}, {{metadata.<key>}}. "
            "For internal tools: 'query' key maps to the query argument; other keys populate metadata. "
            "For provider tools: each key maps to a provider tool args_schema parameter name. "
            "⚠️ Security: {{user.token}} forwards the user's bearer token to the provider tool. "
            "Only use with trusted, internal providers."
        ),
    )
    output_field: str | None = Field(
        default=None,
        description=(
            "Dot-notation path to extract a specific field from the provider tool result "
            "(e.g. 'data.answer' or 'results.0.text'). Ignored for internal tools."
        ),
    )

    @model_validator(mode="after")
    def validate_tool_or_provider(self) -> "HedgingConfig":
        if self.tool is None and self.provider_tool is None:
            raise ValueError("Exactly one of 'tool' or 'provider_tool' must be specified")
        if self.tool is not None and self.provider_tool is not None:
            raise ValueError("Only one of 'tool' or 'provider_tool' can be specified, not both")
        return self
