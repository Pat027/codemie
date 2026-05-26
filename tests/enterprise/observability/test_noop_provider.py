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

"""Tests for NoOpObservabilityProvider."""

from __future__ import annotations

from codemie.enterprise.observability.noop_provider import NoOpObservabilityProvider


class TestNoOpProviderLifecycle:
    def test_initialize_does_not_raise(self):
        provider = NoOpObservabilityProvider()
        provider.initialize()

    def test_shutdown_does_not_raise(self):
        provider = NoOpObservabilityProvider()
        provider.shutdown()

    def test_is_enabled_returns_false(self):
        provider = NoOpObservabilityProvider()
        assert provider.is_enabled() is False


class TestNoOpProviderCallbackHandler:
    def test_get_callback_handler_returns_none(self):
        provider = NoOpObservabilityProvider()
        assert provider.get_callback_handler() is None


class TestNoOpProviderWorkflowTracing:
    def test_create_workflow_trace_context_returns_none(self):
        provider = NoOpObservabilityProvider()
        result = provider.create_workflow_trace_context(
            execution_id="exec-1",
            workflow_id="wf-1",
            workflow_name="Test Workflow",
            user_id="user-1",
            session_id="session-1",
            tags=["tag1"],
        )
        assert result is None

    def test_get_workflow_trace_context_returns_none(self):
        provider = NoOpObservabilityProvider()
        assert provider.get_workflow_trace_context("exec-1") is None

    def test_clear_workflow_trace_context_returns_false(self):
        provider = NoOpObservabilityProvider()
        assert provider.clear_workflow_trace_context("exec-1") is False


class TestNoOpProviderMetadata:
    def test_build_agent_metadata_returns_empty_dict(self):
        provider = NoOpObservabilityProvider()
        result = provider.build_agent_metadata(
            agent_name="test-agent",
            conversation_id="conv-1",
            llm_model="gpt-4",
            username="user@example.com",
            tags=["tag1"],
            trace_context=None,
        )
        assert result == {}

    def test_should_trace_request_returns_false(self):
        provider = NoOpObservabilityProvider()
        assert provider.should_trace_request(None) is False
        assert provider.should_trace_request({}) is False
        assert provider.should_trace_request({"observability_traces_enabled": True}) is False


class TestNoOpProviderObserveDecorator:
    def test_make_observe_decorator_returns_noop(self):
        provider = NoOpObservabilityProvider()
        observe = provider.make_observe_decorator()

        @observe(name="test_fn")
        def my_function():
            return 42

        assert my_function() == 42

    def test_observe_decorator_without_args(self):
        provider = NoOpObservabilityProvider()
        observe = provider.make_observe_decorator()

        @observe()
        def my_function():
            return "hello"

        assert my_function() == "hello"

    def test_observe_decorator_with_positional_arg(self):
        provider = NoOpObservabilityProvider()
        observe = provider.make_observe_decorator()

        decorator = observe("my_name")

        def my_function():
            return "result"

        wrapped = decorator(my_function)
        assert wrapped is my_function
        assert wrapped() == "result"


class TestNoOpProviderWorkflowTracingMinimalArgs:
    def test_create_workflow_trace_context_with_required_args_only(self):
        provider = NoOpObservabilityProvider()
        result = provider.create_workflow_trace_context(
            execution_id="exec-1",
            workflow_id=None,
            workflow_name="Test",
            user_id=None,
        )
        assert result is None

    def test_build_agent_metadata_with_defaults(self):
        provider = NoOpObservabilityProvider()
        result = provider.build_agent_metadata(
            agent_name="agent",
            conversation_id="conv-1",
            llm_model="gpt-4",
        )
        assert result == {}
