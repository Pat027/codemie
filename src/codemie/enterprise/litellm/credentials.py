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

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from cachetools import TTLCache

from codemie.configs import config, logger

if TYPE_CHECKING:
    from codemie.rest_api.models.settings import LiteLLMCredentials


@dataclass(frozen=True)
class ResolvedLiteLLMUserCredentials:
    credentials: LiteLLMCredentials
    setting_id: str
    alias: str | None = None
    is_personal: bool = True


_NO_USER_CREDENTIALS = object()
_user_credentials_cache: TTLCache = TTLCache(maxsize=4096, ttl=config.LITELLM_USER_CREDENTIALS_CACHE_TTL)


def _build_cache_key(
    user_id: str,
    project_name: str | None,
    llm_model: str | None = None,
    integration_id: str | None = None,
) -> tuple[str, str, str, str]:
    return user_id, project_name or "", llm_model or "", integration_id or ""


def clear_litellm_user_credentials_cache(user_id: str | None = None) -> None:
    if user_id is None:
        _user_credentials_cache.clear()
        return
    keys_to_delete = [key for key in _user_credentials_cache if key[0] == user_id]
    for key in keys_to_delete:
        _user_credentials_cache.pop(key, None)


def resolve_litellm_user_credentials(
    *,
    user_id: str,
    username: str,
    project_name: str | None = None,
    llm_model: str | None = None,
    integration_id: str | None = None,
) -> ResolvedLiteLLMUserCredentials | None:
    if not user_id:
        return None

    cache_key = _build_cache_key(user_id, project_name, llm_model, integration_id)
    if cache_key in _user_credentials_cache:
        cached = _user_credentials_cache[cache_key]
        return None if cached is _NO_USER_CREDENTIALS else cached

    try:
        resolved = _resolve_litellm_user_credentials_uncached(
            user_id=user_id,
            username=username,
            project_name=project_name,
            llm_model=llm_model,
            integration_id=integration_id,
        )
    except Exception as exc:
        logger.warning(
            f"credential_event=user_litellm_credentials_resolution_failed "
            f"username={username!r} user_id={user_id!r} project_name={project_name!r} "
            f"exception_type={type(exc).__name__}"
        )
        resolved = None

    _user_credentials_cache[cache_key] = resolved if resolved is not None else _NO_USER_CREDENTIALS
    return resolved


def _resolve_litellm_user_credentials_uncached(
    *,
    user_id: str,
    username: str,
    project_name: str | None,
    llm_model: str | None = None,
    integration_id: str | None = None,
) -> ResolvedLiteLLMUserCredentials | None:
    from codemie.rest_api.models.settings import SettingType
    from codemie.service.settings.base_settings import SearchFields
    from codemie.service.settings.settings import SettingsService
    from codemie_tools.base.models import CredentialTypes

    # When the caller explicitly names an integration, use it directly — personal key takes
    # precedence over any system-managed project budget key.
    if integration_id:
        from codemie.rest_api.models.settings import LiteLLMCredentials

        integration_credentials = SettingsService.get_credentials(
            credential_type=CredentialTypes.LITE_LLM,
            integration_id=integration_id,
            required_fields=SettingsService.LITELLM_FIELDS,
            credential_class=LiteLLMCredentials,
        )
        if integration_credentials and integration_credentials.api_key:
            integration_setting = SettingsService.retrieve_setting(
                {SearchFields.CREDENTIAL_TYPE: CredentialTypes.LITE_LLM},
                setting_id=integration_id,
            )
            return _build_resolved(integration_setting, integration_credentials)

    credentials = SettingsService.get_litellm_creds(project_name=project_name, user_id=user_id)
    if credentials and credentials.api_key:
        setting = SettingsService.retrieve_setting(
            {
                SearchFields.CREDENTIAL_TYPE: CredentialTypes.LITE_LLM,
                SearchFields.PROJECT_NAME: project_name,
                SearchFields.USER_ID: user_id,
            }
        )
        # A project-scoped key (e.g. platform budget key) must never qualify as a personal user
        # credential — returning it would incorrectly activate user_credentials_bypass mode.
        if getattr(setting, "setting_type", None) != SettingType.PROJECT.value:
            return _build_resolved(setting, credentials)
        logger.info(
            f"credential_event=skipped_project_scoped_setting username={username!r} "
            f"user_id={user_id!r} project_name={project_name!r} "
            f"alias={getattr(setting, 'alias', None)!r}"
        )
    else:
        logger.info(
            f"credential_event=no_user_litellm_credentials username={username!r} "
            f"user_id={user_id!r} project_name={project_name!r}"
        )

    # No personal key found — fall back to project premium key for premium models.
    if project_name and llm_model:
        return _try_resolve_premium_credentials(project_name, llm_model)

    return None


def _try_resolve_premium_credentials(
    project_name: str,
    llm_model: str,
) -> ResolvedLiteLLMUserCredentials | None:
    from codemie.enterprise.litellm.budget_categories import BudgetCategory
    from codemie.enterprise.litellm.dependencies import is_premium_model
    from codemie.service.settings.base_settings import SearchFields
    from codemie.service.settings.settings import SettingsService
    from codemie_tools.base.models import CredentialTypes

    if not is_premium_model(llm_model):
        return None
    premium_alias = f"codemie:project:{project_name}:category:{BudgetCategory.PREMIUM_MODELS.value}"
    premium_setting = SettingsService.retrieve_setting(
        {
            SearchFields.ALIAS: premium_alias,
            SearchFields.PROJECT_NAME: project_name,
            SearchFields.CREDENTIAL_TYPE: CredentialTypes.LITE_LLM,
        }
    )
    if not premium_setting:
        return None
    premium_credentials = SettingsService.get_project_litellm_creds_by_alias(project_name, premium_alias)
    if premium_credentials and premium_credentials.api_key:
        return _build_resolved(premium_setting, premium_credentials, is_personal=False)
    return None


def _build_resolved(
    setting: object, credentials: LiteLLMCredentials, *, is_personal: bool = True
) -> ResolvedLiteLLMUserCredentials:
    return ResolvedLiteLLMUserCredentials(
        credentials=credentials,
        setting_id=getattr(setting, "id", ""),
        alias=getattr(setting, "alias", None),
        is_personal=is_personal,
    )


def get_litellm_credentials_for_user(user_id: str, user_applications: list[str]) -> Optional[LiteLLMCredentials]:
    """
    Get LiteLLM credentials for user from core SettingsService.

    This compatibility helper keeps the legacy lookup behavior used by callers
    outside the proxy runtime. The proxy runtime uses
    resolve_litellm_user_credentials() so project credentials are not selected
    by request headers.
    """
    from codemie.core.exceptions import ExtendedHTTPException
    from codemie.service.settings.settings import SettingsService

    try:
        creds = SettingsService.get_litellm_creds(project_name=None, user_id=user_id)
        if creds:
            logger.debug(f"Found user-level LiteLLM credentials for {user_id}")
            return creds
    except (ExtendedHTTPException, ValueError, KeyError) as e:
        logger.debug(f"No user-level LiteLLM credentials for {user_id}: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error retrieving user-level LiteLLM credentials for {user_id}: {e}")

    if user_applications:
        for app in user_applications:
            try:
                creds = SettingsService.get_litellm_creds(project_name=app, user_id=user_id)
                if creds:
                    logger.debug(f"Found app-level LiteLLM credentials for {user_id} in {app}")
                    return creds
            except (ExtendedHTTPException, ValueError, KeyError) as e:
                logger.debug(f"No LiteLLM credentials for {user_id} in {app}: {e}")
                continue
            except Exception as e:
                logger.warning(f"Unexpected error retrieving LiteLLM credentials for {user_id} in {app}: {e}")
                continue

    return None
