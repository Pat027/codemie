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


from codemie.configs import config
from codemie.service.provider.provider_header_context import ProviderHeaderContext


def test_build_minimal():
    ctx = ProviderHeaderContext()
    result = ctx.build()
    assert result == {}


def test_build_all_fields():
    ctx = ProviderHeaderContext(
        conversation_id="conv-1",
        history_index=3,
        assistant_id="asst-1",
        llm_model="gpt-4",
        temperature=0.7,
        top_p=0.9,
    )
    result = ctx.build()

    assert result[ProviderHeaderContext.HEADERS["CONVERSATION_ID"]] == "conv-1"
    assert result[ProviderHeaderContext.HEADERS["MESSAGE_ID"]] == "3"
    assert result[ProviderHeaderContext.HEADERS["ASSISTANT_ID"]] == "asst-1"
    assert result[ProviderHeaderContext.HEADERS["LLM_MODEL"]] == "gpt-4"
    assert result[ProviderHeaderContext.HEADERS["TEMPERATURE"]] == "0.7"
    assert result[ProviderHeaderContext.HEADERS["TOP_P"]] == "0.9"


def test_build_skips_empty_values():
    ctx = ProviderHeaderContext(
        request_headers={"X-Tenant-Id": "", "X-Custom": "val"},
        conversation_id="",
    )
    result = ctx.build()

    assert "X-Tenant-Id" not in result
    assert result["X-Custom"] == "val"
    assert ProviderHeaderContext.HEADERS["CONVERSATION_ID"] not in result


def test_build_skips_none_fields():
    ctx = ProviderHeaderContext(conversation_id="conv-1")
    result = ctx.build()

    assert ProviderHeaderContext.HEADERS["CONVERSATION_ID"] in result
    assert ProviderHeaderContext.HEADERS["MESSAGE_ID"] not in result
    assert ProviderHeaderContext.HEADERS["ASSISTANT_ID"] not in result
    assert ProviderHeaderContext.HEADERS["TEMPERATURE"] not in result


def test_build_passes_through_request_headers():
    ctx = ProviderHeaderContext(request_headers={"X-Tenant-Id": "tenant-1", "X-Custom": "val"})
    result = ctx.build()

    assert result["X-Tenant-Id"] == "tenant-1"
    assert result["X-Custom"] == "val"


def test_build_filters_blocked_request_headers():
    ctx = ProviderHeaderContext(
        request_headers={
            "X-Api-Key": "secret",
            "Authorization": "Bearer token",
            "X-Tenant-Id": "tenant-1",
        }
    )
    result = ctx.build()

    assert "X-Api-Key" not in result
    assert "Authorization" not in result
    assert result["X-Tenant-Id"] == "tenant-1"


def test_build_blocked_headers_case_insensitive():
    ctx = ProviderHeaderContext(request_headers={"x-api-key": "secret", "X-API-KEY": "secret2"})
    result = ctx.build()

    assert "x-api-key" not in result
    assert "X-API-KEY" not in result


def test_build_metadata_headers_override_request_headers():
    # If a request header has the same name as a metadata header, metadata wins
    ctx = ProviderHeaderContext(
        request_headers={"X-Conversation-Id": "from-request"},
        conversation_id="from-context",
    )
    result = ctx.build()

    assert result[ProviderHeaderContext.HEADERS["CONVERSATION_ID"]] == "from-context"


def test_build_custom_blocked_headers(monkeypatch):
    monkeypatch.setattr(config, "FORWARDED_HEADERS_BLOCKLIST", "x-custom-blocked")
    ctx = ProviderHeaderContext(request_headers={"X-Custom-Blocked": "val", "X-Allowed": "ok"})
    result = ctx.build()

    assert "X-Custom-Blocked" not in result
    assert result["X-Allowed"] == "ok"


def test_build_history_index_zero_is_included():
    ctx = ProviderHeaderContext(history_index=0)
    result = ctx.build()

    assert result[ProviderHeaderContext.HEADERS["MESSAGE_ID"]] == "0"
