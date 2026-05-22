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

"""Utility functions for processing FastAPI requests.

This module provides shared utilities for extracting and processing request data,
including custom header extraction for MCP server propagation.
"""

from fastapi import Request

from codemie.configs import config


def extract_custom_headers(raw_request: Request) -> dict[str, str] | None:
    """Extract X-* headers from the incoming request, filtering out blocked headers."""
    custom_headers = {key: value for key, value in raw_request.headers.items() if key.lower().startswith('x-')}

    if not custom_headers:
        return None

    blocked_headers = {h.strip().lower() for h in config.FORWARDED_HEADERS_BLOCKLIST.split(',')}
    filtered_headers = {key: value for key, value in custom_headers.items() if key.lower() not in blocked_headers}

    return filtered_headers if filtered_headers else None
