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

import functools
import inspect
import json
import logging
import os
import socket
from collections.abc import Callable
from typing import Any

from codemie.configs.config import config

logger = logging.getLogger(__name__)


def configure_pyroscope() -> None:
    """Initialize Grafana Pyroscope continuous CPU profiling.

    When PYROSCOPE_ENABLED=False this is a no-op.  Automatically enriches
    global tags with deployment metadata (env, version, hostname, pod name).

    Config knobs (all via environment or .env):
      PYROSCOPE_ENABLED           — master switch (default: False)
      PYROSCOPE_SERVER_URL        — Pyroscope / Grafana Alloy push endpoint
      PYROSCOPE_APP_NAME          — application name shown in Pyroscope UI
      PYROSCOPE_SAMPLE_RATE       — samples per second (default: 100)
      PYROSCOPE_ONCPU             — enable CPU (wall-clock) profiling
      PYROSCOPE_GIL_ONLY          — restrict to GIL-holding threads only
      PYROSCOPE_ENABLE_LOGGING    — verbose pyroscope-io internal logs
      PYROSCOPE_TAGS              — extra global tags as JSON or "k=v,k=v"
    """
    if not config.PYROSCOPE_ENABLED:
        return

    try:
        import pyroscope
    except ImportError:
        logger.warning("pyroscope-io not installed; Pyroscope profiling disabled")
        return

    tags = _build_tags()

    pyroscope.configure(
        application_name=config.PYROSCOPE_APP_NAME,
        report_pid=True,
        report_thread_id=True,
        report_thread_name=True,
        server_address=config.PYROSCOPE_SERVER_URL,
        sample_rate=config.PYROSCOPE_SAMPLE_RATE,
        oncpu=config.PYROSCOPE_ONCPU,
        gil_only=config.PYROSCOPE_GIL_ONLY,
        enable_logging=config.PYROSCOPE_ENABLE_LOGGING,
        tags=tags,
    )

    logger.info(
        f"Pyroscope profiling enabled: app={config.PYROSCOPE_APP_NAME} server={config.PYROSCOPE_SERVER_URL} tags={tags}"
    )


def pyroscope_profile(tags_fn: Callable[..., dict[str, str]]) -> Callable[[Any], Any]:
    """Decorator that tags Pyroscope CPU samples with per-call dynamic tags.

    When PYROSCOPE_ENABLED=False the original function is returned unchanged —
    zero overhead, no wrapping at all.

    ``tags_fn`` is called with the same positional and keyword arguments as the
    decorated function and must return a ``dict[str, str]`` of tags to attach.
    Both sync and async functions are supported.

    Usage::

        @pyroscope_profile(lambda self, request, *a, **kw: {
            "operation": "assistant",
            "assistant_id": request.assistant_id,
            "project": request.project,
        })
        def process_request(self, request, ...):
            ...
    """

    def decorator(fn: Callable) -> Callable:
        if not config.PYROSCOPE_ENABLED:
            return fn

        try:
            import pyroscope
        except ImportError:
            return fn

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                tags = tags_fn(*args, **kwargs)
                with pyroscope.tag_wrapper(tags):
                    return await fn(*args, **kwargs)

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            tags = tags_fn(*args, **kwargs)
            with pyroscope.tag_wrapper(tags):
                return fn(*args, **kwargs)

        return sync_wrapper

    return decorator


def _build_tags() -> dict[str, str]:
    """Merge auto-detected deployment metadata with user-supplied PYROSCOPE_TAGS."""
    auto_tags: dict[str, str] = {
        "env": config.ENV,
        "version": config.APP_VERSION,
        "hostname": os.environ.get("POD_NAME") or socket.gethostname(),
    }
    namespace = os.environ.get("POD_NAMESPACE")
    if namespace:
        auto_tags["k8s_namespace"] = namespace

    user_tags = _parse_tags(config.PYROSCOPE_TAGS)
    # user-supplied tags override auto-detected ones
    return {**auto_tags, **user_tags}


def _parse_tags(tags_str: str) -> dict[str, str]:
    """Parse tags from JSON object or 'key=value,key=value' string."""
    if not tags_str:
        return {}
    stripped = tags_str.strip()
    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse PYROSCOPE_TAGS as JSON: {stripped!r}")
            return {}
    result: dict[str, str] = {}
    for pair in stripped.split(","):
        if "=" in pair:
            key, _, value = pair.partition("=")
            result[key.strip()] = value.strip()
    return result
