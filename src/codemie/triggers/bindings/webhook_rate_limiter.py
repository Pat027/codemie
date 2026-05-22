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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis as redis_lib

from codemie.clients.redis import create_redis_client
from codemie.configs import config

# Lua script: atomically increment counter and set TTL on first request in the window.
# Returns the current count after increment.
_RATE_LIMIT_LUA = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


class WebhookRateLimiter:
    def __init__(
        self,
        redis_client: redis_lib.Redis,
        max_requests: int,
        window_seconds: int,
        namespace: str,
    ) -> None:
        self._redis = redis_client
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._namespace = namespace
        self._script = redis_client.register_script(_RATE_LIMIT_LUA)

    def _redis_key(self, webhook_id: str) -> str:
        return f"{self._namespace}:{webhook_id}"

    def check_and_increment(self, webhook_id: str) -> tuple[bool, int]:
        """Increment the counter for webhook_id and check against the limit.

        Returns (is_allowed, retry_after_seconds).
        retry_after_seconds is 0 when the request is allowed.
        """
        key = self._redis_key(webhook_id)
        count: int = self._script(keys=[key], args=[self._window_seconds])
        if count > self._max_requests:
            retry_after = max(self._redis.ttl(key), 1)
            return False, retry_after
        return True, 0


_rate_limiter: WebhookRateLimiter | None = None


def get_rate_limiter() -> WebhookRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = WebhookRateLimiter(
            redis_client=create_redis_client(),
            max_requests=config.WEBHOOK_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=config.WEBHOOK_RATE_LIMIT_WINDOW_SECONDS,
            namespace=config.WEBHOOK_RATE_LIMIT_REDIS_KEY_NAMESPACE,
        )
    return _rate_limiter
