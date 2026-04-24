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

"""LiteLLM implementation of LLMProxyProvider.

This is the single integration boundary between core LLM proxy lifecycle
logic and the concrete LiteLLMService.  All LiteLLM-specific details are
confined here.

Core code MUST NOT import from codemie.enterprise.litellm directly for
lifecycle operations — it must go through get_active_llm_proxy_provider().
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codemie_enterprise.litellm import LiteLLMService

logger = logging.getLogger(__name__)


class LiteLLMLLMProxyProvider:
    """LiteLLM-backed implementation of LLMProxyProvider.

    Registered via ``register_llm_proxy_provider()`` when LiteLLM is enabled.
    """

    provider_name: str = "litellm"

    def __init__(self, service: "LiteLLMService") -> None:
        self._service = service

    def is_available(self) -> bool:
        return True

    def close(self) -> None:
        self._service.close()
        logger.info("LiteLLM service shutdown complete")

    def clean_expired_customer_cache(self) -> None:
        self._service.clean_expired_cache()

    def clean_expired_models_cache(self) -> None:
        self._service.clean_expired_models_cache()

    def reload_models_cache(self) -> None:
        self._service.models_cache.clear()
        logger.info("Cleared LiteLLM models cache")

    def get_keys_info_by_alias(
        self,
        aliases: list[str],
        include_details: bool = True,
        page: int = 1,
        size: int = 100,
    ) -> list:
        return self._service.get_key_info(aliases, include_details=include_details, page=page, size=size)

    def get_all_keys_spending(
        self,
        include_details: bool = True,
        page: int = 1,
        size: int = 100,
    ) -> list:
        return self._service.get_all_keys_spending(include_details=include_details, page=page, size=size)
