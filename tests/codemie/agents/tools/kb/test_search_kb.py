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

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from codemie.agents.tools.kb.search_kb import SearchKBTool
from langchain_core.tools import ToolException


def _make_tool(
    error=False,
    completed=True,
    last_reindex_triggered_at=None,
    update_date=None,
    repo_name="my-repo",
    text=None,
):
    kb_index = MagicMock()
    kb_index.repo_name = repo_name
    kb_index.error = error
    kb_index.completed = completed
    kb_index.last_reindex_triggered_at = last_reindex_triggered_at
    kb_index.update_date = update_date
    kb_index.index_type = "knowledge_base_jira"
    kb_index.text = text
    tool = SearchKBTool.model_construct(
        index_info=kb_index,
        llm_model="gpt-4",
        metadata={},
        tokens_size_limit=20000,
    )
    return tool


class TestBuildHealthNotice:
    def test_returns_empty_when_kb_index_is_none(self):
        tool = SearchKBTool.model_construct(index_info=None)
        assert tool._build_health_notice() == ""

    def test_reindexing_notice_when_not_completed(self):
        tool = _make_tool(error=False, completed=False)
        notice = tool._build_health_notice()
        assert "is currently being re-indexed" in notice
        assert "my-repo" in notice

    def test_failed_notice_when_error_true(self):
        tool = _make_tool(error=True, completed=False)
        notice = tool._build_health_notice()
        assert "last indexing attempt failed" in notice
        assert "my-repo" in notice

    def test_failed_takes_priority_over_not_completed(self):
        # error=True, completed=False — FAILED wins
        tool = _make_tool(error=True, completed=False)
        notice = tool._build_health_notice()
        assert "last indexing attempt failed" in notice
        assert "re-indexed" not in notice

    def test_stale_notice_when_triggered_at_after_update_date(self):
        now = datetime.now()
        tool = _make_tool(
            error=False,
            completed=True,
            last_reindex_triggered_at=now,
            update_date=now - timedelta(hours=1),
        )
        notice = tool._build_health_notice()
        assert "scheduled reindex that did not complete" in notice
        assert "my-repo" in notice

    def test_no_notice_when_healthy(self):
        now = datetime.now()
        tool = _make_tool(
            error=False,
            completed=True,
            last_reindex_triggered_at=now - timedelta(hours=1),
            update_date=now,
        )
        assert tool._build_health_notice() == ""

    def test_no_notice_when_triggered_at_is_none(self):
        tool = _make_tool(error=False, completed=True, last_reindex_triggered_at=None, update_date=datetime.now())
        assert tool._build_health_notice() == ""

    def test_no_notice_when_update_date_is_none(self):
        tool = _make_tool(error=False, completed=True, last_reindex_triggered_at=datetime.now(), update_date=None)
        assert tool._build_health_notice() == ""

    def test_stale_not_triggered_when_not_completed(self):
        # REINDEXING wins when completed=False, even if triggered_at > update_date
        now = datetime.now()
        tool = _make_tool(
            error=False,
            completed=False,
            last_reindex_triggered_at=now,
            update_date=now - timedelta(hours=1),
        )
        notice = tool._build_health_notice()
        assert "is currently being re-indexed" in notice
        assert "scheduled reindex" not in notice

    def test_failed_notice_includes_error_message(self):
        tool = _make_tool(error=True, text="Connection refused")
        notice = tool._build_health_notice()
        assert "Connection refused" in notice

    def test_failed_notice_no_error_message_when_text_none(self):
        tool = _make_tool(error=True, text=None)
        notice = tool._build_health_notice()
        assert "last indexing attempt failed" in notice
        assert "Error:" not in notice


class TestBuildDescriptionHealthPrefix:
    def test_healthy_returns_empty(self):
        prefix = SearchKBTool._build_description_health_prefix(
            _make_tool(error=False, completed=True).index_info  # no stale dates → healthy
        )
        assert prefix == ""

    def test_failed_returns_prefix(self):
        prefix = SearchKBTool._build_description_health_prefix(_make_tool(error=True).index_info)
        assert "[DATASOURCE STATUS: FAILED]" in prefix

    def test_reindexing_returns_prefix(self):
        prefix = SearchKBTool._build_description_health_prefix(_make_tool(error=False, completed=False).index_info)
        assert "[DATASOURCE STATUS: REINDEXING]" in prefix

    def test_stale_returns_prefix(self):
        now = datetime.now()
        prefix = SearchKBTool._build_description_health_prefix(
            _make_tool(
                error=False, completed=True, last_reindex_triggered_at=now, update_date=now - timedelta(hours=1)
            ).index_info
        )
        assert "[DATASOURCE STATUS: STALE]" in prefix


class TestWrapResult:
    def test_empty_notice_returns_result_unchanged(self):
        tool = _make_tool()
        assert tool._wrap_result("some result", "") == "some result"

    def test_string_result_has_notice_prepended(self):
        tool = _make_tool()
        result = tool._wrap_result("content", "[DATASOURCE STATUS: FAILED] failed.\n\n")
        assert result.startswith("[DATASOURCE STATUS: FAILED]")
        assert "content" in result

    def test_non_string_result_passed_through_unchanged(self):
        tool = _make_tool()
        non_str = [{"doc": "a"}]
        with patch("codemie.agents.tools.datasource_health_mixin.logger") as mock_log:
            result = tool._wrap_result(non_str, "[DATASOURCE STATUS: FAILED] failed.\n\n")
        assert result is non_str
        mock_log.warning.assert_called_once()


class TestExecutePrependsNotice:
    @patch("codemie.agents.tools.kb.search_kb.SearchAndRerankKB")
    def test_standard_search_prepends_reindexing_notice(self, mock_search_class):
        mock_search_class.return_value.execute.return_value = []
        tool = _make_tool(error=False, completed=False)
        tool.index_info.index_type = "knowledge_base_jira"
        result = tool.execute(query="what is X")
        assert "is currently being re-indexed" in result

    @patch("codemie.agents.tools.kb.search_kb.SearchAndRerankKB")
    def test_standard_search_no_notice_when_healthy(self, mock_search_class):
        mock_search_class.return_value.execute.return_value = []
        tool = _make_tool(error=False, completed=True)
        tool.index_info.index_type = "knowledge_base_jira"
        result = tool.execute(query="what is X")
        assert "re-indexed" not in result
        assert "indexing attempt failed" not in result


class TestRunRaisesToolException:
    def test_raises_tool_exception_when_failed(self):
        tool = _make_tool(error=True)
        with pytest.raises(ToolException) as exc_info:
            tool._run(query="what is X")
        assert "last indexing attempt failed" in str(exc_info.value)

    @patch("codemie.agents.tools.kb.search_kb.SearchAndRerankKB")
    def test_no_exception_when_reindexing(self, mock_search_class):
        mock_search_class.return_value.execute.return_value = []
        tool = _make_tool(error=False, completed=False)
        tool.index_info.index_type = "knowledge_base_jira"
        result = tool._run(query="what is X")
        assert "is currently being re-indexed" in result

    @patch("codemie.agents.tools.kb.search_kb.SearchAndRerankKB")
    def test_no_exception_when_healthy(self, mock_search_class):
        mock_search_class.return_value.execute.return_value = []
        tool = _make_tool(error=False, completed=True)
        tool.index_info.index_type = "knowledge_base_jira"
        result = tool._run(query="what is X")
        assert "re-indexed" not in result
        assert "indexing attempt failed" not in result

    @patch("codemie.agents.tools.kb.search_kb.SearchAndRerankKB")
    def test_no_exception_when_stale(self, mock_search_class):
        now = datetime.now()
        mock_search_class.return_value.execute.return_value = []
        tool = _make_tool(
            error=False,
            completed=True,
            last_reindex_triggered_at=now,
            update_date=now - timedelta(hours=1),
        )
        tool.index_info.index_type = "knowledge_base_jira"
        result = tool._run(query="what is X")
        assert "scheduled reindex that did not complete" in result
