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

"""Verify webhook_rate_limiter can be imported without the redis package installed."""

import importlib
import sys


def test_webhook_rate_limiter_importable_without_redis():
    """Module must not require redis at import time (redis is a transient dep of codemie-enterprise)."""
    # Remove the module from sys.modules so it is re-imported fresh
    sys.modules.pop("codemie.triggers.bindings.webhook_rate_limiter", None)
    # Temporarily hide redis from the import system
    redis_mod = sys.modules.pop("redis", None)
    try:
        importlib.import_module("codemie.triggers.bindings.webhook_rate_limiter")
    except ImportError as exc:
        raise AssertionError("webhook_rate_limiter must be importable without redis installed") from exc
    finally:
        # Restore original module state
        sys.modules.pop("codemie.triggers.bindings.webhook_rate_limiter", None)
        if redis_mod is not None:
            sys.modules["redis"] = redis_mod
