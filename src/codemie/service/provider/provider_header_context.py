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

from typing import ClassVar

from pydantic import BaseModel, Field

from codemie.configs import config


class ProviderHeaderContext(BaseModel):
    """Context for building provider call headers with request and assistant metadata."""

    model_config = {"frozen": True}

    HEADERS: ClassVar[dict[str, str]] = {
        "CORRELATION_ID": "X-Correlation-Id",
        "CONVERSATION_ID": "X-Conversation-Id",
        "MESSAGE_ID": "X-Conversation-Message-Id",
        "ASSISTANT_ID": "X-Assistant-Id",
        "TEMPERATURE": "X-Assistant-Temperature",
        "TOP_P": "X-Assistant-Top-P",
        "LLM_MODEL": "X-Assistant-LLM-Model",
    }

    request_headers: dict[str, str] = Field(default_factory=dict)
    conversation_id: str | None = None
    history_index: int | None = None
    assistant_id: str | None = None
    llm_model: str | None = None
    temperature: float | None = None
    top_p: float | None = None

    def build(self) -> dict[str, str]:
        """Build provider call headers, filtering blocked request headers and merging assistant metadata."""
        blocked = {h.strip().lower() for h in config.FORWARDED_HEADERS_BLOCKLIST.split(",")}
        headers = {k: v for k, v in self.request_headers.items() if k.lower() not in blocked}
        mapping = {
            self.HEADERS["CONVERSATION_ID"]: self.conversation_id,
            self.HEADERS["MESSAGE_ID"]: self.history_index,
            self.HEADERS["ASSISTANT_ID"]: self.assistant_id,
            self.HEADERS["LLM_MODEL"]: self.llm_model,
            self.HEADERS["TEMPERATURE"]: self.temperature,
            self.HEADERS["TOP_P"]: self.top_p,
        }
        headers.update({k: str(v) for k, v in mapping.items() if v is not None})
        return {k: v for k, v in headers.items() if v}
