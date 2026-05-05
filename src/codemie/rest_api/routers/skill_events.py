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

"""REST endpoint for `codemie skill *` lifecycle events.

Persists each event into Postgres (authoritative, durable) and mirrors it
into the existing Elastic-backed metrics path so legacy dashboards keep
working during the transition. The Elastic mirror can be removed in a
follow-up once analytics handlers read directly from Postgres.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, status

from codemie.configs import logger
from codemie.core.constants import HEADER_CODEMIE_CLI, HEADER_CODEMIE_CLIENT
from codemie.core.exceptions import ExtendedHTTPException
from codemie.rest_api.models.skill_event import SkillEventRequest, SkillEventResponse
from codemie.rest_api.security.authentication import authenticate
from codemie.rest_api.security.user import User
from codemie.service.skill_event_service import skill_event_service


router = APIRouter(
    tags=["Skills"],
    prefix="/v1/skills",
    dependencies=[Depends(authenticate)],
)


@router.post(
    "/events",
    status_code=status.HTTP_200_OK,
    response_model=SkillEventResponse,
    response_model_by_alias=True,
)
def record_skill_event(
    request: SkillEventRequest,
    user: User = Depends(authenticate),
    x_codemie_cli: Annotated[str | None, Header(alias=HEADER_CODEMIE_CLI)] = None,
    x_codemie_client: Annotated[str | None, Header(alias=HEADER_CODEMIE_CLIENT)] = None,
) -> SkillEventResponse:
    """Record a single `codemie skill *` lifecycle event.

    The CLI fans out multi-skill operations into one POST per skill. Ops
    with no targeted skill (bare `list`, `find`, interactive `add` w/o
    `--skill`) come in with `skill_*` fields null — that's fine, the row
    still records the lifecycle and contributes to per-user / per-command
    counts.
    """
    try:
        event = skill_event_service.record(
            request=request,
            user=user,
            x_codemie_cli=x_codemie_cli,
            x_codemie_client=x_codemie_client,
        )
        return SkillEventResponse(
            id=event.id,
            success=True,
            message=f"Skill event '{request.command}/{request.status}' recorded",
        )
    except ExtendedHTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to record skill event command=%s status=%s: %s",
            request.command,
            request.status,
            exc,
            exc_info=True,
        )
        raise ExtendedHTTPException(
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to record skill event",
            details=f"command={request.command} status={request.status} error={exc}",
            help="Please retry; if the issue persists, contact support.",
        ) from exc
