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

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codemie.rest_api.security.user import User


@pytest.mark.asyncio
async def test_budget_usage_falls_back_to_username_when_email_missing():
    """Personal budget rows should still have a stable label when email is blank."""
    from codemie.rest_api.routers.analytics import get_user_budget_usage
    from codemie.service.analytics.handlers.budget_usage_service import _get_key_spending_columns

    mock_user = User(
        id="test-user-id",
        username="maksim_yuzva@epam.com",
        email="",
        project_names=[],
        admin_project_names=[],
    )

    # subject_label = email or username or id; email is blank so username is used
    label = mock_user.username
    mock_rows = [
        {
            "project_name": label,
            "current_spending": 15.5,
            "budget_reset_at": "2026-04-01T00:00:00Z",
            "time_until_reset": None,
            "budget_limit": 100.0,
            "total": 15.5,
        },
        {
            "project_name": f"{label} (premium)",
            "current_spending": 1.25,
            "budget_reset_at": "2026-04-02T00:00:00Z",
            "time_until_reset": None,
            "budget_limit": 5.0,
            "total": 25.0,
        },
        {
            "project_name": f"{label} (cli)",
            "current_spending": 3.75,
            "budget_reset_at": "2026-04-03T00:00:00Z",
            "time_until_reset": None,
            "budget_limit": 20.0,
            "total": 18.75,
        },
    ]

    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("codemie.clients.postgres.get_async_session", return_value=mock_ctx):
        with patch(
            "codemie.service.analytics.handlers.budget_usage_service.BudgetUsageService.get_budget_usage",
            new_callable=AsyncMock,
            return_value=(_get_key_spending_columns(), mock_rows),
        ):
            response = await get_user_budget_usage(user=mock_user, user_id=None)

    rows = response["data"]["rows"]
    assert rows[0]["project_name"] == mock_user.username
    assert rows[1]["project_name"] == f"{mock_user.username} (premium)"
    assert rows[2]["project_name"] == f"{mock_user.username} (cli)"
