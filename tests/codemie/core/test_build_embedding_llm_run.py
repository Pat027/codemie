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

"""Tests for build_embedding_llm_run helper (Cycle 3)."""

import pytest
from unittest.mock import MagicMock


class _NoProxyEmbeddings:
    """Stand-in for a non-proxy embeddings instance (no consume_last_usage)."""


class TestBuildEmbeddingLLMRun:
    def test_proxy_path_uses_real_tokens_and_cost(self, mocker):
        from codemie.core.utils import build_embedding_llm_run
        from codemie.service.request_summary_manager import LLMRun

        mock_usage = MagicMock()
        mock_usage.input_tokens = 100
        mock_usage.cost = 0.000005

        mock_embeddings = MagicMock()
        mock_embeddings.consume_last_usage.return_value = mock_usage

        result = build_embedding_llm_run(mock_embeddings, "test query", "ada-002")

        assert isinstance(result, LLMRun)
        assert result.input_tokens == 100
        assert result.money_spent == pytest.approx(0.000005)
        assert result.output_tokens == 0
        assert result.llm_model == "ada-002"
        mock_embeddings.consume_last_usage.assert_called_once()

    def test_fallback_path_uses_calculated_tokens(self, mocker):
        from codemie.core.utils import build_embedding_llm_run
        from codemie.service.request_summary_manager import LLMRun

        mock_embeddings = _NoProxyEmbeddings()

        mocker.patch("codemie.core.utils.llm_service.get_embeddings_model_cost").return_value = MagicMock(input=0.0002)
        mocker.patch("codemie.core.utils.calculate_tokens", return_value=50)

        result = build_embedding_llm_run(mock_embeddings, "test query", "ada-002")

        assert isinstance(result, LLMRun)
        assert result.input_tokens == 50
        assert result.money_spent == pytest.approx(50 * 0.0002)
        assert result.llm_model == "ada-002"

    def test_proxy_usage_none_falls_back_to_calculated(self, mocker):
        from codemie.core.utils import build_embedding_llm_run

        mock_embeddings = MagicMock()
        mock_embeddings.consume_last_usage.return_value = None

        mocker.patch("codemie.core.utils.llm_service.get_embeddings_model_cost").return_value = MagicMock(input=0.0002)
        mocker.patch("codemie.core.utils.calculate_tokens", return_value=30)

        result = build_embedding_llm_run(mock_embeddings, "test query", "ada-002")

        assert result.input_tokens == 30
        assert result.money_spent == pytest.approx(30 * 0.0002)

    def test_llm_run_has_zero_output_tokens(self, mocker):
        from codemie.core.utils import build_embedding_llm_run

        mock_usage = MagicMock()
        mock_usage.input_tokens = 10
        mock_usage.cost = 0.000001
        mock_embeddings = MagicMock()
        mock_embeddings.consume_last_usage.return_value = mock_usage

        result = build_embedding_llm_run(mock_embeddings, "x", "model")

        assert result.output_tokens == 0

    def test_each_call_produces_unique_run_id(self, mocker):
        from codemie.core.utils import build_embedding_llm_run

        mock_usage = MagicMock()
        mock_usage.input_tokens = 10
        mock_usage.cost = 0.000001
        mock_embeddings = MagicMock()
        mock_embeddings.consume_last_usage.return_value = mock_usage

        r1 = build_embedding_llm_run(mock_embeddings, "x", "model")
        r2 = build_embedding_llm_run(mock_embeddings, "x", "model")

        assert r1.run_id != r2.run_id
