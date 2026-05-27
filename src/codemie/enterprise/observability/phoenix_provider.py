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

"""Arize Phoenix observability provider.

Implements the ObservabilityProvider ABC and delegates all Phoenix-specific
logic to the codemie_enterprise.phoenix support modules (service, context
manager, helpers, observe).

Available when OBSERVABILITY_PROVIDER=phoenix and codemie_enterprise[phoenix]
is installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from codemie.configs import config, logger

from .base import ObservabilityProvider

if TYPE_CHECKING:
    from codemie_enterprise.phoenix.models import PhoenixTraceContext
    from codemie_enterprise.phoenix.service import PhoenixService


class PhoenixObservabilityProvider(ObservabilityProvider):
    """Arize Phoenix implementation of the ObservabilityProvider contract.

    Thin delegation wrapper — all Phoenix-specific logic lives in
    codemie_enterprise.phoenix (service, context_manager, helpers, observe).
    This class owns lifecycle, wires dependencies, and satisfies the ABC.
    """

    def __init__(self) -> None:
        from codemie_enterprise.phoenix.config import PhoenixConfig

        self._config: PhoenixConfig = PhoenixConfig(
            enabled=True,
            host=config.PHOENIX_HOST,
            project_name=config.PHOENIX_PROJECT_NAME,
            api_key=config.PHOENIX_API_KEY,
            batch_span_processor=config.PHOENIX_BATCH_SPAN_PROCESSOR,
        )
        self._service: PhoenixService | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def initialize(self) -> None:
        """Register OTEL tracer provider and install LangChain instrumentation."""
        from codemie_enterprise.phoenix.service import PhoenixService

        self._service = PhoenixService(self._config)
        self._service.initialize()

    def shutdown(self) -> None:
        """Flush pending spans and shut down the OTEL tracer provider."""
        if self._service is not None:
            self._service.shutdown()
            logger.info("Phoenix service shutdown complete")
        self._service = None

    # ── State ──────────────────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        """True if Phoenix was configured and initialized successfully."""
        return self._config.enabled and self._service is not None and self._service._initialized

    # ── Tracing surface ────────────────────────────────────────────────────────

    def get_callback_handler(self) -> None:
        """Always returns None — Phoenix uses OTEL auto-instrumentation, not callbacks."""
        return None

    def create_workflow_trace_context(
        self,
        execution_id: str,
        workflow_id: str | None = None,
        workflow_name: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
    ) -> PhoenixTraceContext | None:
        """Open a root OTEL span for a workflow and attach it to the OTEL context."""
        if not self.is_enabled():
            return None
        from codemie_enterprise.phoenix.context_manager import PhoenixContextManager

        return PhoenixContextManager.create_workflow_trace_context(
            execution_id=execution_id,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            user_id=user_id,
            session_id=session_id,
            tags=tags,
            tracer_provider=self._service.tracer_provider if self._service else None,
        )

    def get_workflow_trace_context(self, execution_id: str) -> PhoenixTraceContext | None:
        """Return the active PhoenixTraceContext for the given execution_id."""
        from codemie_enterprise.phoenix.context_manager import PhoenixContextManager

        return PhoenixContextManager.get_current_trace_context(execution_id)

    def clear_workflow_trace_context(self, execution_id: str) -> bool:
        """End the workflow span and detach OTEL context. Must be called in finally blocks."""
        from codemie_enterprise.phoenix.context_manager import PhoenixContextManager

        return PhoenixContextManager.clear_trace_context(execution_id)

    def build_agent_metadata(
        self,
        agent_name: str,
        conversation_id: str | None = None,
        llm_model: str | None = None,
        username: str | None = None,
        tags: list[str] | None = None,
        trace_context: Any | None = None,
    ) -> dict[str, Any]:
        """Build metadata dict for a LangChain agent run config."""
        from codemie_enterprise.phoenix.helpers import build_agent_metadata as _build
        from codemie_enterprise.phoenix.models import PhoenixTraceContext

        resolved_context = trace_context if isinstance(trace_context, PhoenixTraceContext) else None
        return _build(
            agent_name=agent_name,
            conversation_id=conversation_id,
            llm_model=llm_model,
            username=username,
            tags=tags,
            trace_context=resolved_context,
        )

    def should_trace_request(self, request_metadata: dict[str, Any] | None) -> bool:
        """Return True if this request should be traced.

        Checks provider availability, then optional per-request override via
        "observability_traces_enabled" metadata key.
        """
        if not self.is_enabled():
            return False
        if request_metadata is None:
            return True
        override = request_metadata.get("observability_traces_enabled")
        if override is not None:
            return bool(override)
        return True

    def make_observe_decorator(self) -> Any:
        """Return an OTEL span-based @observe decorator factory."""
        from codemie_enterprise.phoenix.observe import make_observe

        return make_observe(
            is_enabled=self.is_enabled,
            tracer_provider=self._service.tracer_provider if self._service else None,
        )
