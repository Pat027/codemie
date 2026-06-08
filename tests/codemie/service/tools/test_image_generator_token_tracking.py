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

"""Tests: ChatModelImageGenerator path attaches TokensCalculationCallback via get_llm_by_credentials."""

import unittest
from unittest.mock import MagicMock, patch

_SVC = "codemie.service.tools.toolkit_settings_service"
_IMG = "codemie_tools.data_management.file_system.image_generator"


class TestBuildImageGeneratorTokenTracking(unittest.TestCase):
    def _config_for_chat_model_path(self):
        """Patch config so only the ChatModelImageGenerator branch is reachable."""
        mock_cfg = MagicMock()
        mock_cfg.LLM_PROXY_ENABLED = False
        mock_cfg.LITE_LLM_URL = None
        mock_cfg.AZURE_OPENAI_URL = None
        mock_cfg.AZURE_OPENAI_API_KEY = None
        return patch(f"{_SVC}.config", mock_cfg)

    @patch(f"{_SVC}.ToolkitSettingService._resolve_image_generation_model", return_value="vision-model")
    @patch(f"{_SVC}.get_llm_by_credentials")
    def test_uses_get_llm_by_credentials_with_request_uuid_when_provided(self, mock_get_llm, _mock_resolve):
        from codemie.service.tools.toolkit_settings_service import ToolkitSettingService

        mock_get_llm.return_value = MagicMock()
        with self._config_for_chat_model_path():
            with patch(f"{_IMG}.ChatModelImageGenerator"):
                ToolkitSettingService._build_image_generator(assistant=MagicMock(), request_uuid="req-123")

        mock_get_llm.assert_called_once_with(llm_model="vision-model", request_id="req-123")

    @patch(f"{_SVC}.ToolkitSettingService._resolve_image_generation_model", return_value="vision-model")
    @patch(f"{_SVC}.get_llm_by_credentials")
    def test_uses_get_llm_by_credentials_with_none_when_request_uuid_absent(self, mock_get_llm, _mock_resolve):
        from codemie.service.tools.toolkit_settings_service import ToolkitSettingService

        mock_get_llm.return_value = MagicMock()
        with self._config_for_chat_model_path():
            with patch(f"{_IMG}.ChatModelImageGenerator"):
                ToolkitSettingService._build_image_generator(assistant=MagicMock(), request_uuid=None)

        mock_get_llm.assert_called_once_with(llm_model="vision-model", request_id=None)

    @patch(f"{_SVC}.ToolkitSettingService._build_image_generator")
    @patch(f"{_SVC}.FileSystemToolkit")
    @patch(f"{_SVC}.FileRepositoryFactory")
    @patch(f"{_SVC}.get_llm_by_credentials")
    def test_get_file_system_toolkit_passes_request_uuid_to_build_image_generator(
        self, mock_get_llm, mock_repo_factory, mock_fs_toolkit, mock_build_image_gen
    ):
        from codemie.service.tools.toolkit_settings_service import ToolkitSettingService

        mock_assistant = MagicMock()
        mock_assistant.context = []
        mock_user = MagicMock()
        mock_user.id = "user-1"
        mock_get_llm.return_value = MagicMock()
        mock_build_image_gen.return_value = None
        mock_fs_toolkit.get_toolkit.return_value.get_tools.return_value = []

        with patch("codemie.service.settings.settings.SettingsService.get_file_system_config", return_value=None):
            ToolkitSettingService.get_file_system_toolkit(mock_assistant, "project-1", mock_user, "gpt-4", "req-456")

        mock_build_image_gen.assert_called_once_with(mock_assistant, request_uuid="req-456")
