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

"""No-op observability provider.

Used when OBSERVABILITY_PROVIDER=none or no enterprise package is installed.
All methods are safe, zero-overhead no-ops.
"""

from __future__ import annotations

from typing import Any

from .base import ObservabilityProvider


class NoOpObservabilityProvider(ObservabilityProvider):
    """Disables all observability. All methods are safe no-ops with zero overhead."""

    def initialize(self) -> None:
        # Intentional no-op: this provider disables all observability, so no initialization is needed.
        pass

    def shutdown(self) -> None:
        # Intentional no-op: this provider disables all observability, so no cleanup is needed.
        pass

    def is_enabled(self) -> bool:
        return False

    def get_callback_handler(self) -> Any | None:
        return None

    def create_workflow_trace_context(
        self,
        execution_id: str,
        workflow_id: str | None,
        workflow_name: str,
        user_id: str | None,
        session_id: str | None = None,
        tags: list[str] | None = None,
    ) -> Any | None:
        return None

    def get_workflow_trace_context(self, execution_id: str) -> Any | None:
        return None

    def clear_workflow_trace_context(self, execution_id: str) -> bool:
        return False

    def build_agent_metadata(
        self,
        agent_name: str,
        conversation_id: str,
        llm_model: str,
        username: str | None = None,
        tags: list[str] | None = None,
        trace_context: Any | None = None,
    ) -> dict:
        return {}

    def should_trace_request(self, request_metadata: dict | None) -> bool:
        return False

    def make_observe_decorator(self) -> Any:
        def observe(*args: Any, **kwargs: Any) -> Any:
            return lambda fn: fn

        return observe
