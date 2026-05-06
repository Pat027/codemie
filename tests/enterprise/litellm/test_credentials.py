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

"""Tests for LiteLLM credentials retrieval (codemie.enterprise.litellm.credentials)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _setting(
    *,
    setting_id: str,
    alias: str,
    api_key: str,
    default: bool = False,
    project_name: str = "project-a",
    setting_type: str = "user",
) -> MagicMock:
    setting = MagicMock()
    setting.id = setting_id
    setting.alias = alias
    setting.default = default
    setting.project_name = project_name
    setting.setting_type = setting_type
    setting.normalize_values.return_value = {"api_key": api_key, "url": "https://litellm.local"}
    setting.credential.side_effect = {"api_key": api_key, "url": "https://litellm.local"}.get
    return setting


class TestGetLiteLLMCredentialsForUser:
    """Test get_litellm_credentials_for_user() function."""

    def test_returns_user_level_credentials_when_found(self):
        """Test returns user-level credentials when found."""
        from codemie.rest_api.models.settings import LiteLLMCredentials

        mock_credentials = LiteLLMCredentials(api_key="sk-user-key", url="http://localhost:4000")

        with patch(
            "codemie.service.settings.settings.SettingsService.get_litellm_creds", return_value=mock_credentials
        ) as mock_get_creds:
            from codemie.enterprise.litellm.credentials import get_litellm_credentials_for_user

            result = get_litellm_credentials_for_user(user_id="test-user", user_applications=["app1", "app2"])

            # Should return user-level credentials
            assert result is mock_credentials
            assert result.api_key == "sk-user-key"

            # Should have checked user-level first (project_name=None)
            mock_get_creds.assert_called_once_with(project_name=None, user_id="test-user")

    def test_returns_application_level_credentials_when_user_level_not_found(self):
        """Test returns app-level credentials when user-level not found."""
        from codemie.rest_api.models.settings import LiteLLMCredentials

        mock_app_credentials = LiteLLMCredentials(api_key="sk-app-key", url="http://localhost:4000")

        def get_creds_side_effect(project_name, user_id):
            if project_name is None:
                # User-level not found
                raise Exception("Not found")
            elif project_name == "app1":
                # App-level found
                return mock_app_credentials
            else:
                raise Exception("Not found")

        with patch(
            "codemie.service.settings.settings.SettingsService.get_litellm_creds", side_effect=get_creds_side_effect
        ) as mock_get_creds:
            from codemie.enterprise.litellm.credentials import get_litellm_credentials_for_user

            result = get_litellm_credentials_for_user(user_id="test-user", user_applications=["app1", "app2"])

            # Should return app-level credentials
            assert result is mock_app_credentials
            assert result.api_key == "sk-app-key"

            # Should have checked user-level first, then app1
            assert mock_get_creds.call_count == 2

    def test_checks_all_applications_in_order(self):
        """Test checks all applications in order until credentials found."""
        from codemie.rest_api.models.settings import LiteLLMCredentials

        mock_app2_credentials = LiteLLMCredentials(api_key="sk-app2-key", url="http://localhost:4000")

        def get_creds_side_effect(project_name, user_id):
            if project_name is None:
                # User-level not found
                raise Exception("Not found")
            elif project_name == "app1":
                # App1-level not found
                raise Exception("Not found")
            elif project_name == "app2":
                # App2-level found
                return mock_app2_credentials
            else:
                raise Exception("Not found")

        with patch(
            "codemie.service.settings.settings.SettingsService.get_litellm_creds", side_effect=get_creds_side_effect
        ) as mock_get_creds:
            from codemie.enterprise.litellm.credentials import get_litellm_credentials_for_user

            result = get_litellm_credentials_for_user(user_id="test-user", user_applications=["app1", "app2", "app3"])

            # Should return app2-level credentials
            assert result is mock_app2_credentials
            assert result.api_key == "sk-app2-key"

            # Should have checked user-level, app1, and app2 (stops at app2)
            assert mock_get_creds.call_count == 3

    def test_returns_none_when_no_credentials_found(self):
        """Test returns None when no credentials found anywhere."""
        with patch(
            "codemie.service.settings.settings.SettingsService.get_litellm_creds", side_effect=Exception("Not found")
        ) as mock_get_creds:
            from codemie.enterprise.litellm.credentials import get_litellm_credentials_for_user

            result = get_litellm_credentials_for_user(user_id="test-user", user_applications=["app1", "app2"])

            # Should return None
            assert result is None

            # Should have checked user-level and all apps
            assert mock_get_creds.call_count == 3  # user + app1 + app2

    def test_returns_none_when_no_applications(self):
        """Test returns None when user has no applications and no user-level creds."""
        with patch(
            "codemie.service.settings.settings.SettingsService.get_litellm_creds", side_effect=Exception("Not found")
        ) as mock_get_creds:
            from codemie.enterprise.litellm.credentials import get_litellm_credentials_for_user

            result = get_litellm_credentials_for_user(user_id="test-user", user_applications=[])

            # Should return None
            assert result is None

            # Should have checked only user-level
            assert mock_get_creds.call_count == 1

    def test_logs_debug_messages_on_success(self):
        """Test logs debug messages when credentials found."""
        from codemie.rest_api.models.settings import LiteLLMCredentials

        mock_credentials = LiteLLMCredentials(api_key="sk-user-key", url="http://localhost:4000")

        with (
            patch("codemie.service.settings.settings.SettingsService.get_litellm_creds", return_value=mock_credentials),
            patch("codemie.enterprise.litellm.credentials.logger") as mock_logger,
        ):
            from codemie.enterprise.litellm.credentials import get_litellm_credentials_for_user

            get_litellm_credentials_for_user(user_id="test-user", user_applications=["app1"])

            # Should have logged success
            mock_logger.debug.assert_called_once()
            call_args = mock_logger.debug.call_args[0][0]
            assert "Found user-level LiteLLM credentials" in call_args
            assert "test-user" in call_args

    def test_logs_debug_messages_on_failure(self):
        """Test logs debug/warning messages when credentials not found."""
        with (
            patch(
                "codemie.service.settings.settings.SettingsService.get_litellm_creds",
                side_effect=Exception("Not found"),
            ),
            patch("codemie.enterprise.litellm.credentials.logger") as mock_logger,
        ):
            from codemie.enterprise.litellm.credentials import get_litellm_credentials_for_user

            get_litellm_credentials_for_user(user_id="test-user", user_applications=["app1"])

            # Should have logged failures (warning for unexpected exceptions)
            # Since we raise generic Exception, it's logged as warning, not debug
            assert mock_logger.warning.call_count >= 1
            # At least one call should mention error retrieving credentials
            warning_calls = [call[0][0] for call in mock_logger.warning.call_args_list]
            assert any("error" in msg.lower() and "credentials" in msg.lower() for msg in warning_calls)

    def test_logs_debug_for_expected_exceptions(self):
        """Test logs debug (not warning) for expected exceptions like ValueError."""
        with (
            patch(
                "codemie.service.settings.settings.SettingsService.get_litellm_creds",
                side_effect=ValueError("Invalid credentials"),
            ),
            patch("codemie.enterprise.litellm.credentials.logger") as mock_logger,
        ):
            from codemie.enterprise.litellm.credentials import get_litellm_credentials_for_user

            get_litellm_credentials_for_user(user_id="test-user", user_applications=["app1"])

            # Should have logged with debug (expected exception)
            assert mock_logger.debug.call_count >= 1
            # Should NOT have logged warnings for expected exceptions
            assert mock_logger.warning.call_count == 0
            # At least one debug call should mention no credentials
            debug_calls = [call[0][0] for call in mock_logger.debug.call_args_list]
            assert any("No" in msg and "credentials" in msg for msg in debug_calls)

    def test_stops_at_first_valid_credentials(self):
        """Test stops searching when first valid credentials found (doesn't check remaining apps)."""
        from codemie.rest_api.models.settings import LiteLLMCredentials

        mock_credentials = LiteLLMCredentials(api_key="sk-app1-key", url="http://localhost:4000")

        def get_creds_side_effect(project_name, user_id):
            if project_name is None:
                # User-level not found
                raise Exception("Not found")
            elif project_name == "app1":
                # App1-level found
                return mock_credentials
            else:
                # Should never be called for app2
                raise AssertionError("Should not check app2")

        with patch(
            "codemie.service.settings.settings.SettingsService.get_litellm_creds", side_effect=get_creds_side_effect
        ) as mock_get_creds:
            from codemie.enterprise.litellm.credentials import get_litellm_credentials_for_user

            result = get_litellm_credentials_for_user(user_id="test-user", user_applications=["app1", "app2"])

            # Should return app1 credentials
            assert result is mock_credentials

            # Should have checked user-level and app1 only (not app2)
            assert mock_get_creds.call_count == 2


class TestResolveLiteLLMUserCredentials:
    def setup_method(self):
        from codemie.enterprise.litellm.credentials import clear_litellm_user_credentials_cache

        clear_litellm_user_credentials_cache()

    def teardown_method(self):
        from codemie.enterprise.litellm.credentials import clear_litellm_user_credentials_cache

        clear_litellm_user_credentials_cache()

    def test_resolves_credentials_via_settings_service_for_current_project(self):
        from codemie.enterprise.litellm.credentials import resolve_litellm_user_credentials
        from codemie.rest_api.models.settings import LiteLLMCredentials

        credentials = LiteLLMCredentials(api_key="sk-default", url="https://litellm.local")
        setting = _setting(setting_id="s2", alias="default-key", api_key="sk-default")

        with (
            patch(
                "codemie.service.settings.settings.SettingsService.get_litellm_creds",
                return_value=credentials,
            ) as mock_get_creds,
            patch(
                "codemie.service.settings.settings.SettingsService.retrieve_setting",
                return_value=setting,
            ) as mock_retrieve,
        ):
            result = resolve_litellm_user_credentials(
                user_id="user-1",
                username="user@example.com",
                project_name="project-a",
            )

        assert result is not None
        assert result.credentials.api_key == "sk-default"
        assert result.alias == "default-key"
        assert result.setting_id == "s2"
        mock_get_creds.assert_called_once_with(project_name="project-a", user_id="user-1")
        mock_retrieve.assert_called_once()

    def test_returns_none_when_settings_service_has_no_credentials(self):
        from codemie.enterprise.litellm.credentials import resolve_litellm_user_credentials

        with patch("codemie.service.settings.settings.SettingsService.get_litellm_creds", return_value=None):
            result = resolve_litellm_user_credentials(
                user_id="user-1",
                username="user@example.com",
                project_name="project-a",
            )

        assert result is None

    def test_returns_none_when_resolved_credentials_have_empty_api_key(self):
        from codemie.enterprise.litellm.credentials import resolve_litellm_user_credentials
        from codemie.rest_api.models.settings import LiteLLMCredentials

        with patch(
            "codemie.service.settings.settings.SettingsService.get_litellm_creds",
            return_value=LiteLLMCredentials(api_key="", url="https://litellm.local"),
        ):
            result = resolve_litellm_user_credentials(
                user_id="user-1",
                username="user@example.com",
                project_name="project-a",
            )

        assert result is None

    def test_returns_none_when_no_user_id(self):
        from codemie.enterprise.litellm.credentials import resolve_litellm_user_credentials

        result = resolve_litellm_user_credentials(
            user_id="",
            username="user@example.com",
            project_name="project-a",
        )

        assert result is None

    def test_logs_warning_and_returns_none_when_resolution_raises(self):
        from codemie.enterprise.litellm.credentials import resolve_litellm_user_credentials

        with (
            patch(
                "codemie.service.settings.settings.SettingsService.get_litellm_creds",
                side_effect=RuntimeError("boom"),
            ),
            patch("codemie.enterprise.litellm.credentials.logger") as mock_logger,
        ):
            result = resolve_litellm_user_credentials(
                user_id="user-1",
                username="user@example.com",
                project_name="project-a",
            )

        assert result is None
        warning = mock_logger.warning.call_args[0][0]
        assert "user_litellm_credentials_resolution_failed" in warning
        assert "username='user@example.com'" in warning
        assert "user_id='user-1'" in warning
        assert "project_name='project-a'" in warning
        assert "exception_type=RuntimeError" in warning

    def test_caches_positive_result_per_project(self):
        from codemie.enterprise.litellm.credentials import resolve_litellm_user_credentials
        from codemie.rest_api.models.settings import LiteLLMCredentials

        project_a_credentials = LiteLLMCredentials(api_key="sk-project-a", url="https://litellm.local")
        project_b_credentials = LiteLLMCredentials(api_key="sk-project-b", url="https://litellm.local")
        project_a_setting = _setting(setting_id="s1", alias="key-a", api_key="sk-project-a", project_name="project-a")
        project_b_setting = _setting(setting_id="s2", alias="key-b", api_key="sk-project-b", project_name="project-b")

        with (
            patch(
                "codemie.service.settings.settings.SettingsService.get_litellm_creds",
                side_effect=[project_a_credentials, project_b_credentials],
            ) as mock_get,
            patch(
                "codemie.service.settings.settings.SettingsService.retrieve_setting",
                side_effect=[project_a_setting, project_b_setting],
            ),
        ):
            first = resolve_litellm_user_credentials(
                user_id="user-1",
                username="user@example.com",
                project_name="project-a",
            )
            second = resolve_litellm_user_credentials(
                user_id="user-1",
                username="user@example.com",
                project_name="project-b",
            )
            third = resolve_litellm_user_credentials(
                user_id="user-1",
                username="user@example.com",
                project_name="project-a",
            )

        assert first is not None
        assert second is not None
        assert third is not None
        assert first.credentials.api_key == "sk-project-a"
        assert second.credentials.api_key == "sk-project-b"
        assert third.credentials.api_key == "sk-project-a"
        assert mock_get.call_count == 2

    def test_caches_negative_result_per_project(self):
        from codemie.enterprise.litellm.credentials import resolve_litellm_user_credentials

        with patch(
            "codemie.service.settings.settings.SettingsService.get_litellm_creds",
            side_effect=[None, None],
        ) as mock_get:
            first = resolve_litellm_user_credentials(
                user_id="user-1",
                username="user@example.com",
                project_name="project-a",
            )
            second = resolve_litellm_user_credentials(
                user_id="user-1",
                username="user@example.com",
                project_name="project-b",
            )
            third = resolve_litellm_user_credentials(
                user_id="user-1",
                username="user@example.com",
                project_name="project-a",
            )

        assert first is None
        assert second is None
        assert third is None
        assert mock_get.call_count == 2

    def test_cache_can_be_cleared_for_all_project_entries_of_user(self):
        from codemie.enterprise.litellm.credentials import (
            clear_litellm_user_credentials_cache,
            resolve_litellm_user_credentials,
        )
        from codemie.rest_api.models.settings import LiteLLMCredentials

        credentials = LiteLLMCredentials(api_key="sk-only", url="https://litellm.local")
        setting = _setting(setting_id="s1", alias="only-key", api_key="sk-only")

        with (
            patch(
                "codemie.service.settings.settings.SettingsService.get_litellm_creds",
                return_value=credentials,
            ) as mock_get,
            patch(
                "codemie.service.settings.settings.SettingsService.retrieve_setting",
                return_value=setting,
            ),
        ):
            resolve_litellm_user_credentials(
                user_id="user-1",
                username="user@example.com",
                project_name="project-a",
            )
            resolve_litellm_user_credentials(
                user_id="user-1",
                username="user@example.com",
                project_name="project-b",
            )
            clear_litellm_user_credentials_cache("user-1")
            resolve_litellm_user_credentials(
                user_id="user-1",
                username="user@example.com",
                project_name="project-a",
            )
            resolve_litellm_user_credentials(
                user_id="user-1",
                username="user@example.com",
                project_name="project-b",
            )

        assert mock_get.call_count == 4

    def test_create_user_litellm_setting_clears_user_cache(self):
        from codemie.rest_api.models.settings import CredentialValues, SettingRequest
        from codemie.service.settings.settings import SettingsService
        from codemie_tools.base.models import CredentialTypes

        request = SettingRequest(
            project_name="project-a",
            alias="user-litellm",
            credential_type=CredentialTypes.LITE_LLM,
            credential_values=[CredentialValues(key="api_key", value="sk-user")],
        )

        with (
            patch("codemie.rest_api.models.settings.Settings.check_alias_unique"),
            patch("codemie.service.settings.settings.SettingsService.check_webhook_unique"),
            patch(
                "codemie.service.settings.settings.SettingsService._prepare_cred_values",
                return_value=request.credential_values,
            ),
            patch(
                "codemie.service.settings.settings.SettingsService._encrypt_fields",
                return_value=request.credential_values,
            ),
            patch("codemie.service.settings.settings.ensure_application_exists"),
            patch("codemie.service.settings.settings.Settings") as mock_settings_model,
            patch("codemie.enterprise.litellm.credentials.clear_litellm_user_credentials_cache") as mock_clear,
        ):
            mock_settings_model.return_value.save.return_value = SimpleNamespace(id="setting-1")

            SettingsService.create_setting(user_id="user-1", request=request)

        mock_clear.assert_called_once_with("user-1")

    def test_update_user_litellm_setting_clears_user_cache(self):
        from codemie.rest_api.models.settings import CredentialValues, SettingRequest
        from codemie.service.settings.settings import SettingsService
        from codemie_tools.base.models import CredentialTypes

        request = SettingRequest(
            project_name="project-a",
            alias="user-litellm",
            credential_type=CredentialTypes.LITE_LLM,
            credential_values=[CredentialValues(key="api_key", value="sk-user")],
        )
        existing = MagicMock()
        existing.credential_values = []
        existing.user_id = "user-1"

        with (
            patch("codemie.rest_api.models.settings.Settings.check_alias_unique"),
            patch("codemie.service.settings.settings.SettingsService.check_webhook_unique"),
            patch("codemie.rest_api.models.settings.Settings.get_by_id", return_value=existing),
            patch(
                "codemie.service.settings.settings.SettingsService._prepare_cred_values",
                return_value=request.credential_values,
            ),
            patch("codemie.service.settings.settings.SettingsService._handle_new_creds"),
            patch("codemie.enterprise.litellm.credentials.clear_litellm_user_credentials_cache") as mock_clear,
        ):
            SettingsService.update_settings(
                credential_id="setting-1",
                request=request,
                user_id="user-1",
            )

        mock_clear.assert_called_once_with("user-1")

    def test_delete_user_litellm_setting_clears_user_cache(self):
        from codemie.rest_api.routers.user_settings import delete_user_setting
        from codemie_tools.base.models import CredentialTypes

        user = MagicMock()
        user.id = "user-1"
        setting_ability = MagicMock()
        setting_ability.credential_type = CredentialTypes.LITE_LLM

        with (
            patch(
                "codemie.rest_api.routers.user_settings.SettingsService.get_setting_ability",
                return_value=setting_ability,
            ),
            patch("codemie.rest_api.routers.user_settings.Ability") as mock_ability,
            patch("codemie.rest_api.routers.user_settings.BedrockOrchestratorService.delete_all_entities"),
            patch("codemie.rest_api.routers.user_settings.SettingsService.delete_setting") as mock_delete,
        ):
            mock_ability.return_value.can.return_value = True

            delete_user_setting(setting_id="setting-1", user=user)

        mock_delete.assert_called_once_with(credential_id="setting-1", user_id="user-1")

    def test_returns_none_when_retrieved_setting_is_project_scoped(self):
        """Project-scoped keys (e.g. platform budget key) must not activate user_credentials_bypass."""
        from codemie.enterprise.litellm.credentials import resolve_litellm_user_credentials
        from codemie.rest_api.models.settings import LiteLLMCredentials

        credentials = LiteLLMCredentials(api_key="sk-platform", url="https://litellm.local")
        project_setting = _setting(
            setting_id="s-platform",
            alias="codemie:project:project-a:category:platform",
            api_key="sk-platform",
            setting_type="project",
        )

        with (
            patch(
                "codemie.service.settings.settings.SettingsService.get_litellm_creds",
                return_value=credentials,
            ),
            patch(
                "codemie.service.settings.settings.SettingsService.retrieve_setting",
                return_value=project_setting,
            ),
        ):
            result = resolve_litellm_user_credentials(
                user_id="user-1",
                username="user@example.com",
                project_name="project-a",
            )

        assert result is None

    def test_resolves_credentials_via_explicit_integration_id(self):
        """When integration_id is supplied it takes precedence over the project fallback."""
        from codemie.enterprise.litellm.credentials import resolve_litellm_user_credentials
        from codemie.rest_api.models.settings import LiteLLMCredentials

        integration_creds = LiteLLMCredentials(api_key="sk-integration", url="https://litellm.local")
        integration_setting = _setting(
            setting_id="integration-1",
            alias="personal-integration",
            api_key="sk-integration",
            setting_type="user",
        )

        with (
            patch(
                "codemie.service.settings.settings.SettingsService.get_credentials",
                return_value=integration_creds,
            ),
            patch(
                "codemie.service.settings.settings.SettingsService.retrieve_setting",
                return_value=integration_setting,
            ),
        ):
            result = resolve_litellm_user_credentials(
                user_id="user-1",
                username="user@example.com",
                project_name="project-a",
                integration_id="integration-1",
            )

        assert result is not None
        assert result.credentials.api_key == "sk-integration"
        assert result.alias == "personal-integration"
        assert result.setting_id == "integration-1"
