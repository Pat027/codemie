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

"""Shared OAuth HTML utilities for callback pages."""

import html


def html_success_page(message: str) -> str:
    """Generate OAuth success callback HTML page.

    Args:
        message: Success message to display.

    Returns:
        Complete HTML page string.
    """
    escaped = html.escape(message)
    body = f"<h2>Authentication Complete</h2><p>{escaped}</p><p>You can close this window.</p>"
    return f"<!DOCTYPE html><html><head><meta charset='UTF-8'></head><body>{body}</body></html>"


def html_error_page(message: str) -> str:
    """Generate OAuth error callback HTML page.

    Args:
        message: Error message to display.

    Returns:
        Complete HTML page string.
    """
    escaped = html.escape(message)
    body = (
        f"<h2>Authentication Failed</h2><p>{escaped}</p><p>You can close this window and return to the application.</p>"
    )
    return f"<!DOCTYPE html><html><head><meta charset='UTF-8'></head><body>{body}</body></html>"
