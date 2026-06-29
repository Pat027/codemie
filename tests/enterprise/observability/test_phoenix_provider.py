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

"""Tests for PhoenixObservabilityProvider."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_phoenix_enterprise():
    """Mock codemie_enterprise.phoenix modules so tests work without the package."""
    phoenix_module = ModuleType("codemie_enterprise.phoenix")
    phoenix_config_module = ModuleType("codemie_enterprise.phoenix.config")
    phoenix_service_module = ModuleType("codemie_enterprise.phoenix.service")
    phoenix_context_module = ModuleType("codemie_enterprise.phoenix.context_manager")
    phoenix_helpers_module = ModuleType("codemie_enterprise.phoenix.helpers")
    phoenix_models_module = ModuleType("codemie_enterprise.phoenix.models")
    phoenix_observe_module = ModuleType("codemie_enterprise.phoenix.observe")

    mock_phoenix_config = MagicMock(name="PhoenixConfig")
    phoenix_config_module.PhoenixConfig = mock_phoenix_config

    mock_service_cls = MagicMock(name="PhoenixService")
    phoenix_service_module.PhoenixService = mock_service_cls

    mock_context_manager = MagicMock(name="PhoenixContextManager")
    phoenix_context_module.PhoenixContextManager = mock_context_manager

    phoenix_helpers_module.build_agent_metadata = MagicMock(name="build_agent_metadata")

    class _FakePhoenixTraceContext:
        pass

    phoenix_models_module.PhoenixTraceContext = _FakePhoenixTraceContext

    phoenix_observe_module.make_observe = MagicMock(name="make_observe")

    modules = {
        "codemie_enterprise": ModuleType("codemie_enterprise"),
        "codemie_enterprise.phoenix": phoenix_module,
        "codemie_enterprise.phoenix.config": phoenix_config_module,
        "codemie_enterprise.phoenix.service": phoenix_service_module,
        "codemie_enterprise.phoenix.context_manager": phoenix_context_module,
        "codemie_enterprise.phoenix.helpers": phoenix_helpers_module,
        "codemie_enterprise.phoenix.models": phoenix_models_module,
        "codemie_enterprise.phoenix.observe": phoenix_observe_module,
    }

    with patch.dict(sys.modules, modules):
        yield {
            "PhoenixConfig": mock_phoenix_config,
            "PhoenixService": mock_service_cls,
            "PhoenixContextManager": mock_context_manager,
            "build_agent_metadata": phoenix_helpers_module.build_agent_metadata,
            "PhoenixTraceContext": _FakePhoenixTraceContext,
            "make_observe": phoenix_observe_module.make_observe,
        }


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr("codemie.configs.config.PHOENIX_HOST", "http://test:6006")
    monkeypatch.setattr("codemie.configs.config.PHOENIX_PROJECT_NAME", "test-project")
    monkeypatch.setattr("codemie.configs.config.PHOENIX_API_KEY", "test-key")
    monkeypatch.setattr("codemie.configs.config.PHOENIX_BATCH_SPAN_PROCESSOR", True)

    from codemie.enterprise.observability.phoenix_provider import PhoenixObservabilityProvider

    return PhoenixObservabilityProvider()


class TestPhoenixProviderLifecycle:
    def test_initialize_creates_service(self, provider, _mock_phoenix_enterprise):
        mock_service_cls = _mock_phoenix_enterprise["PhoenixService"]
        mock_instance = MagicMock()
        mock_service_cls.return_value = mock_instance

        provider.initialize()

        mock_service_cls.assert_called_once()
        mock_instance.initialize.assert_called_once()
        assert provider._service is mock_instance

    def test_shutdown_calls_service_shutdown(self, provider):
        mock_service = MagicMock()
        provider._service = mock_service

        provider.shutdown()

        mock_service.shutdown.assert_called_once()
        assert provider._service is None

    def test_shutdown_without_service_does_not_raise(self, provider):
        provider._service = None
        provider.shutdown()


class TestPhoenixProviderIsEnabled:
    def test_returns_false_when_service_not_initialized(self, provider):
        provider._service = None
        assert provider.is_enabled() is False

    def test_returns_false_when_service_not_initialized_flag(self, provider):
        mock_service = MagicMock()
        mock_service.tracer_provider = None
        provider._service = mock_service
        assert provider.is_enabled() is False

    def test_returns_true_when_service_initialized(self, provider):
        mock_service = MagicMock()
        mock_service._initialized = True
        provider._service = mock_service
        provider._config.enabled = True
        assert provider.is_enabled() is True


class TestPhoenixProviderCallbackHandler:
    def test_always_returns_none(self, provider):
        assert provider.get_callback_handler() is None


class TestPhoenixProviderWorkflowTracing:
    def test_create_workflow_trace_context_when_disabled(self, provider):
        provider._service = None
        result = provider.create_workflow_trace_context(
            execution_id="exec-1",
            workflow_id="wf-1",
            workflow_name="Test",
            user_id="user-1",
        )
        assert result is None

    def test_create_workflow_trace_context_delegates(self, provider, _mock_phoenix_enterprise):
        mock_service = MagicMock()
        mock_service._initialized = True
        mock_service.tracer_provider = MagicMock()
        provider._service = mock_service
        provider._config.enabled = True

        mock_ctx = MagicMock()
        _mock_phoenix_enterprise["PhoenixContextManager"].create_workflow_trace_context.return_value = mock_ctx

        result = provider.create_workflow_trace_context(
            execution_id="exec-1",
            workflow_id="wf-1",
            workflow_name="Test Workflow",
            user_id="user-1",
            session_id="sess-1",
            tags=["tag1"],
        )

        _mock_phoenix_enterprise["PhoenixContextManager"].create_workflow_trace_context.assert_called_once_with(
            execution_id="exec-1",
            workflow_id="wf-1",
            workflow_name="Test Workflow",
            user_id="user-1",
            session_id="sess-1",
            tags=["tag1"],
            tracer_provider=mock_service.tracer_provider,
        )
        assert result is mock_ctx

    def test_get_workflow_trace_context_delegates(self, provider, _mock_phoenix_enterprise):
        mock_ctx = MagicMock()
        _mock_phoenix_enterprise["PhoenixContextManager"].get_current_trace_context.return_value = mock_ctx

        result = provider.get_workflow_trace_context("exec-1")

        _mock_phoenix_enterprise["PhoenixContextManager"].get_current_trace_context.assert_called_once_with("exec-1")
        assert result is mock_ctx

    def test_clear_workflow_trace_context_delegates(self, provider, _mock_phoenix_enterprise):
        _mock_phoenix_enterprise["PhoenixContextManager"].clear_trace_context.return_value = True

        result = provider.clear_workflow_trace_context("exec-1")

        _mock_phoenix_enterprise["PhoenixContextManager"].clear_trace_context.assert_called_once_with("exec-1")
        assert result is True


class TestPhoenixProviderAgentMetadata:
    def test_build_agent_metadata_delegates_with_none_context(self, provider, _mock_phoenix_enterprise):
        expected = {"run_name": "test-agent", "metadata": {}}
        _mock_phoenix_enterprise["build_agent_metadata"].return_value = expected

        result = provider.build_agent_metadata(
            agent_name="test-agent",
            conversation_id="conv-1",
            llm_model="gpt-4",
            username="user@example.com",
            tags=["tag1"],
            trace_context=None,
        )

        _mock_phoenix_enterprise["build_agent_metadata"].assert_called_once_with(
            agent_name="test-agent",
            conversation_id="conv-1",
            llm_model="gpt-4",
            username="user@example.com",
            tags=["tag1"],
            trace_context=None,
        )
        assert result == expected

    def test_build_agent_metadata_passes_phoenix_trace_context(self, provider, _mock_phoenix_enterprise):
        phoenix_trace_context_cls = _mock_phoenix_enterprise["PhoenixTraceContext"]
        trace_ctx = phoenix_trace_context_cls()

        _mock_phoenix_enterprise["build_agent_metadata"].return_value = {}

        provider.build_agent_metadata(
            agent_name="test-agent",
            conversation_id="conv-1",
            llm_model="gpt-4",
            trace_context=trace_ctx,
        )

        call_kwargs = _mock_phoenix_enterprise["build_agent_metadata"].call_args[1]
        assert call_kwargs["trace_context"] is trace_ctx

    def test_build_agent_metadata_non_phoenix_context_resolved_to_none(self, provider, _mock_phoenix_enterprise):
        _mock_phoenix_enterprise["build_agent_metadata"].return_value = {}

        provider.build_agent_metadata(
            agent_name="test-agent",
            conversation_id="conv-1",
            llm_model="gpt-4",
            trace_context="not-a-phoenix-context",
        )

        call_kwargs = _mock_phoenix_enterprise["build_agent_metadata"].call_args[1]
        assert call_kwargs["trace_context"] is None


class TestPhoenixProviderShouldTraceRequest:
    def test_returns_false_when_disabled(self, provider):
        provider._service = None
        assert provider.should_trace_request(None) is False

    def test_returns_true_when_enabled_no_metadata(self, provider):
        mock_service = MagicMock()
        mock_service._initialized = True
        provider._service = mock_service
        provider._config.enabled = True

        assert provider.should_trace_request(None) is True

    def test_returns_true_when_enabled_empty_metadata(self, provider):
        mock_service = MagicMock()
        mock_service._initialized = True
        provider._service = mock_service
        provider._config.enabled = True

        assert provider.should_trace_request({}) is True

    def test_per_request_override_false(self, provider):
        mock_service = MagicMock()
        mock_service._initialized = True
        provider._service = mock_service
        provider._config.enabled = True

        assert provider.should_trace_request({"observability_traces_enabled": False}) is False

    def test_per_request_override_true(self, provider):
        mock_service = MagicMock()
        mock_service._initialized = True
        provider._service = mock_service
        provider._config.enabled = True

        assert provider.should_trace_request({"observability_traces_enabled": True}) is True


class TestPhoenixProviderObserveDecorator:
    def test_make_observe_delegates(self, provider, _mock_phoenix_enterprise):
        mock_service = MagicMock()
        mock_service.tracer_provider = MagicMock()
        provider._service = mock_service

        mock_decorator = MagicMock()
        _mock_phoenix_enterprise["make_observe"].return_value = mock_decorator

        result = provider.make_observe_decorator()

        _mock_phoenix_enterprise["make_observe"].assert_called_once()
        assert result is mock_decorator

    def test_make_observe_passes_none_tracer_provider_when_service_none(self, provider, _mock_phoenix_enterprise):
        provider._service = None

        mock_decorator = MagicMock()
        _mock_phoenix_enterprise["make_observe"].return_value = mock_decorator

        result = provider.make_observe_decorator()

        call_kwargs = _mock_phoenix_enterprise["make_observe"].call_args[1]
        assert call_kwargs["tracer_provider"] is None
        assert result is mock_decorator


class TestPhoenixProviderIsEnabledAdditional:
    def test_returns_false_when_config_disabled(self, provider):
        mock_service = MagicMock()
        mock_service._initialized = True
        provider._service = mock_service
        provider._config.enabled = False

        assert provider.is_enabled() is False


class TestPhoenixProviderShouldTraceRequestAdditional:
    def test_falsy_non_none_override_returns_false(self, provider):
        mock_service = MagicMock()
        mock_service._initialized = True
        provider._service = mock_service
        provider._config.enabled = True

        assert provider.should_trace_request({"observability_traces_enabled": 0}) is False

    def test_unrelated_metadata_keys_ignored(self, provider):
        mock_service = MagicMock()
        mock_service._initialized = True
        provider._service = mock_service
        provider._config.enabled = True

        assert provider.should_trace_request({"unrelated_key": False}) is True


class TestPhoenixProviderShutdownLogging:
    def test_shutdown_logs_when_service_present(self, provider):
        from unittest.mock import patch

        mock_service = MagicMock()
        provider._service = mock_service

        with patch("codemie.enterprise.observability.phoenix_provider.logger") as mock_logger:
            provider.shutdown()

        mock_logger.info.assert_called_once_with("Phoenix service shutdown complete")
