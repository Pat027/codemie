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

"""Tests for LangfuseObservabilityProvider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from codemie.enterprise.observability.langfuse_provider import LangfuseObservabilityProvider


@pytest.fixture
def provider():
    return LangfuseObservabilityProvider()


class TestLangfuseProviderLifecycle:
    def test_initialize_creates_and_registers_service(self, provider):
        mock_service = MagicMock()
        with (
            patch(
                "codemie.enterprise.langfuse.dependencies.initialize_langfuse_from_config",
                return_value=mock_service,
            ) as mock_init,
            patch("codemie.enterprise.langfuse.dependencies.set_global_langfuse_service") as mock_set,
        ):
            provider.initialize()

            mock_init.assert_called_once()
            mock_set.assert_called_once_with(mock_service)
            assert provider._service is mock_service

    def test_shutdown_flushes_and_clears_service(self, provider):
        mock_service = MagicMock()
        provider._service = mock_service

        with patch("codemie.enterprise.langfuse.dependencies.set_global_langfuse_service") as mock_set:
            provider.shutdown()

            mock_service.shutdown.assert_called_once()
            mock_set.assert_called_once_with(None)
            assert provider._service is None

    def test_shutdown_without_service_does_not_raise(self, provider):
        with patch("codemie.enterprise.langfuse.dependencies.set_global_langfuse_service"):
            provider.shutdown()


class TestLangfuseProviderIsEnabled:
    def test_returns_true_when_langfuse_enabled(self, provider, monkeypatch):
        monkeypatch.setattr("codemie.enterprise.langfuse.dependencies.HAS_LANGFUSE", True)
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", True)
        assert provider.is_enabled() is True

    def test_returns_false_when_has_langfuse_false(self, provider, monkeypatch):
        monkeypatch.setattr("codemie.enterprise.langfuse.dependencies.HAS_LANGFUSE", False)
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", True)
        assert provider.is_enabled() is False

    def test_returns_false_when_traces_disabled(self, provider, monkeypatch):
        monkeypatch.setattr("codemie.enterprise.langfuse.dependencies.HAS_LANGFUSE", True)
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", False)
        assert provider.is_enabled() is False


class TestLangfuseProviderCallbackHandler:
    def test_returns_handler_when_available(self, provider, monkeypatch):
        mock_handler = MagicMock()
        mock_service = MagicMock()
        mock_service.get_callback_handler.return_value = mock_handler

        monkeypatch.setattr("codemie.enterprise.langfuse.dependencies.HAS_LANGFUSE", True)
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", True)
        monkeypatch.setattr(
            "codemie.enterprise.langfuse.dependencies._global_langfuse_service",
            mock_service,
        )

        result = provider.get_callback_handler()
        assert result is mock_handler

    def test_returns_none_when_langfuse_disabled(self, provider, monkeypatch):
        monkeypatch.setattr("codemie.enterprise.langfuse.dependencies.HAS_LANGFUSE", False)
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", False)

        assert provider.get_callback_handler() is None

    def test_returns_none_when_service_not_initialized(self, provider, monkeypatch):
        monkeypatch.setattr("codemie.enterprise.langfuse.dependencies.HAS_LANGFUSE", True)
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", True)
        monkeypatch.setattr(
            "codemie.enterprise.langfuse.dependencies._global_langfuse_service",
            None,
        )

        assert provider.get_callback_handler() is None


class TestLangfuseProviderWorkflowTracing:
    def test_create_workflow_trace_context_delegates(self, provider):
        mock_ctx = MagicMock()
        with patch(
            "codemie.enterprise.langfuse.create_workflow_trace_context",
            return_value=mock_ctx,
        ) as mock_create:
            result = provider.create_workflow_trace_context(
                execution_id="exec-1",
                workflow_id="wf-1",
                workflow_name="Test",
                user_id="user-1",
                session_id="sess-1",
                tags=["tag1"],
            )

            mock_create.assert_called_once_with(
                execution_id="exec-1",
                workflow_id="wf-1",
                workflow_name="Test",
                user_id="user-1",
                session_id="sess-1",
                tags=["tag1"],
            )
            assert result is mock_ctx

    def test_get_workflow_trace_context_delegates(self, provider):
        mock_ctx = MagicMock()
        with patch(
            "codemie.enterprise.langfuse.get_workflow_trace_context",
            return_value=mock_ctx,
        ) as mock_get:
            result = provider.get_workflow_trace_context("exec-1")
            mock_get.assert_called_once_with("exec-1")
            assert result is mock_ctx

    def test_clear_workflow_trace_context_delegates(self, provider):
        with patch(
            "codemie.enterprise.langfuse.clear_workflow_trace_context",
            return_value=True,
        ) as mock_clear:
            result = provider.clear_workflow_trace_context("exec-1")
            mock_clear.assert_called_once_with("exec-1")
            assert result is True


class TestLangfuseProviderAgentMetadata:
    def test_build_agent_metadata_delegates(self, provider):
        expected = {"callbacks": [MagicMock()], "run_name": "test-agent"}
        with patch(
            "codemie.enterprise.langfuse.build_agent_metadata_with_workflow_context",
            return_value=expected,
        ) as mock_build:
            result = provider.build_agent_metadata(
                agent_name="test-agent",
                conversation_id="conv-1",
                llm_model="gpt-4",
                username="user@example.com",
                tags=["tag1"],
                trace_context=None,
            )

            mock_build.assert_called_once_with(
                agent_name="test-agent",
                conversation_id="conv-1",
                llm_model="gpt-4",
                username="user@example.com",
                tags=["tag1"],
                trace_context=None,
            )
            assert result == expected


class TestLangfuseProviderShouldTraceRequest:
    def test_returns_false_when_langfuse_disabled(self, provider, monkeypatch):
        monkeypatch.setattr("codemie.enterprise.langfuse.dependencies.HAS_LANGFUSE", False)
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", False)

        assert provider.should_trace_request(None) is False

    def test_returns_false_when_handler_is_none(self, provider, monkeypatch):
        monkeypatch.setattr("codemie.enterprise.langfuse.dependencies.HAS_LANGFUSE", True)
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", True)
        monkeypatch.setattr(
            "codemie.enterprise.langfuse.dependencies._global_langfuse_service",
            None,
        )

        assert provider.should_trace_request(None) is False

    def test_returns_config_value_when_no_override(self, provider, monkeypatch):
        monkeypatch.setattr("codemie.enterprise.langfuse.dependencies.HAS_LANGFUSE", True)
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", True)

        mock_service = MagicMock()
        mock_service.get_callback_handler.return_value = MagicMock()
        monkeypatch.setattr(
            "codemie.enterprise.langfuse.dependencies._global_langfuse_service",
            mock_service,
        )

        assert provider.should_trace_request(None) is True
        assert provider.should_trace_request({}) is True

    def test_per_request_override_langfuse_key(self, provider, monkeypatch):
        monkeypatch.setattr("codemie.enterprise.langfuse.dependencies.HAS_LANGFUSE", True)
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", True)

        mock_service = MagicMock()
        mock_service.get_callback_handler.return_value = MagicMock()
        monkeypatch.setattr(
            "codemie.enterprise.langfuse.dependencies._global_langfuse_service",
            mock_service,
        )

        assert provider.should_trace_request({"langfuse_traces_enabled": False}) is False
        assert provider.should_trace_request({"langfuse_traces_enabled": True}) is True

    def test_per_request_override_generic_key(self, provider, monkeypatch):
        monkeypatch.setattr("codemie.enterprise.langfuse.dependencies.HAS_LANGFUSE", True)
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", True)

        mock_service = MagicMock()
        mock_service.get_callback_handler.return_value = MagicMock()
        monkeypatch.setattr(
            "codemie.enterprise.langfuse.dependencies._global_langfuse_service",
            mock_service,
        )

        assert provider.should_trace_request({"observability_traces_enabled": False}) is False
        assert provider.should_trace_request({"observability_traces_enabled": True}) is True

    def test_per_request_override_string_values(self, provider, monkeypatch):
        monkeypatch.setattr("codemie.enterprise.langfuse.dependencies.HAS_LANGFUSE", True)
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", True)

        mock_service = MagicMock()
        mock_service.get_callback_handler.return_value = MagicMock()
        monkeypatch.setattr(
            "codemie.enterprise.langfuse.dependencies._global_langfuse_service",
            mock_service,
        )

        assert provider.should_trace_request({"langfuse_traces_enabled": "true"}) is True
        assert provider.should_trace_request({"langfuse_traces_enabled": "false"}) is False
        assert provider.should_trace_request({"langfuse_traces_enabled": "True"}) is True

    def test_per_request_override_unsupported_type_returns_false(self, provider, monkeypatch):
        monkeypatch.setattr("codemie.enterprise.langfuse.dependencies.HAS_LANGFUSE", True)
        monkeypatch.setattr("codemie.configs.config.LANGFUSE_TRACES", True)

        mock_service = MagicMock()
        mock_service.get_callback_handler.return_value = MagicMock()
        monkeypatch.setattr(
            "codemie.enterprise.langfuse.dependencies._global_langfuse_service",
            mock_service,
        )

        assert provider.should_trace_request({"langfuse_traces_enabled": 123}) is False


class TestLangfuseProviderObserveDecorator:
    def test_make_observe_decorator_delegates_to_loader(self, provider):
        with patch("codemie.enterprise.loader.observe") as mock_observe:
            result = provider.make_observe_decorator()
            assert result is mock_observe


class TestLangfuseProviderBuildAgentMetadataAdditional:
    def test_build_agent_metadata_forwards_non_none_trace_context(self, provider):
        trace_ctx = MagicMock()
        expected = {"run_name": "agent", "metadata": {"trace_id": "abc"}}
        with patch(
            "codemie.enterprise.langfuse.build_agent_metadata_with_workflow_context",
            return_value=expected,
        ) as mock_build:
            result = provider.build_agent_metadata(
                agent_name="agent",
                conversation_id="conv-1",
                llm_model="gpt-4",
                trace_context=trace_ctx,
            )

            call_kwargs = mock_build.call_args[1]
            assert call_kwargs["trace_context"] is trace_ctx
            assert result == expected

    def test_build_agent_metadata_with_defaults(self, provider):
        with patch(
            "codemie.enterprise.langfuse.build_agent_metadata_with_workflow_context",
            return_value={},
        ) as mock_build:
            provider.build_agent_metadata(
                agent_name="agent",
                conversation_id="conv-1",
                llm_model="gpt-4",
            )

            call_kwargs = mock_build.call_args[1]
            assert call_kwargs["username"] is None
            assert call_kwargs["tags"] is None
            assert call_kwargs["trace_context"] is None


class TestLangfuseProviderShutdownAdditional:
    def test_shutdown_logs_info_when_service_present(self, provider):
        mock_service = MagicMock()
        provider._service = mock_service

        with (
            patch("codemie.enterprise.langfuse.dependencies.set_global_langfuse_service"),
            patch("codemie.enterprise.observability.langfuse_provider.logger") as mock_logger,
        ):
            provider.shutdown()

        mock_logger.info.assert_called_once_with("LangFuse service shutdown complete")
