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

import pytest
from unittest.mock import Mock, patch

from codemie.core.constants import REQUEST_ID
from codemie.core.models import CodeFields
from codemie.rest_api.models.index import IndexInfo
from codemie.rest_api.models.tool import DatasourceSearchInvokeRequest, CodeDatasourceSearchParams
from codemie.service.monitoring.metrics_constants import MetricsAttributes
from codemie.service.tools.tool_execution_service import ToolExecutionService

_SVC = "codemie.service.tools.tool_execution_service"


def test_invoke_datasource_search():
    """Test invoking datasource search without request_id (no-op tracking path)."""
    datasource = Mock(spec=IndexInfo)
    request = Mock(spec=DatasourceSearchInvokeRequest)
    request.query = "test query"
    request.llm_model = "gpt-4"
    request.request_id = None

    mock_search_tool = Mock()
    mock_search_tool.metadata = {}
    mock_search_tool.name = "search_tool"
    mock_search_tool.execute = Mock(return_value="search results")

    with patch.object(ToolExecutionService, 'get_search_tool', return_value=mock_search_tool) as mock_get_tool:
        result = ToolExecutionService.invoke_datasource_search(datasource, request)

    mock_get_tool.assert_called_once_with(datasource, request)
    mock_search_tool.execute.assert_called_once_with(query=request.query)
    assert mock_search_tool.metadata == {'llm_model': request.llm_model, REQUEST_ID: ""}
    assert result == "search results"


def test_get_search_tool_kb_index():
    """Test getting search tool for KB index."""
    # Create mock KB index and request
    datasource = Mock(spec=IndexInfo)
    datasource.is_code_index = Mock(return_value=False)

    request = Mock(spec=DatasourceSearchInvokeRequest)
    request.llm_model = "gpt-4"

    # Mock SearchKBTool constructor
    with patch('codemie.service.tools.tool_execution_service.SearchKBTool', return_value="kb_tool") as mock_kb_tool:
        result = ToolExecutionService.get_search_tool(datasource, request)

    # Assert
    mock_kb_tool.assert_called_once_with(index_info=datasource, llm_model="gpt-4")
    assert result == "kb_tool"


def test_get_search_tool_code_index():
    """Test getting search tool for code index."""
    # Create mock code index and request
    datasource = Mock(spec=IndexInfo)
    datasource.is_code_index = Mock(return_value=True)
    datasource.project_name = "test-project"
    datasource.repo_name = "test-repo"
    datasource.index_type = "code"
    datasource.repo_type = "git"

    request = Mock(spec=DatasourceSearchInvokeRequest)
    request.llm_model = "gpt-4"
    request.query = "search query"

    # Create code search parameters
    code_params = Mock(spec=CodeDatasourceSearchParams)
    code_params.user_input = "custom input"
    code_params.top_k = 5
    code_params.with_filtering = True
    request.code_search_params = code_params

    # Mock CodeToolkit.search_code_tool
    with patch(
        'codemie.service.tools.tool_execution_service.CodeToolkit.search_code_tool', return_value="code_tool"
    ) as mock_code_tool:
        result = ToolExecutionService.get_search_tool(datasource, request)

    # Assert
    mock_code_tool.assert_called_once()
    code_fields_arg = mock_code_tool.call_args.kwargs['code_fields']
    assert isinstance(code_fields_arg, CodeFields)
    assert code_fields_arg.app_name == "test-project"
    assert code_fields_arg.repo_name == "test-repo"
    assert code_fields_arg.index_type == "code"
    assert mock_code_tool.call_args.kwargs['user_input'] == "custom input"
    assert mock_code_tool.call_args.kwargs['top_k'] == 5
    assert mock_code_tool.call_args.kwargs['with_filtering']
    assert result == "code_tool"


def test_get_search_tool_code_index_default_params():
    """Test getting search tool for code index with default params."""
    # Create mock code index and request
    datasource = Mock(spec=IndexInfo)
    datasource.is_code_index = Mock(return_value=True)
    datasource.project_name = "test-project"
    datasource.repo_name = "test-repo"
    datasource.index_type = "code"
    datasource.repo_type = "git"

    request = Mock(spec=DatasourceSearchInvokeRequest)
    request.llm_model = "gpt-4"
    request.query = "search query"
    request.code_search_params = None

    # Mock CodeToolkit.search_code_tool
    with patch(
        'codemie.service.tools.tool_execution_service.CodeToolkit.search_code_tool', return_value="code_tool"
    ) as mock_code_tool:
        result = ToolExecutionService.get_search_tool(datasource, request)

    # Assert
    mock_code_tool.assert_called_once()
    code_fields_arg = mock_code_tool.call_args.kwargs['code_fields']
    assert isinstance(code_fields_arg, CodeFields)
    assert code_fields_arg.app_name == "test-project"
    assert code_fields_arg.repo_name == "test-repo"
    assert code_fields_arg.index_type == "code"
    assert mock_code_tool.call_args.kwargs['user_input'] == "search query"  # Falls back to request.query
    assert result == "code_tool"


def test_invoke_datasource_search_injects_request_id_in_metadata():
    """REQUEST_ID must land in tool metadata when request_id is provided."""
    datasource = Mock(spec=IndexInfo)
    datasource.project_name = "my-project"
    request = Mock(spec=DatasourceSearchInvokeRequest)
    request.query = "test query"
    request.llm_model = "gpt-4"
    request.request_id = "req-abc-123"

    mock_search_tool = Mock()
    mock_search_tool.metadata = {}
    mock_search_tool.name = "search_kb_my-index"
    mock_search_tool.execute = Mock(return_value="results")

    with patch.object(ToolExecutionService, 'get_search_tool', return_value=mock_search_tool):
        with patch(f"{_SVC}.emit_llm_token_metric"):
            with patch(f"{_SVC}.request_summary_manager"):
                ToolExecutionService.invoke_datasource_search(datasource, request)

    assert mock_search_tool.metadata[REQUEST_ID] == "req-abc-123"


def test_invoke_datasource_search_emits_token_metric_with_real_attrs():
    """emit_llm_token_metric is called with tool.name and datasource.project_name."""
    datasource = Mock(spec=IndexInfo)
    datasource.project_name = "my-project"
    request = Mock(spec=DatasourceSearchInvokeRequest)
    request.query = "test query"
    request.llm_model = "gpt-4"
    request.request_id = "req-abc-123"

    mock_search_tool = Mock()
    mock_search_tool.metadata = {}
    mock_search_tool.name = "search_kb_my-index"
    mock_search_tool.execute = Mock(return_value="results")

    with patch.object(ToolExecutionService, 'get_search_tool', return_value=mock_search_tool):
        with patch(f"{_SVC}.emit_llm_token_metric") as mock_emit:
            with patch(f"{_SVC}.request_summary_manager"):
                ToolExecutionService.invoke_datasource_search(datasource, request)

    mock_emit.assert_called_once()
    call_kwargs = mock_emit.call_args[1]
    assert call_kwargs["request_id"] == "req-abc-123"
    assert call_kwargs["base_attributes"][MetricsAttributes.TOOL_NAME] == "search_kb_my-index"
    assert call_kwargs["base_attributes"][MetricsAttributes.PROJECT] == "my-project"


def test_invoke_datasource_search_clears_summary_in_finally_on_error():
    """Summary is cleared even when execute() raises."""
    datasource = Mock(spec=IndexInfo)
    datasource.project_name = "proj"
    request = Mock(spec=DatasourceSearchInvokeRequest)
    request.query = "q"
    request.llm_model = "gpt-4"
    request.request_id = "req-err"

    mock_search_tool = Mock()
    mock_search_tool.metadata = {}
    mock_search_tool.name = "search_tool"
    mock_search_tool.execute = Mock(side_effect=RuntimeError("ES down"))

    with patch.object(ToolExecutionService, 'get_search_tool', return_value=mock_search_tool):
        with patch(f"{_SVC}.emit_llm_token_metric"):
            with patch(f"{_SVC}.request_summary_manager") as mock_rsm:
                with pytest.raises(RuntimeError):
                    ToolExecutionService.invoke_datasource_search(datasource, request)

    mock_rsm.clear_summary.assert_called_once_with("req-err")


def test_invoke_datasource_search_skips_tracking_when_no_request_id():
    """No metric emission or summary clear when request_id is absent."""
    datasource = Mock(spec=IndexInfo)
    datasource.project_name = "proj"
    request = Mock(spec=DatasourceSearchInvokeRequest)
    request.query = "q"
    request.llm_model = "gpt-4"
    request.request_id = None

    mock_search_tool = Mock()
    mock_search_tool.metadata = {}
    mock_search_tool.name = "search_tool"
    mock_search_tool.execute = Mock(return_value="results")

    with patch.object(ToolExecutionService, 'get_search_tool', return_value=mock_search_tool):
        with patch(f"{_SVC}.emit_llm_token_metric") as mock_emit:
            with patch(f"{_SVC}.request_summary_manager") as mock_rsm:
                ToolExecutionService.invoke_datasource_search(datasource, request)

    mock_emit.assert_not_called()
    mock_rsm.clear_summary.assert_not_called()
