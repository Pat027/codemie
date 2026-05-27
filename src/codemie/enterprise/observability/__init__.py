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

"""Observability abstraction layer.

Provider-agnostic interface for LLM tracing. Supports Langfuse, Arize Phoenix,
and a no-op fallback. Provider is selected via OBSERVABILITY_PROVIDER config.

Usage:
    from codemie.enterprise.observability import get_observability_provider

    provider = get_observability_provider()
    handler = provider.get_callback_handler()  # None for Phoenix (uses OTEL auto-instrumentation)
    if handler:
        callbacks.append(handler)
"""

from .base import ObservabilityProvider
from .factory import get_observability_provider, reset_provider

__all__ = [
    "ObservabilityProvider",
    "get_observability_provider",
    "reset_provider",
]
