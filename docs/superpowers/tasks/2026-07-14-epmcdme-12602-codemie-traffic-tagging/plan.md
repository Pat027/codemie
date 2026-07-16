# EPMCDME-12602: Codemie Traffic Tagging Headers (non-LiteLLM path) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inject `X-CodeMie-Version` and `X-CodeMie-Project` HTTP headers into outbound LLM requests on the non-LiteLLM (internal) routing path for Azure/DIAL, Vertex AI, and Anthropic providers.

**Architecture:** A single private helper `_build_codemie_tagging_headers()` is added to `dependecies.py`. Each applicable provider factory calls it first to seed `merged_headers`, then applies static `client_headers` from model config on top (model config wins on collision). AWS Bedrock is explicitly excluded — it uses a request-body field, not HTTP headers.

**Tech Stack:** Python 3.12, LangChain (`langchain-openai`, `langchain-google-vertexai`, `langchain-anthropic`), pytest + `unittest.mock`.

## Global Constraints

- Header names: `X-CodeMie-Version` and `X-CodeMie-Project` (capital M, matching existing `constants.py` casing).
- Precedence: model YAML `client_headers` overwrite Codemie tagging headers (model config wins).
- Empty project: skip `X-CodeMie-Project` header entirely when `get_current_project()` returns `""`.
- `X-CodeMie-Version` value: always `config.APP_VERSION`.
- AWS Bedrock (`get_bedrock_llm`): do not touch — out of scope.
- No new packages. No env-var reads in feature code — use `config.APP_VERSION` via the imported `config` singleton.
- Apache 2.0 license header required on all new Python files (`make license-fix` auto-adds it).
- Commit message format: `EPMCDME-12602: <description>`.
- Test-first: yes — write the failing test, run it to confirm RED, implement, run again to confirm GREEN.

---

### Task 1: Constants + tagging helper + Azure/DIAL injection

**Test-first: yes — failing test asserts `X-CodeMie-Version` in `default_headers` before the helper exists.**

**Files:**
- Modify: `src/codemie/core/constants.py` (add two constants after line 51)
- Modify: `src/codemie/core/dependecies.py` (add helper + update `get_llm_by_credentials_raw`)
- Create: `tests/codemie/core/test_dependencies_tagging_headers.py`

**Interfaces:**
- Produces: `_build_codemie_tagging_headers() -> dict[str, str]` (private, used by all three provider factories)
- Produces: `HEADER_CODEMIE_VERSION = "X-CodeMie-Version"` in `constants.py`
- Produces: `HEADER_CODEMIE_TAGGING_PROJECT = "X-CodeMie-Project"` in `constants.py`

---

- [ ] **Step 1: Write the failing test file**

Create `tests/codemie/core/test_dependencies_tagging_headers.py` with the first three test cases:

```python
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

"""Tests for Codemie traffic-tagging header injection in core dependencies."""

import pytest
from unittest.mock import MagicMock, patch


def _make_model_details(client_headers=None):
    """Build a minimal LLMModel mock that reaches the AzureChatOpenAI call."""
    m = MagicMock()
    m.provider = None  # not GOOGLE_VERTEX_AI / AWS_BEDROCK / ANTHROPIC
    m.deployment_name = "gpt-4"
    m.base_name = "gpt-4"
    m.api_version = None
    m.max_output_tokens = 4096
    m.features.streaming = True
    m.features.temperature = True
    m.features.parallel_tool_calls = True
    m.features.max_tokens = True
    m.features.top_p = True
    if client_headers is not None:
        m.configuration = MagicMock()
        m.configuration.client_headers = client_headers
    else:
        m.configuration = None
    return m


def _make_creds():
    creds = MagicMock()
    creds.url = "https://test.openai.azure.com"
    creds.api_key = "test-key"
    creds.api_version = "2025-04-01-preview"
    return creds


class TestAzureTaggingHeaders:
    """X-CodeMie-* header injection on the Azure/DIAL path."""

    def test_both_tags_injected_when_project_set(self):
        """AzureChatOpenAI receives X-CodeMie-Version and X-CodeMie-Project."""
        from codemie.configs.config import config

        with patch("codemie.core.dependecies.AzureChatOpenAI") as mock_azure, \
             patch("codemie.core.dependecies.llm_service.get_model_details",
                   return_value=_make_model_details()), \
             patch("codemie.core.dependecies.dial_credentials") as mock_creds_var, \
             patch("codemie.core.dependecies.get_current_project", return_value="my-project"), \
             patch.object(config, "APP_VERSION", "1.2.3"), \
             patch.object(config, "OPENAI_API_TYPE", "azure"), \
             patch.object(config, "AZURE_OPENAI_MAX_RETRIES", 3):
            mock_creds_var.get.return_value = _make_creds()
            from codemie.core.dependecies import get_llm_by_credentials_raw
            get_llm_by_credentials_raw("gpt-4")

        call_kwargs = mock_azure.call_args[1]
        assert "default_headers" in call_kwargs
        assert call_kwargs["default_headers"]["X-CodeMie-Version"] == "1.2.3"
        assert call_kwargs["default_headers"]["X-CodeMie-Project"] == "my-project"

    def test_project_header_skipped_when_empty(self):
        """X-CodeMie-Project is absent when get_current_project() returns empty string."""
        from codemie.configs.config import config

        with patch("codemie.core.dependecies.AzureChatOpenAI") as mock_azure, \
             patch("codemie.core.dependecies.llm_service.get_model_details",
                   return_value=_make_model_details()), \
             patch("codemie.core.dependecies.dial_credentials") as mock_creds_var, \
             patch("codemie.core.dependecies.get_current_project", return_value=""), \
             patch.object(config, "APP_VERSION", "1.2.3"), \
             patch.object(config, "OPENAI_API_TYPE", "azure"), \
             patch.object(config, "AZURE_OPENAI_MAX_RETRIES", 3):
            mock_creds_var.get.return_value = _make_creds()
            from codemie.core.dependecies import get_llm_by_credentials_raw
            get_llm_by_credentials_raw("gpt-4")

        call_kwargs = mock_azure.call_args[1]
        assert "default_headers" in call_kwargs
        assert "X-CodeMie-Version" in call_kwargs["default_headers"]
        assert "X-CodeMie-Project" not in call_kwargs["default_headers"]

    def test_client_headers_override_codemie_tags(self):
        """Model client_headers win when they set the same key as a Codemie tag."""
        from codemie.configs.config import config

        model = _make_model_details(client_headers={"X-CodeMie-Version": "override-value"})
        with patch("codemie.core.dependecies.AzureChatOpenAI") as mock_azure, \
             patch("codemie.core.dependecies.llm_service.get_model_details", return_value=model), \
             patch("codemie.core.dependecies.dial_credentials") as mock_creds_var, \
             patch("codemie.core.dependecies.get_current_project", return_value="proj"), \
             patch.object(config, "APP_VERSION", "1.2.3"), \
             patch.object(config, "OPENAI_API_TYPE", "azure"), \
             patch.object(config, "AZURE_OPENAI_MAX_RETRIES", 3):
            mock_creds_var.get.return_value = _make_creds()
            from codemie.core.dependecies import get_llm_by_credentials_raw
            get_llm_by_credentials_raw("gpt-4")

        call_kwargs = mock_azure.call_args[1]
        assert call_kwargs["default_headers"]["X-CodeMie-Version"] == "override-value"
```

- [ ] **Step 2: Run tests to confirm RED**

```
pytest tests/codemie/core/test_dependencies_tagging_headers.py -v
```

Expected: 3 failures — `AssertionError: 'default_headers' not in call_kwargs` (or similar, since the helper doesn't exist yet).

- [ ] **Step 3: Add constants to `constants.py`**

In `src/codemie/core/constants.py`, after line 51 (`HEADER_CODEMIE_CLI_PROJECT = "X-CodeMie-Project"`):

```python
HEADER_CODEMIE_VERSION = "X-CodeMie-Version"
HEADER_CODEMIE_TAGGING_PROJECT = "X-CodeMie-Project"
```

- [ ] **Step 4: Add the import for the new constants in `dependecies.py`**

In `src/codemie/core/dependecies.py`, update the constants import (line 31):

```python
from codemie.core.constants import (
    DEFAULT_MAX_OUTPUT_TOKENS_4K,
    DEFAULT_MAX_OUTPUT_TOKENS_8K,
    DatasourceTypes,
    HEADER_CODEMIE_VERSION,
    HEADER_CODEMIE_TAGGING_PROJECT,
)
```

- [ ] **Step 5: Add `_build_codemie_tagging_headers()` to `dependecies.py`**

Add immediately before `format_headers_for_openai_api` (before line 332):

```python
def _build_codemie_tagging_headers() -> dict[str, str]:
    headers: dict[str, str] = {HEADER_CODEMIE_VERSION: config.APP_VERSION}
    project = get_current_project()
    if project:
        headers[HEADER_CODEMIE_TAGGING_PROJECT] = project
    return headers
```

- [ ] **Step 6: Update the merge logic in `get_llm_by_credentials_raw()`**

Replace the existing merged_headers block (lines 367–370):

```python
# Before (original):
merged_headers = {}
if llm_model_details.configuration and llm_model_details.configuration.client_headers:
    merged_headers.update(llm_model_details.configuration.client_headers)
```

With:

```python
# After:
merged_headers = _build_codemie_tagging_headers()
if llm_model_details.configuration and llm_model_details.configuration.client_headers:
    merged_headers.update(llm_model_details.configuration.client_headers)
```

Also update the guard that conditionally sets `default_headers` (lines 388–391). Since `merged_headers` now always contains at least `X-CodeMie-Version`, it is never empty — the guard remains correct and can stay as-is:

```python
if merged_headers:
    format_headers_for_openai_api(merged_headers)
    base_args['default_headers'] = merged_headers
```

- [ ] **Step 7: Run tests to confirm GREEN**

```
pytest tests/codemie/core/test_dependencies_tagging_headers.py -v
```

Expected: 3 passed.

- [ ] **Step 8: Commit**

```bash
git add src/codemie/core/constants.py \
        src/codemie/core/dependecies.py \
        tests/codemie/core/test_dependencies_tagging_headers.py
git commit -m "EPMCDME-12602: Add X-CodeMie-Version/Project tagging headers on Azure/DIAL path"
```

---

### Task 2: Vertex AI and Anthropic path injection

**Test-first: yes — failing tests assert tag presence before factory functions are updated.**

**Files:**
- Modify: `src/codemie/core/dependecies.py` (`get_vertex_llm`, `get_anthropic_llm`)
- Modify: `tests/codemie/core/test_dependencies_tagging_headers.py` (add 2 test classes)

**Interfaces:**
- Consumes: `_build_codemie_tagging_headers()` from Task 1
- Consumes: `HEADER_CODEMIE_VERSION`, `HEADER_CODEMIE_TAGGING_PROJECT` from Task 1

---

- [ ] **Step 1: Add Vertex AI and Anthropic test classes to the existing test file**

Append to `tests/codemie/core/test_dependencies_tagging_headers.py`:

```python
class TestVertexTaggingHeaders:
    """X-CodeMie-* header injection on the Google Vertex AI path."""

    def test_tags_injected_into_client_options(self):
        """ChatVertexAI receives additional_headers with both Codemie tags."""
        from codemie.configs.config import config

        model = MagicMock()
        model.base_name = "gemini-1.5-pro"
        model.deployment_name = "gemini-1.5-pro"
        model.max_output_tokens = 8192
        model.features.streaming = True
        model.features.temperature = True
        model.features.top_p = True
        model.configuration = None

        with patch("langchain_google_vertexai.ChatVertexAI") as mock_vertex, \
             patch("codemie.core.dependecies.get_current_project", return_value="vertex-proj"), \
             patch.object(config, "APP_VERSION", "2.0.0"), \
             patch.object(config, "GOOGLE_PROJECT_ID", "test-gcp-project"), \
             patch.object(config, "GOOGLE_VERTEXAI_REGION", "us-central1"), \
             patch.object(config, "GOOGLE_VERTEXAI_MAX_RETRIES", 2):
            mock_vertex.return_value = MagicMock()
            from codemie.core.dependecies import get_vertex_llm
            from codemie.core.dependecies import llm_service as _llm_service
            with patch.object(_llm_service, "is_gemini_models", return_value=True), \
                 patch.object(_llm_service, "is_claude_models", return_value=False):
                get_vertex_llm(llm_model_details=model)

        call_kwargs = mock_vertex.call_args[1]
        headers = call_kwargs["client_options"]["additional_headers"]
        assert headers["X-CodeMie-Version"] == "2.0.0"
        assert headers["X-CodeMie-Project"] == "vertex-proj"


class TestAnthropicTaggingHeaders:
    """X-CodeMie-* header injection on the Anthropic direct path."""

    def test_tags_injected_into_extra_headers(self):
        """ChatAnthropic receives extra_headers with both Codemie tags."""
        from codemie.configs.config import config

        model = MagicMock()
        model.deployment_name = "claude-3-5-sonnet-20241022"
        model.max_output_tokens = 8192
        model.features.streaming = True
        model.features.temperature = True
        model.features.top_p = True
        model.configuration = None

        with patch("langchain_anthropic.ChatAnthropic") as mock_anthropic, \
             patch("codemie.core.dependecies.get_current_project", return_value="anthro-proj"), \
             patch.object(config, "APP_VERSION", "3.0.0"), \
             patch.object(config, "ANTHROPIC_MAX_RETRIES", 2):
            mock_anthropic.return_value = MagicMock()
            from codemie.core.dependecies import get_anthropic_llm
            get_anthropic_llm(llm_model_details=model)

        call_kwargs = mock_anthropic.call_args[1]
        extra_headers = call_kwargs["model_kwargs"]["extra_headers"]
        assert extra_headers["X-CodeMie-Version"] == "3.0.0"
        assert extra_headers["X-CodeMie-Project"] == "anthro-proj"
```

- [ ] **Step 2: Run new tests to confirm RED**

```
pytest tests/codemie/core/test_dependencies_tagging_headers.py::TestVertexTaggingHeaders \
       tests/codemie/core/test_dependencies_tagging_headers.py::TestAnthropicTaggingHeaders -v
```

Expected: 2 failures.

- [ ] **Step 3: Update `get_vertex_llm()` in `dependecies.py`**

Replace the existing merged_headers block in `get_vertex_llm` (lines ~402–405):

```python
# Before:
merged_headers = {}
if llm_model_details.configuration and llm_model_details.configuration.client_headers:
    merged_headers.update(llm_model_details.configuration.client_headers)
```

With:

```python
# After:
merged_headers = _build_codemie_tagging_headers()
if llm_model_details.configuration and llm_model_details.configuration.client_headers:
    merged_headers.update(llm_model_details.configuration.client_headers)
```

The existing guard `if merged_headers: base_args['client_options'] = ...` remains correct.

- [ ] **Step 4: Update `get_anthropic_llm()` in `dependecies.py`**

Replace the merged_headers block and model_kwargs in `get_anthropic_llm` (lines ~466–470):

```python
# Before:
merged_headers = {}
if llm_model_details.configuration and llm_model_details.configuration.client_headers:
    merged_headers.update(llm_model_details.configuration.client_headers)

model_kwargs = {"extra_headers": merged_headers if merged_headers else None}
```

With:

```python
# After:
merged_headers = _build_codemie_tagging_headers()
if llm_model_details.configuration and llm_model_details.configuration.client_headers:
    merged_headers.update(llm_model_details.configuration.client_headers)

model_kwargs = {"extra_headers": merged_headers}
```

(`merged_headers` always contains at least `X-CodeMie-Version`, so the conditional guard is dropped.)

- [ ] **Step 5: Run all tagging tests to confirm GREEN**

```
pytest tests/codemie/core/test_dependencies_tagging_headers.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/codemie/core/dependecies.py \
        tests/codemie/core/test_dependencies_tagging_headers.py
git commit -m "EPMCDME-12602: Inject tagging headers on Vertex AI and Anthropic paths"
```

---

### Task 3: LiteLLM regression assertion

**Test-first: yes — assertion is added before the LiteLLM path is verified clean.**

**Files:**
- Modify: `tests/enterprise/litellm/test_llm_factory.py` (add regression assertion to existing class)

**Interfaces:**
- Consumes: nothing from Tasks 1–2 (regression test runs against unchanged LiteLLM factory)

---

- [ ] **Step 1: Locate the existing test and add the regression assertion**

In `tests/enterprise/litellm/test_llm_factory.py`, within `TestGenerateLiteLLMHeadersFromContext`, add a new test method that directly verifies the header-generation function excludes Codemie tags:

```python
def test_no_codemie_tagging_headers_in_litellm_path(self):
    """_generate_litellm_headers must produce x-litellm-tags but not X-CodeMie-* tags."""
    from codemie.configs.config import config
    from codemie.rest_api.models.settings import LiteLLMContext, LiteLLMCredentials
    from codemie.enterprise.litellm.llm_factory import _generate_litellm_headers

    ctx = LiteLLMContext(
        credentials=LiteLLMCredentials(api_key="k", url="http://test"),
        current_project="test-project",
    )
    mock_model = MagicMock()
    mock_model.configuration = None

    with patch.object(config, "LITE_LLM_TAGS_HEADER_VALUE", "default"), \
         patch.object(config, "LITE_LLM_PROJECTS_TO_TAGS_LIST", ""):
        headers = _generate_litellm_headers(mock_model, ctx)

    assert "x-litellm-tags" in headers
    assert "X-CodeMie-Version" not in headers
    assert "X-CodeMie-Project" not in headers
```

- [ ] **Step 2: Run the regression test to confirm it passes (GREEN immediately)**

```
pytest tests/enterprise/litellm/test_llm_factory.py::TestGenerateLiteLLMHeadersFromContext::test_no_codemie_tagging_headers_in_litellm_path -v
```

Expected: PASS (LiteLLM path was not modified; this is a regression guard).

- [ ] **Step 3: Run the full tagging test suite to confirm nothing broke**

```
pytest tests/codemie/core/test_dependencies_tagging_headers.py \
       tests/enterprise/litellm/test_llm_factory.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Run linter**

```
make ruff
```

Expected: exits clean.

- [ ] **Step 5: Run license check and fix**

```
make license-check
```

If the new test file is missing the Apache header, run:

```
make license-fix
```

Then re-stage and re-commit.

- [ ] **Step 6: Commit**

```bash
git add tests/enterprise/litellm/test_llm_factory.py
git commit -m "EPMCDME-12602: Add LiteLLM regression assertion for tagging headers"
```

---

## Final verification

```
make verify
```

Expected: ruff, license, gitleaks, and tests all pass.
