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

"""Langfuse observability provider.

Thin delegation wrapper around the existing enterprise/langfuse/ adapter layer.
Contains no logic changes — all business logic remains in enterprise/langfuse/.
"""

from __future__ import annotations

from typing import Any

from codemie.configs import logger

from .base import ObservabilityProvider


class LangfuseObservabilityProvider(ObservabilityProvider):
    """Delegates all calls to the existing enterprise/langfuse/ adapter layer.

    This is a pure forwarding adapter — no logic lives here. All behavior
    is unchanged from the pre-abstraction implementation.
    """

    def __init__(self) -> None:
        self._service: Any = None

    def initialize(self) -> None:
        """Initialize the Langfuse service and register it as the global singleton."""
        from codemie.enterprise.langfuse.dependencies import (
            initialize_langfuse_from_config,
            set_global_langfuse_service,
        )

        self._service = initialize_langfuse_from_config()
        set_global_langfuse_service(self._service)

    def shutdown(self) -> None:
        """Flush pending traces, release resources, and clear the global singleton."""
        from codemie.enterprise.langfuse.dependencies import set_global_langfuse_service

        if self._service is not None:
            self._service.shutdown()
            logger.info("LangFuse service shutdown complete")
        set_global_langfuse_service(None)
        self._service = None

    def is_enabled(self) -> bool:
        from codemie.enterprise.langfuse import is_langfuse_enabled

        return is_langfuse_enabled()

    def get_callback_handler(self) -> Any | None:
        from codemie.enterprise.langfuse import get_langfuse_callback_handler

        return get_langfuse_callback_handler()

    def create_workflow_trace_context(
        self,
        execution_id: str,
        workflow_id: str | None,
        workflow_name: str,
        user_id: str | None,
        session_id: str | None = None,
        tags: list[str] | None = None,
    ) -> Any | None:
        from codemie.enterprise.langfuse import create_workflow_trace_context

        return create_workflow_trace_context(
            execution_id=execution_id,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            user_id=user_id,
            session_id=session_id,
            tags=tags,
        )

    def get_workflow_trace_context(self, execution_id: str) -> Any | None:
        from codemie.enterprise.langfuse import get_workflow_trace_context

        return get_workflow_trace_context(execution_id)

    def clear_workflow_trace_context(self, execution_id: str) -> bool:
        from codemie.enterprise.langfuse import clear_workflow_trace_context

        return clear_workflow_trace_context(execution_id)

    def build_agent_metadata(
        self,
        agent_name: str,
        conversation_id: str,
        llm_model: str,
        username: str | None = None,
        tags: list[str] | None = None,
        trace_context: Any | None = None,
    ) -> dict:
        from codemie.enterprise.langfuse import build_agent_metadata_with_workflow_context

        return build_agent_metadata_with_workflow_context(
            agent_name=agent_name,
            conversation_id=conversation_id,
            llm_model=llm_model,
            username=username,
            tags=tags,
            trace_context=trace_context,
        )

    def should_trace_request(self, request_metadata: dict | None) -> bool:
        """Determine if tracing should be enabled for this request.

        Priority: HAS_LANGFUSE + is_langfuse_enabled() > request metadata override.
        Also checks that the callback handler is available (service initialized).
        """
        from codemie.configs import config
        from codemie.enterprise.langfuse import get_langfuse_callback_handler, is_langfuse_enabled

        if not is_langfuse_enabled():
            return False

        # Handler must be available (service initialized); otherwise tracing is a no-op
        if get_langfuse_callback_handler() is None:
            return False

        # Per-request override: check both Langfuse-specific and generic keys
        trace_setting = None
        if request_metadata:
            trace_setting = request_metadata.get("langfuse_traces_enabled")
            if trace_setting is None:
                trace_setting = request_metadata.get("observability_traces_enabled")

        if trace_setting is not None:
            logger.info(f"Per-request trace override: {trace_setting}")
            if isinstance(trace_setting, str):
                return trace_setting.strip().lower() == "true"
            if isinstance(trace_setting, bool):
                return trace_setting
            logger.warning("Unsupported type for traces_enabled metadata key; defaulting to False.")
            return False

        return config.LANGFUSE_TRACES

    def get_trace_context(
        self,
        trace_name: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
    ):
        """
        Return a context manager that sets trace attributes for the current invocation.

        Delegates to get_langfuse_trace_context(); returns nullcontext() if Langfuse
        is disabled.
        """
        from codemie.enterprise.langfuse.dependencies import get_langfuse_trace_context

        return get_langfuse_trace_context(
            trace_name=trace_name,
            user_id=user_id,
            session_id=session_id,
            tags=tags,
        )

    def make_observe_decorator(self) -> Any:
        """Return the existing Langfuse @observe decorator from loader.py."""
        from codemie.enterprise.loader import observe

        return observe
