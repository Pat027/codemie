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

import logging

from fastapi import Request
from starlette.routing import Match

logger = logging.getLogger(__name__)


async def pyroscope_endpoint_tagging_middleware(request: Request, call_next):
    """Tag Pyroscope CPU-profile samples with the matched route template and HTTP method.

    Uses the route path template (e.g. /api/v1/users/{user_id}) rather than the
    concrete URL so that high-cardinality path params don't fragment the flame graph.
    Falls back to the raw request path when no route matches (e.g. 404s).
    """
    try:
        import pyroscope
    except ImportError:
        return await call_next(request)

    route_path = _match_route_template(request)

    with pyroscope.tag_wrapper({"http_endpoint": route_path, "http_method": request.method}):
        return await call_next(request)


def _match_route_template(request: Request) -> str:
    """Return the route path template or the raw path if no route matches."""
    try:
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                return getattr(route, "path", request.url.path)
    except Exception:
        pass
    return request.url.path
