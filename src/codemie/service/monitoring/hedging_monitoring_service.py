# Copyright 2026 EPAM Systems, Inc. (“EPAM”)
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

from dataclasses import dataclass
from typing import Optional

from codemie.configs import logger
from codemie.core.dependecies import get_current_project
from codemie.rest_api.models.assistant import Assistant
from codemie.rest_api.security.user import User
from codemie.service.monitoring.base_monitoring_service import BaseMonitoringService, send_log_metric
from codemie.service.monitoring.metrics_constants import MetricsAttributes

# Max chars of the triggering query kept in the metric. Bounds PII exposure and metric size
# while still letting dashboards show which query drove a given outcome.
_QUERY_MAX_LEN = 200


@dataclass(frozen=True)
class HedgingMetricPayload:
    """All hedging-specific dimensions for one request-hedging metric emission."""

    entry: str  # stream | sync
    served_by: str  # fast_path | agent | unknown
    fast_path_used: bool
    fast_path_outcome: str  # hit | miss | error | timeout
    winner: str  # fast_path | agent | none | n/a
    terminal_reason: str  # completed | client_disconnect | exception
    tool_name: str
    datasource_name: Optional[str]
    timeout_ms: int
    fast_path_latency_ms: Optional[int]  # None on timeout
    total_latency_seconds: float
    query: Optional[str]
    conversation_id: Optional[str]
    request_uuid: str


class HedgingMonitoringService(BaseMonitoringService):
    """Emits one structured analytics metric per request-hedging request.

    The metric is shipped as a JSON-in-message log line (``send_log_metric``) so it lands in
    the same Kibana pipeline as ``conversation_assistant_usage`` — exposed under
    ``message.metric_name`` / ``message.attributes.*``.

    It intentionally uses ``send_log_metric`` rather than ``send_count_metric``: the triggering
    ``query`` is unbounded user text and must not become a Prometheus/OTel counter label.

    Two dimensions are tracked independently because they differ in the streaming race:
      * ``fast_path_outcome`` — the fast-path attempt result (hit/miss/error/timeout).
      * ``served_by`` — which path actually answered the user. A fast-path ``hit`` that finishes
        after the timeout loses the race and is discarded, so the agent serves
        (``fast_path_outcome=hit`` with ``served_by=agent``).
    """

    HEDGING_METRIC = "request_hedging"

    @classmethod
    def send_hedging_metric(
        cls,
        *,
        user: User,
        assistant: Assistant,
        payload: HedgingMetricPayload,
    ) -> None:
        """Build the ``request_hedging`` attribute set and emit it as a log metric.

        Never raises: analytics must not affect the request path.
        """
        try:
            attributes = {
                MetricsAttributes.USER_ID: user.id,
                MetricsAttributes.USER_NAME: user.name,
                MetricsAttributes.USER_EMAIL: user.username,
                MetricsAttributes.ASSISTANT_ID: assistant.id,
                MetricsAttributes.ASSISTANT_NAME: assistant.name,
                MetricsAttributes.PROJECT: get_current_project(fallback=assistant.project),
                MetricsAttributes.TOOL_NAME: payload.tool_name,
                MetricsAttributes.REPO_NAME: payload.datasource_name or "",
                MetricsAttributes.CONVERSATION_ID: payload.conversation_id or "",
                MetricsAttributes.REQUEST_UUID: payload.request_uuid,
                MetricsAttributes.EXECUTION_TIME: payload.total_latency_seconds,
                MetricsAttributes.STATUS: "success"
                if payload.terminal_reason == "completed"
                else payload.terminal_reason,
                # hedging-specific dimensions (plain string keys, like the conversation
                # metric's "mark" / "action")
                "entry": payload.entry,
                "served_by": payload.served_by,
                "fast_path_used": payload.fast_path_used,
                "fast_path_outcome": payload.fast_path_outcome,
                "winner": payload.winner,
                "terminal_reason": payload.terminal_reason,
                "timeout_ms": payload.timeout_ms,
                "fast_path_latency_ms": payload.fast_path_latency_ms,
                "query": (payload.query or "")[:_QUERY_MAX_LEN],
                "query_length": len(payload.query or ""),
            }
            send_log_metric(cls.HEDGING_METRIC, attributes)
        except Exception as e:
            logger.warning(f"[HEDGED] failed to emit hedging metric: {e}")
