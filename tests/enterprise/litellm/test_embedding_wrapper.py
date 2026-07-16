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

"""Tests for EmbeddingClientWrapper and LiteLLMAzureOpenAIEmbeddings (Cycles 1 & 2)."""

import threading
from unittest.mock import MagicMock, patch


class TestEmbeddingClientWrapper:
    def _make_raw_response(self, cost_str, prompt_tokens):
        mock_parsed = MagicMock()
        mock_parsed.usage.prompt_tokens = prompt_tokens

        mock_raw = MagicMock()
        mock_raw.headers = {"x-litellm-response-cost": cost_str} if cost_str is not None else {}
        mock_raw.parse.return_value = mock_parsed
        return mock_raw, mock_parsed

    def test_create_returns_parsed_response(self):
        from codemie.enterprise.litellm.llm_factory import EmbeddingClientWrapper

        mock_real = MagicMock()
        raw, parsed = self._make_raw_response("0.000005", 100)
        mock_real.with_raw_response.create.return_value = raw

        wrapper = EmbeddingClientWrapper(mock_real)
        result = wrapper.create(input=["hello"], model="test")

        assert result is parsed

    def test_consume_last_usage_returns_none_before_any_create(self):
        from codemie.enterprise.litellm.llm_factory import EmbeddingClientWrapper

        wrapper = EmbeddingClientWrapper(MagicMock())

        assert wrapper.consume_last_usage() is None

    def test_create_accumulates_proxy_cost_from_header(self):
        from codemie.enterprise.litellm.llm_factory import EmbeddingClientWrapper, EmbeddingUsage

        mock_real = MagicMock()
        raw, _ = self._make_raw_response("0.000005", 100)
        mock_real.with_raw_response.create.return_value = raw

        wrapper = EmbeddingClientWrapper(mock_real)
        wrapper.create(input=["hello"], model="test")

        usage = wrapper.consume_last_usage()
        assert isinstance(usage, EmbeddingUsage)
        assert usage.input_tokens == 100
        assert abs(usage.cost - 0.000005) < 1e-10

    def test_consume_last_usage_accumulates_multiple_creates(self):
        from codemie.enterprise.litellm.llm_factory import EmbeddingClientWrapper

        mock_real = MagicMock()
        raw1, _ = self._make_raw_response("0.000003", 60)
        raw2, _ = self._make_raw_response("0.000002", 40)
        mock_real.with_raw_response.create.side_effect = [raw1, raw2]

        wrapper = EmbeddingClientWrapper(mock_real)
        wrapper.create(input=["hello"], model="test")
        wrapper.create(input=["world"], model="test")

        usage = wrapper.consume_last_usage()
        assert usage.input_tokens == 100
        assert abs(usage.cost - 0.000005) < 1e-10

    def test_consume_last_usage_resets_accumulator(self):
        from codemie.enterprise.litellm.llm_factory import EmbeddingClientWrapper

        mock_real = MagicMock()
        raw, _ = self._make_raw_response("0.000005", 100)
        mock_real.with_raw_response.create.return_value = raw

        wrapper = EmbeddingClientWrapper(mock_real)
        wrapper.create(input=["hello"], model="test")
        wrapper.consume_last_usage()

        assert wrapper.consume_last_usage() is None

    def test_create_skips_accumulation_when_header_absent(self):
        from codemie.enterprise.litellm.llm_factory import EmbeddingClientWrapper

        mock_real = MagicMock()
        raw, _ = self._make_raw_response(None, 100)
        mock_real.with_raw_response.create.return_value = raw

        wrapper = EmbeddingClientWrapper(mock_real)
        wrapper.create(input=["hello"], model="test")

        assert wrapper.consume_last_usage() is None

    def test_accumulation_is_thread_safe(self):
        from codemie.enterprise.litellm.llm_factory import EmbeddingClientWrapper

        def make_raw():
            raw, _ = self._make_raw_response("0.000001", 1)
            return raw

        mock_real = MagicMock()
        mock_real.with_raw_response.create.side_effect = lambda **_: make_raw()

        wrapper = EmbeddingClientWrapper(mock_real)

        threads = [threading.Thread(target=lambda: wrapper.create(input=["x"], model="test")) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        usage = wrapper.consume_last_usage()
        assert usage is not None
        assert usage.input_tokens == 50
        assert abs(usage.cost - 0.000050) < 1e-9


class TestLiteLLMAzureOpenAIEmbeddings:
    def _make_instance(self, original_client):
        from codemie.enterprise.litellm.llm_factory import LiteLLMAzureOpenAIEmbeddings

        def fake_parent_init(self_inst, **kwargs):
            object.__setattr__(self_inst, 'client', original_client)
            object.__setattr__(self_inst, 'async_client', MagicMock(name="async_client"))

        with patch("langchain_openai.AzureOpenAIEmbeddings.__init__", fake_parent_init):
            instance = LiteLLMAzureOpenAIEmbeddings()

        return instance

    def test_client_is_wrapped_after_init(self):
        from codemie.enterprise.litellm.llm_factory import EmbeddingClientWrapper

        original_client = MagicMock(name="original_client")
        instance = self._make_instance(original_client)

        assert isinstance(instance.client, EmbeddingClientWrapper)
        assert instance.client._real is original_client

    def test_consume_last_usage_delegates_to_wrapper(self):
        from codemie.enterprise.litellm.llm_factory import EmbeddingUsage

        original_client = MagicMock(name="original_client")
        raw = MagicMock()
        raw.headers = {"x-litellm-response-cost": "0.000007"}
        parsed = MagicMock()
        parsed.usage.prompt_tokens = 70
        raw.parse.return_value = parsed
        original_client.with_raw_response.create.return_value = raw

        instance = self._make_instance(original_client)
        instance.client.create(input=["test"], model="test")

        usage = instance.consume_last_usage()
        assert isinstance(usage, EmbeddingUsage)
        assert usage.input_tokens == 70
        assert abs(usage.cost - 0.000007) < 1e-10

    def test_consume_last_usage_returns_none_before_any_calls(self):
        original_client = MagicMock(name="original_client")
        instance = self._make_instance(original_client)

        assert instance.consume_last_usage() is None
