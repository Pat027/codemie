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

"""Provider-neutral LLM proxy lifecycle protocol.

Core code (main.py, routers, tools) depends only on this protocol.
All LiteLLM-specific lifecycle logic lives in the enterprise package
and must not leak into this module.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProxyProvider(Protocol):
    """Provider-neutral protocol for LLM proxy lifecycle management.

    Covers operations that every LLM proxy implementation must support:
    - Graceful shutdown
    - Cache maintenance (callable references safe to pass to APScheduler)
    - Cache invalidation triggered by admin actions

    Core code calls only these methods.  The active implementation is
    resolved via the provider registry and may be a noop in non-enterprise
    mode or the full LiteLLM implementation in enterprise mode.
    """

    @property
    def provider_name(self) -> str: ...

    def is_available(self) -> bool: ...

    def close(self) -> None: ...

    def clean_expired_customer_cache(self) -> None: ...

    def clean_expired_models_cache(self) -> None: ...

    def reload_models_cache(self) -> None: ...

    def get_keys_info_by_alias(
        self,
        aliases: list[str],
        include_details: bool = True,
        page: int = 1,
        size: int = 100,
    ) -> list: ...

    def get_all_keys_spending(
        self,
        include_details: bool = True,
        page: int = 1,
        size: int = 100,
    ) -> list: ...
