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

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from codemie.rest_api.security.user import User
from codemie.service.monitoring.hedging_monitoring_service import HedgingMetricPayload, HedgingMonitoringService


@pytest.fixture
def mock_user():
    return User(id="user-1", name="Alice", username="alice@example.com")


@pytest.fixture
def mock_assistant():
    return SimpleNamespace(id="assistant-1", name="My Assistant", project="proj-1")


_DEFAULT_PAYLOAD_KWARGS = {
    "entry": "stream",
    "served_by": "fast_path",
    "fast_path_used": True,
    "fast_path_outcome": "hit",
    "winner": "fast_path",
    "terminal_reason": "completed",
    "tool_name": "prov/toolkit/search",
    "datasource_name": "my-ds",
    "timeout_ms": 200,
    "fast_path_latency_ms": 18,
    "total_latency_seconds": 0.42,
    "query": "What is X?",
    "conversation_id": "conv-1",
    "request_uuid": "req-1",
}


def _call(handler_user, handler_assistant, **overrides):
    payload_kwargs = {**_DEFAULT_PAYLOAD_KWARGS, **overrides}
    payload = HedgingMetricPayload(**payload_kwargs)
    HedgingMonitoringService.send_hedging_metric(
        user=handler_user,
        assistant=handler_assistant,
        payload=payload,
    )


@patch("codemie.service.monitoring.hedging_monitoring_service.send_log_metric")
def test_emits_request_hedging_metric_name(mock_send, mock_user, mock_assistant):
    _call(mock_user, mock_assistant)

    mock_send.assert_called_once()
    name, attributes = mock_send.call_args[0]
    assert name == "request_hedging"
    assert isinstance(attributes, dict)


@patch("codemie.service.monitoring.hedging_monitoring_service.send_log_metric")
def test_attributes_contain_core_dimensions(mock_send, mock_user, mock_assistant):
    _call(mock_user, mock_assistant)

    attrs = mock_send.call_args[0][1]
    assert attrs["assistant_id"] == "assistant-1"
    assert attrs["assistant_name"] == "My Assistant"
    assert attrs["project"] == "proj-1"
    assert attrs["tool_name"] == "prov/toolkit/search"
    assert attrs["repo_name"] == "my-ds"
    assert attrs["served_by"] == "fast_path"
    assert attrs["fast_path_used"] is True
    assert attrs["fast_path_outcome"] == "hit"
    assert attrs["winner"] == "fast_path"
    assert attrs["terminal_reason"] == "completed"
    assert attrs["entry"] == "stream"
    assert attrs["status"] == "success"
    assert attrs["fast_path_latency_ms"] == 18
    assert attrs["request_uuid"] == "req-1"
    assert attrs["conversation_id"] == "conv-1"


@patch("codemie.service.monitoring.hedging_monitoring_service.send_log_metric")
def test_query_truncated_to_200_chars_with_length(mock_send, mock_user, mock_assistant):
    long_query = "x" * 500
    _call(mock_user, mock_assistant, query=long_query)

    attrs = mock_send.call_args[0][1]
    assert attrs["query"] == "x" * 200
    assert attrs["query_length"] == 500


@patch("codemie.service.monitoring.hedging_monitoring_service.send_log_metric")
def test_none_query_and_datasource_are_safe(mock_send, mock_user, mock_assistant):
    _call(mock_user, mock_assistant, query=None, datasource_name=None)

    attrs = mock_send.call_args[0][1]
    assert attrs["query"] == ""
    assert attrs["query_length"] == 0
    assert attrs["repo_name"] == ""


@patch("codemie.service.monitoring.hedging_monitoring_service.send_log_metric")
def test_non_completed_terminal_reason_becomes_status(mock_send, mock_user, mock_assistant):
    _call(mock_user, mock_assistant, terminal_reason="client_disconnect")

    attrs = mock_send.call_args[0][1]
    assert attrs["status"] == "client_disconnect"


@patch("codemie.service.monitoring.hedging_monitoring_service.send_log_metric")
def test_timeout_fast_path_latency_is_none(mock_send, mock_user, mock_assistant):
    _call(mock_user, mock_assistant, fast_path_outcome="timeout", fast_path_latency_ms=None, served_by="agent")

    attrs = mock_send.call_args[0][1]
    assert attrs["fast_path_outcome"] == "timeout"
    assert attrs["fast_path_latency_ms"] is None
    assert attrs["served_by"] == "agent"


@patch(
    "codemie.service.monitoring.hedging_monitoring_service.send_log_metric",
    side_effect=RuntimeError("boom"),
)
def test_emit_never_raises(mock_send, mock_user, mock_assistant):
    # Analytics must never affect the request path.
    _call(mock_user, mock_assistant)
    mock_send.assert_called_once()
