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

"""Unit tests for HedgingToolService."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from codemie.clients.provider.client.models.tool_invocation_response import ToolInvocationResponse
from codemie.rest_api.models.hedging import HedgingConfig, HedgingProviderToolDetails, HedgingToolDetails
from codemie.service.tools.hedging_tool_service import HedgingToolService
from codemie.workflows.utils.safe_eval import SafeEvalError
from codemie_tools.base.codemie_hedge_tool import HedgeToolResult


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_toolkit(tool_name: str, tool_class=None):
    """Build a mock toolkit with one tool entry."""
    tool = Mock()
    tool.name = tool_name
    tool.tool_class = tool_class or Mock()
    toolkit = Mock()
    toolkit.tools = [tool]
    return toolkit


def _resp(status: str = "Completed", result=None) -> ToolInvocationResponse:
    return ToolInvocationResponse(status=status, result=result)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_user():
    user = Mock()
    user.id = "user-1"
    user.name = "Alice"
    user.username = "alice"
    user.email = "alice@example.com"
    user.auth_token = "tok"
    return user


@pytest.fixture
def mock_request():
    r = Mock()
    r.text = "hello"
    r.conversation_id = "conv-1"
    r.metadata = {"k": "v"}
    return r


@pytest.fixture
def provider_hedging_cfg():
    return HedgingConfig(
        provider_tool=HedgingProviderToolDetails(
            provider_name="my-provider",
            toolkit_name="search",
            tool_name="semantic_search",
        ),
        input_mapping={"query": "{{query}}"},
        output_field="results.0",
        timeout_ms=300,
    )


# ---------------------------------------------------------------------------
# TestGetToolDefinition
# ---------------------------------------------------------------------------


class TestGetToolDefinition:
    def test_returns_tool_class_when_found(self):
        expected_class = Mock()
        toolkit = _make_toolkit("my_tool", tool_class=expected_class)

        with patch("codemie.service.tools.hedging_tool_service.toolkit_provider") as mock_tp:
            mock_tp.get_hedgeable_toolkits.return_value = [toolkit]
            result = HedgingToolService.get_tool_definition("my_tool")

        assert result is expected_class

    def test_returns_none_when_not_found(self):
        toolkit = _make_toolkit("other_tool")

        with patch("codemie.service.tools.hedging_tool_service.toolkit_provider") as mock_tp:
            mock_tp.get_hedgeable_toolkits.return_value = [toolkit]
            result = HedgingToolService.get_tool_definition("my_tool")

        assert result is None

    def test_searches_multiple_toolkits(self):
        expected_class = Mock()
        toolkit_a = _make_toolkit("tool_a")
        toolkit_b = _make_toolkit("tool_b", tool_class=expected_class)

        with patch("codemie.service.tools.hedging_tool_service.toolkit_provider") as mock_tp:
            mock_tp.get_hedgeable_toolkits.return_value = [toolkit_a, toolkit_b]
            result = HedgingToolService.get_tool_definition("tool_b")

        assert result is expected_class

    def test_returns_none_when_registry_is_empty(self):
        with patch("codemie.service.tools.hedging_tool_service.toolkit_provider") as mock_tp:
            mock_tp.get_hedgeable_toolkits.return_value = []
            result = HedgingToolService.get_tool_definition("any_tool")

        assert result is None


# ---------------------------------------------------------------------------
# TestInstantiate
# ---------------------------------------------------------------------------


class TestInstantiate:
    def test_returns_instance_when_found(self):
        mock_instance = Mock()
        mock_class = Mock(return_value=mock_instance)
        cfg = HedgingConfig(tool=HedgingToolDetails(name="my_tool"))

        with patch.object(HedgingToolService, "get_tool_definition", return_value=mock_class):
            result = HedgingToolService.instantiate(cfg)

        assert result is mock_instance
        mock_class.assert_called_once_with()

    def test_raises_value_error_when_not_found(self):
        cfg = HedgingConfig(tool=HedgingToolDetails(name="missing_tool"))

        with patch.object(HedgingToolService, "get_tool_definition", return_value=None):
            with pytest.raises(ValueError, match="missing_tool"):
                HedgingToolService.instantiate(cfg)

    def test_raises_value_error_message_includes_registry_hint(self):
        cfg = HedgingConfig(tool=HedgingToolDetails(name="unknown"))

        with patch.object(HedgingToolService, "get_tool_definition", return_value=None):
            with pytest.raises(ValueError, match="not found in registry"):
                HedgingToolService.instantiate(cfg)


# ---------------------------------------------------------------------------
# TestBuildTemplateContext
# ---------------------------------------------------------------------------


class TestBuildTemplateContext:
    def test_all_fields_populated(self, mock_request, mock_user):
        ctx = HedgingToolService.build_template_context(mock_request, mock_user, {"x-tenant": "acme"})

        assert ctx["query"] == "hello"
        assert ctx["conversation_id"] == "conv-1"
        assert ctx["user"]["id"] == "user-1"
        assert ctx["user"]["name"] == "Alice"
        assert ctx["user"]["username"] == "alice"
        assert ctx["user"]["email"] == "alice@example.com"
        assert ctx["user"]["token"] == "tok"
        assert ctx["headers"] == {"x-tenant": "acme"}
        assert ctx["metadata"] == {"k": "v"}

    def test_none_text_becomes_empty_string(self, mock_user):
        r = Mock()
        r.text = None
        r.conversation_id = "conv-1"
        r.metadata = {}

        ctx = HedgingToolService.build_template_context(r, mock_user, {})

        assert ctx["query"] == ""

    def test_none_conversation_id_becomes_empty_string(self, mock_user):
        r = Mock()
        r.text = "q"
        r.conversation_id = None
        r.metadata = {}

        ctx = HedgingToolService.build_template_context(r, mock_user, {})

        assert ctx["conversation_id"] == ""

    def test_none_auth_token_becomes_empty_string(self, mock_request):
        user = Mock()
        user.id = "u"
        user.name = "Bob"
        user.username = "bob"
        user.email = "bob@example.com"
        user.auth_token = None

        ctx = HedgingToolService.build_template_context(mock_request, user, {})

        assert ctx["user"]["token"] == ""

    def test_none_metadata_becomes_empty_dict(self, mock_user):
        r = Mock()
        r.text = "q"
        r.conversation_id = "c"
        r.metadata = None

        ctx = HedgingToolService.build_template_context(r, mock_user, {})

        assert ctx["metadata"] == {}

    def test_headers_passed_through(self, mock_request, mock_user):
        headers = {"x-foo": "bar", "x-baz": "qux"}
        ctx = HedgingToolService.build_template_context(mock_request, mock_user, headers)

        assert ctx["headers"] is headers


# ---------------------------------------------------------------------------
# TestEvaluateResultCondition
# ---------------------------------------------------------------------------


class TestEvaluateResultCondition:
    def test_simple_comparison_true(self):
        assert HedgingToolService._evaluate_result_condition({"score": 10}, "score > 5") is True

    def test_simple_comparison_false(self):
        assert HedgingToolService._evaluate_result_condition({"score": 3}, "score > 5") is False

    def test_json_style_true_alias(self):
        assert HedgingToolService._evaluate_result_condition({"active": True}, "active == true") is True

    def test_json_style_false_alias(self):
        assert HedgingToolService._evaluate_result_condition({"active": False}, "active == false") is True

    def test_json_style_null_alias(self):
        assert HedgingToolService._evaluate_result_condition({"val": None}, "val == null") is True

    def test_non_dict_result_wrapped_as_result_key(self):
        assert HedgingToolService._evaluate_result_condition(42, "result == 42") is True

    def test_non_dict_string_wrapped(self):
        assert HedgingToolService._evaluate_result_condition("ok", 'result == "ok"') is True

    def test_safe_eval_error_returns_false_and_logs(self):
        with (
            patch("codemie.service.tools.hedging_tool_service.safe_eval", side_effect=SafeEvalError("bad")),
            patch("codemie.service.tools.hedging_tool_service.logger") as mock_logger,
        ):
            result = HedgingToolService._evaluate_result_condition({"x": 1}, "x.__class__")

        assert result is False
        mock_logger.warning.assert_called_once()

    def test_syntax_error_returns_false_and_logs(self):
        with (
            patch("codemie.service.tools.hedging_tool_service.safe_eval", side_effect=SyntaxError("oops")),
            patch("codemie.service.tools.hedging_tool_service.logger") as mock_logger,
        ):
            result = HedgingToolService._evaluate_result_condition({}, "invalid syntax !!!")

        assert result is False
        mock_logger.warning.assert_called_once()

    def test_generic_exception_returns_false_and_logs(self):
        with (
            patch("codemie.service.tools.hedging_tool_service.safe_eval", side_effect=RuntimeError("boom")),
            patch("codemie.service.tools.hedging_tool_service.logger") as mock_logger,
        ):
            result = HedgingToolService._evaluate_result_condition({}, "anything")

        assert result is False
        mock_logger.warning.assert_called_once()

    def test_equality_with_string_value(self):
        assert HedgingToolService._evaluate_result_condition({"status": "ok"}, 'status == "ok"') is True


# ---------------------------------------------------------------------------
# TestExtractProviderResult
# ---------------------------------------------------------------------------


class TestExtractProviderResult:
    def test_non_completed_status_returns_empty(self):
        r = HedgingToolService._extract_provider_result(_resp(status="Error", result="x"), None)
        assert r.empty is True

    def test_none_result_returns_empty(self):
        r = HedgingToolService._extract_provider_result(_resp(result=None), None)
        assert r.empty is True

    def test_completed_with_result_no_field_returns_data(self):
        r = HedgingToolService._extract_provider_result(_resp(result="answer"), None)
        assert r.empty is False
        assert r.data == "answer"

    def test_result_condition_true_returns_data(self):
        with patch.object(HedgingToolService, "_evaluate_result_condition", return_value=True):
            r = HedgingToolService._extract_provider_result(_resp(result={"score": 9}), None, "score > 5")
        assert r.empty is False

    def test_result_condition_false_returns_empty(self):
        with patch.object(HedgingToolService, "_evaluate_result_condition", return_value=False):
            r = HedgingToolService._extract_provider_result(_resp(result={"score": 1}), None, "score > 5")
        assert r.empty is True

    def test_result_condition_none_skips_evaluation(self):
        # No condition → no call to _evaluate_result_condition, data returned directly.
        with patch.object(HedgingToolService, "_evaluate_result_condition") as mock_eval:
            r = HedgingToolService._extract_provider_result(_resp(result="direct"), None, None)
        mock_eval.assert_not_called()
        assert r.empty is False
        assert r.data == "direct"

    def test_output_field_nested_dict(self):
        r = HedgingToolService._extract_provider_result(_resp(result={"data": {"answer": "42"}}), "data.answer")
        assert r.empty is False
        assert r.data == "42"

    def test_output_field_list_index(self):
        r = HedgingToolService._extract_provider_result(_resp(result={"items": ["first", "second"]}), "items.0")
        assert r.data == "first"

    def test_output_field_missing_key_returns_empty(self):
        r = HedgingToolService._extract_provider_result(_resp(result={"data": {}}), "data.answer")
        assert r.empty is True

    def test_output_field_bad_list_index_returns_empty(self):
        r = HedgingToolService._extract_provider_result(_resp(result={"items": ["only"]}), "items.5")
        assert r.empty is True

    def test_output_field_on_scalar_intermediate_returns_empty(self):
        # result["a"] is a string; cannot traverse further to "b".
        r = HedgingToolService._extract_provider_result(_resp(result={"a": "flat"}), "a.b")
        assert r.empty is True

    def test_extracted_value_none_returns_empty(self):
        r = HedgingToolService._extract_provider_result(_resp(result={"key": None}), "key")
        assert r.empty is True

    def test_deep_three_level_traversal(self):
        r = HedgingToolService._extract_provider_result(_resp(result={"a": {"b": {"c": "deep"}}}), "a.b.c")
        assert r.data == "deep"


# ---------------------------------------------------------------------------
# TestInvokeProviderTool
# ---------------------------------------------------------------------------


class TestInvokeProviderTool:
    """invoke_provider_tool resolves the provider from the DB and delegates the HTTP call
    to ProviderToolFactory.invoke (which lives in the provider module)."""

    def _make_provider(self, toolkit_name="search", tool_name="semantic_search"):
        tool = Mock()
        tool.name = tool_name

        toolkit = Mock()
        toolkit.name = toolkit_name
        toolkit.provided_tools = [tool]

        provider = Mock()
        provider.provided_toolkits = [toolkit]
        provider.service_location_url = "http://provider.local"
        provider.configuration = Mock()
        return provider

    def test_provider_not_found_raises(self, provider_hedging_cfg, mock_user):
        with patch("codemie.service.tools.hedging_tool_service.Provider") as mock_prov:
            mock_prov.get_by_fields.return_value = None
            with pytest.raises(ValueError, match="my-provider"):
                HedgingToolService.invoke_provider_tool(provider_hedging_cfg, {}, mock_user, "proj-1", "req-uuid")

    def test_toolkit_not_found_raises(self, provider_hedging_cfg, mock_user):
        provider = Mock()
        provider.provided_toolkits = []

        with patch("codemie.service.tools.hedging_tool_service.Provider") as mock_prov:
            mock_prov.get_by_fields.return_value = provider
            with pytest.raises(ValueError, match="search"):
                HedgingToolService.invoke_provider_tool(provider_hedging_cfg, {}, mock_user, "proj-1", "req-uuid")

    def test_tool_not_found_raises(self, provider_hedging_cfg, mock_user):
        toolkit = Mock()
        toolkit.name = "search"
        toolkit.provided_tools = []

        provider = Mock()
        provider.provided_toolkits = [toolkit]
        provider.service_location_url = "http://provider.local"

        with patch("codemie.service.tools.hedging_tool_service.Provider") as mock_prov:
            mock_prov.get_by_fields.return_value = provider
            with pytest.raises(ValueError, match="semantic_search"):
                HedgingToolService.invoke_provider_tool(provider_hedging_cfg, {}, mock_user, "proj-1", "req-uuid")

    def test_happy_path_resolves_params_and_delegates_to_factory(self, provider_hedging_cfg, mock_user):
        provider = self._make_provider()
        toolkit = provider.provided_toolkits[0]
        tool = toolkit.provided_tools[0]
        expected_result = HedgeToolResult(empty=False, data="found it")

        mock_factory = Mock()
        mock_factory.invoke.return_value = Mock()

        template_ctx = {"query": "test query"}

        with (
            patch("codemie.service.tools.hedging_tool_service.Provider") as mock_prov,
            patch(
                "codemie.service.tools.hedging_tool_service.ProviderToolFactory", return_value=mock_factory
            ) as mock_factory_cls,
            patch("codemie.service.tools.hedging_tool_service.process_string", return_value="resolved query"),
            patch.object(HedgingToolService, "_resolve_datasource", return_value=None),
            patch.object(HedgingToolService, "_extract_provider_result", return_value=expected_result),
        ):
            mock_prov.get_by_fields.return_value = provider
            result = HedgingToolService.invoke_provider_tool(
                provider_hedging_cfg, template_ctx, mock_user, "proj-1", "req-uuid"
            )

        assert result is expected_result
        # Factory is constructed with the resolved provider/toolkit/tool and datasource
        mock_factory_cls.assert_called_once_with(provider, toolkit, tool, datasource=None)
        # The HTTP call is delegated to the provider module via .invoke
        mock_factory.invoke.assert_called_once()
        call_kwargs = mock_factory.invoke.call_args[1]
        assert call_kwargs["user"] is mock_user
        assert call_kwargs["project_id"] == "proj-1"
        assert call_kwargs["request_uuid"] == "req-uuid"
        assert call_kwargs["params"] == {"query": "resolved query"}
        assert call_kwargs["datasource"] is None

    def _invoke_and_get_factory_kwargs(self, template_ctx, mock_user, datasource_name=None, datasource=None):
        """Helper: run invoke_provider_tool with a minimal valid provider and return the
        (factory_class_mock, invoke_kwargs) recorded on the patched ProviderToolFactory."""
        provider = self._make_provider()
        mock_factory = Mock()
        mock_factory.invoke.return_value = Mock()

        cfg = HedgingConfig(
            provider_tool=HedgingProviderToolDetails(
                provider_name="my-provider",
                toolkit_name="search",
                tool_name="semantic_search",
                datasource_name=datasource_name,
            ),
            input_mapping={"query": "{{query}}"},
        )

        with (
            patch("codemie.service.tools.hedging_tool_service.Provider") as mock_prov,
            patch(
                "codemie.service.tools.hedging_tool_service.ProviderToolFactory", return_value=mock_factory
            ) as mock_factory_cls,
            patch("codemie.service.tools.hedging_tool_service.process_string", return_value="q"),
            patch.object(HedgingToolService, "_resolve_datasource", return_value=datasource),
            patch.object(HedgingToolService, "_extract_provider_result", return_value=HedgeToolResult(empty=True)),
        ):
            mock_prov.get_by_fields.return_value = provider
            HedgingToolService.invoke_provider_tool(cfg, template_ctx, mock_user, "proj", "uuid")

        return mock_factory_cls, mock_factory.invoke.call_args[1]

    def test_request_headers_forwarded_to_factory_invoke(self, mock_user):
        headers = {"x-tenant": "acme", "x-request-id": "abc123"}
        _, invoke_kwargs = self._invoke_and_get_factory_kwargs({"headers": headers}, mock_user)

        assert invoke_kwargs["headers"] == headers

    def test_empty_headers_dict_passed_as_none(self, mock_user):
        _, invoke_kwargs = self._invoke_and_get_factory_kwargs({"headers": {}}, mock_user)

        assert invoke_kwargs["headers"] is None

    def test_missing_headers_key_passed_as_none(self, mock_user):
        _, invoke_kwargs = self._invoke_and_get_factory_kwargs({}, mock_user)

        assert invoke_kwargs["headers"] is None

    def test_none_headers_value_passed_as_none(self, mock_user):
        _, invoke_kwargs = self._invoke_and_get_factory_kwargs({"headers": None}, mock_user)

        assert invoke_kwargs["headers"] is None

    def test_input_mapping_uses_process_string_for_each_key(self, mock_user):
        cfg = HedgingConfig(
            provider_tool=HedgingProviderToolDetails(provider_name="p", toolkit_name="tk", tool_name="t"),
            input_mapping={"a": "{{query}}", "b": "{{user.id}}"},
        )
        provider = self._make_provider(toolkit_name="tk", tool_name="t")
        mock_factory = Mock()
        mock_factory.invoke.return_value = Mock()

        resolved_values = {"a": "resolved_a", "b": "resolved_b"}

        def fake_process(template, ctx):
            key = "a" if "query" in template else "b"
            return resolved_values[key]

        with (
            patch("codemie.service.tools.hedging_tool_service.Provider") as mock_prov,
            patch("codemie.service.tools.hedging_tool_service.ProviderToolFactory", return_value=mock_factory),
            patch("codemie.service.tools.hedging_tool_service.process_string", side_effect=fake_process),
            patch.object(HedgingToolService, "_resolve_datasource", return_value=None),
            patch.object(HedgingToolService, "_extract_provider_result", return_value=HedgeToolResult(empty=True)),
        ):
            mock_prov.get_by_fields.return_value = provider
            HedgingToolService.invoke_provider_tool(cfg, {"query": "q"}, mock_user, "p", "uuid")

        invoke_kwargs = mock_factory.invoke.call_args[1]
        assert invoke_kwargs["params"] == {"a": "resolved_a", "b": "resolved_b"}

    def test_resolved_datasource_passed_to_factory_constructor_and_invoke(self, mock_user):
        sentinel_ds = Mock()
        mock_factory_cls, invoke_kwargs = self._invoke_and_get_factory_kwargs(
            {}, mock_user, datasource_name="ds-name", datasource=sentinel_ds
        )

        # datasource flows into both the factory constructor and the invoke call
        assert mock_factory_cls.call_args.kwargs["datasource"] is sentinel_ds
        assert invoke_kwargs["datasource"] is sentinel_ds

    def test_resolve_datasource_called_with_name_and_project(self, mock_user):
        provider = self._make_provider()
        mock_factory = Mock()
        mock_factory.invoke.return_value = Mock()

        cfg = HedgingConfig(
            provider_tool=HedgingProviderToolDetails(
                provider_name="my-provider",
                toolkit_name="search",
                tool_name="semantic_search",
                datasource_name="ds-name",
            ),
            input_mapping={},
        )

        with (
            patch("codemie.service.tools.hedging_tool_service.Provider") as mock_prov,
            patch("codemie.service.tools.hedging_tool_service.ProviderToolFactory", return_value=mock_factory),
            patch("codemie.service.tools.hedging_tool_service.process_string", return_value="q"),
            patch.object(HedgingToolService, "_resolve_datasource", return_value=None) as mock_resolve_ds,
            patch.object(HedgingToolService, "_extract_provider_result", return_value=HedgeToolResult(empty=True)),
        ):
            mock_prov.get_by_fields.return_value = provider
            HedgingToolService.invoke_provider_tool(cfg, {}, mock_user, "proj-1", "req-uuid")

        mock_resolve_ds.assert_called_once_with("ds-name", "proj-1")


# ---------------------------------------------------------------------------
# TestResolveDatasource
# ---------------------------------------------------------------------------


class TestResolveDatasource:
    """_resolve_datasource maps a named datasource to its ProviderIndexInfo. Decryption of the
    datasource config is handled downstream by ProviderToolFactory.invoke, not here."""

    def test_returns_none_when_datasource_name_is_none(self):
        assert HedgingToolService._resolve_datasource(None, "proj-1") is None

    def test_returns_none_when_datasource_name_is_empty_string(self):
        assert HedgingToolService._resolve_datasource("", "proj-1") is None

    def test_raises_value_error_when_filter_returns_empty_list(self):
        with patch("codemie.service.tools.hedging_tool_service.ProviderIndexInfo") as mock_pii:
            mock_pii.filter_by_project_and_repo.return_value = []
            with pytest.raises(ValueError, match="my-datasource"):
                HedgingToolService._resolve_datasource("my-datasource", "proj-1")

    def test_returns_first_datasource_when_found(self):
        datasource_first = Mock()
        datasource_second = Mock()

        with patch("codemie.service.tools.hedging_tool_service.ProviderIndexInfo") as mock_pii:
            mock_pii.filter_by_project_and_repo.return_value = [datasource_first, datasource_second]
            result = HedgingToolService._resolve_datasource("my-ds", "proj-1")

        assert result is datasource_first
        mock_pii.filter_by_project_and_repo.assert_called_once_with(
            project_name="proj-1",
            repo_name="my-ds",
        )
