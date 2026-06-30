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

import re
from typing import Literal

from fastapi import status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from codemie.configs.logger import logger

_LOG_UNSAFE_CHARS = re.compile(r"[\r\n\x00-\x1f\x7f]")


def _sanitize_log_value(value: str | None) -> str | None:
    """Neutralize CR/LF/control chars in client-supplied values before logging (CWE-117).

    The diagnostics endpoint is unauthenticated, so its string fields are
    attacker-controllable; sanitizing at the source keeps the log line safe
    regardless of the logger's own escaping or the runtime environment.
    """
    if value is None:
        return None
    return _LOG_UNSAFE_CHARS.sub(" ", value)


class OAuth2CallbackDiagnostics(BaseModel):
    """Client-reported outcome of the OAuth2 callback bridge page.

    Diagnostics only. The bridge page (which closes itself) reports whether it
    could notify the opener window, so the otherwise-unobservable client step
    lands in the backend logs. Carries no secrets — only non-secret identifiers,
    origins, booleans, and error codes. Unknown fields are ignored, never logged.
    """

    model_config = ConfigDict(extra="ignore")

    result: Literal["success", "error"]
    auth_config_id: str | None = Field(default=None, max_length=256)
    opener_present: bool
    target_origin: str | None = Field(default=None, max_length=256)
    post_message_attempted: bool = False
    post_message_error: str | None = Field(default=None, max_length=512)
    window_should_close: bool = False
    bridge_error_code: str | None = Field(default=None, max_length=128)
    idp_error_code: str | None = Field(default=None, max_length=128)


def build_oauth2_callback_diagnostics_response(payload: OAuth2CallbackDiagnostics) -> Response:
    """Log the client-side callback outcome and return an empty 204.

    Failure-shaped outcomes (an ``error`` result, a lost ``window.opener``, or a
    ``postMessage`` exception) log at WARNING so they are easy to find; clean
    successes log at INFO.
    """

    message = (
        "MCP OAuth2 callback client diagnostics: "
        f"result={payload.result} auth_config_id={_sanitize_log_value(payload.auth_config_id)} "
        f"opener_present={payload.opener_present} target_origin={_sanitize_log_value(payload.target_origin)} "
        f"post_message_attempted={payload.post_message_attempted} "
        f"post_message_error={_sanitize_log_value(payload.post_message_error)} "
        f"window_should_close={payload.window_should_close} "
        f"bridge_error_code={_sanitize_log_value(payload.bridge_error_code)} "
        f"idp_error_code={_sanitize_log_value(payload.idp_error_code)}"
    )
    if payload.result == "error" or not payload.opener_present or payload.post_message_error:
        logger.warning(message)
    else:
        logger.info(message)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
