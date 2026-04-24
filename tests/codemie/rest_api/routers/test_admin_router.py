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

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from codemie.rest_api.routers.admin import add_application, get_applications, get_speech_token, reload_llm_models
from codemie.rest_api.security.user import User


def test_get_applications_returns_application_names():
    applications = [SimpleNamespace(name="proj-a"), SimpleNamespace(name="proj-b")]

    with patch("codemie.rest_api.routers.admin.Application.search_by_name", return_value=applications):
        response = get_applications(search="proj", limit=2)

    assert response.applications == ["proj-a", "proj-b"]


def test_add_application_creates_application_and_emits_metric():
    admin = User(id="admin-1", username="admin", email="admin@example.com", is_admin=True)
    request = SimpleNamespace(name="proj-a")

    with (
        patch("codemie.service.user.application_service.application_service.create_application") as mock_create,
        patch("codemie.rest_api.routers.admin.ProjectMonitoringService.send_project_creation_metric") as mock_metric,
    ):
        mock_create.return_value = SimpleNamespace(name="proj-a")
        response = add_application(request, admin=admin)

    assert response.message == f"Application {request} has been created"
    mock_create.assert_called_once_with("proj-a")
    mock_metric.assert_called_once_with(user=admin, project_name="proj-a")


def test_get_speech_token_uses_config_values():
    with patch("codemie.rest_api.routers.admin.config") as mock_config:
        mock_config.AZURE_SPEECH_SERVICE_KEY = "speech-token"
        mock_config.AZURE_SPEECH_REGION = "westus"

        response = get_speech_token()

    assert response == {
        "token": "speech-token",
        "region": "westus",
        "stt_wss_url": "wss://westus.stt.speech.microsoft.com/speech/universal/v2",
        "tts_url": "https://westus.tts.speech.microsoft.com/cognitiveservices/avatar/relay/token/v1",
    }


@pytest.mark.asyncio
async def test_reload_llm_models_refreshes_proxy_models():
    admin = User(id="admin-1", username="admin", email="admin@example.com", is_admin=True)
    models = SimpleNamespace(chat_models=["chat-1", "chat-2"], embedding_models=["embed-1"])
    proxy_provider = SimpleNamespace(reload_models_cache=MagicMock())
    llm_service = SimpleNamespace(initialize_default_litellm_models=MagicMock())

    with (
        patch("codemie.enterprise.litellm.require_litellm_enabled") as mock_require,
        patch("codemie.enterprise.litellm.get_available_models", return_value=models),
        patch(
            "codemie.service.llm_proxy.provider_registry.get_active_llm_proxy_provider",
            return_value=proxy_provider,
        ),
        patch("codemie.service.llm_service.llm_service.llm_service", llm_service),
    ):
        response = await reload_llm_models(admin=admin)

    assert response.message == "Successfully reloaded LLM models: 2 chat models, 1 embedding models"
    mock_require.assert_called_once_with()
    proxy_provider.reload_models_cache.assert_called_once_with()
    llm_service.initialize_default_litellm_models.assert_called_once_with(models)
