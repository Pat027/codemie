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

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from codemie.repository.project_spend_tracking_repository import ProjectSpendTrackingRepository


@pytest.mark.asyncio
async def test_get_latest_key_spending_for_project_returns_first_matching_row():
    repository = ProjectSpendTrackingRepository()
    row = SimpleNamespace(project_name="proj-a", cumulative_spend=12.5)
    execute_result = MagicMock()
    execute_result.scalars.return_value.first.return_value = row
    session = AsyncMock()
    session.execute.return_value = execute_result

    result = await repository.get_latest_key_spending_for_project(session=session, project_name="proj-a")

    assert result is row
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_latest_key_spending_for_project_returns_none_when_no_rows():
    repository = ProjectSpendTrackingRepository()
    execute_result = MagicMock()
    execute_result.scalars.return_value.first.return_value = None
    session = AsyncMock()
    session.execute.return_value = execute_result

    result = await repository.get_latest_key_spending_for_project(session=session, project_name="proj-a")

    assert result is None


@pytest.mark.asyncio
async def test_get_latest_budget_rows_for_project_returns_all_budget_rows():
    repository = ProjectSpendTrackingRepository()
    rows = [SimpleNamespace(budget_id="budget-1"), SimpleNamespace(budget_id="budget-2")]
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = rows
    session = AsyncMock()
    session.execute.return_value = execute_result

    result = await repository.get_latest_budget_rows_for_project(
        session=session,
        project_name="proj-a",
        rows_limit=10,
    )

    assert result == rows
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_latest_spending_by_project_returns_empty_for_empty_input():
    repository = ProjectSpendTrackingRepository()
    session = AsyncMock()

    result = await repository.get_latest_spending_by_project(session=session, project_names=[])

    assert result == []
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_latest_spending_by_project_returns_rows_for_requested_projects():
    repository = ProjectSpendTrackingRepository()
    rows = [SimpleNamespace(project_name="proj-a"), SimpleNamespace(project_name="proj-b")]
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = rows
    session = AsyncMock()
    session.execute.return_value = execute_result

    result = await repository.get_latest_spending_by_project(
        session=session,
        project_names=["proj-a", "proj-b"],
        spend_subject_type="budget",
    )

    assert result == rows
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_latest_before_by_project_budget_ids_returns_empty_for_empty_input():
    repository = ProjectSpendTrackingRepository()
    session = AsyncMock()

    result = await repository.get_latest_before_by_project_budget_ids(session, [], datetime.now())

    assert result == {}
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_latest_before_by_project_budget_ids_groups_rows_by_pair():
    repository = ProjectSpendTrackingRepository()
    session = AsyncMock()
    row = SimpleNamespace(project_name="proj-a", budget_id="budget-1")
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [row]
    session.execute.return_value = execute_result

    result = await repository.get_latest_before_by_project_budget_ids(
        session,
        [("proj-a", "budget-1")],
        datetime.now(),
        spend_subject_type="project_budget",
    )

    assert result == {("proj-a", "budget-1"): row}


@pytest.mark.asyncio
async def test_get_latest_before_by_budget_category_ids_returns_empty_for_empty_input():
    repository = ProjectSpendTrackingRepository()
    session = AsyncMock()

    result = await repository.get_latest_before_by_budget_category_ids(session, [], datetime.now())

    assert result == {}
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_latest_before_by_budget_category_ids_groups_rows_by_triple():
    repository = ProjectSpendTrackingRepository()
    session = AsyncMock()
    row = SimpleNamespace(project_name="proj-a", budget_id="budget-1", budget_category="cli")
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [row]
    session.execute.return_value = execute_result

    result = await repository.get_latest_before_by_budget_category_ids(
        session,
        [("proj-a", "budget-1", "cli")],
        datetime.now(),
    )

    assert result == {("proj-a", "budget-1", "cli"): row}


@pytest.mark.asyncio
async def test_get_latest_before_by_member_budget_ids_returns_empty_for_empty_input():
    repository = ProjectSpendTrackingRepository()
    session = AsyncMock()

    result = await repository.get_latest_before_by_member_budget_ids(session, [], datetime.now())

    assert result == {}
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_latest_before_by_member_budget_ids_groups_rows_by_member_triple():
    repository = ProjectSpendTrackingRepository()
    session = AsyncMock()
    row = SimpleNamespace(project_name="proj-a", budget_id="budget-1", user_id="user-1")
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [row]
    session.execute.return_value = execute_result

    result = await repository.get_latest_before_by_member_budget_ids(
        session,
        [("proj-a", "budget-1", "user-1")],
        datetime.now(),
    )

    assert result == {("proj-a", "budget-1", "user-1"): row}


@pytest.mark.asyncio
async def test_insert_project_budget_entries_returns_early_for_empty_rows():
    repository = ProjectSpendTrackingRepository()
    session = AsyncMock()

    await repository.insert_project_budget_entries(session, [])

    session.execute.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_insert_project_budget_entries_executes_upsert_and_commit():
    repository = ProjectSpendTrackingRepository()
    session = AsyncMock()
    row = SimpleNamespace(
        id="row-1",
        project_name="proj-a",
        cost_center_id=None,
        cost_center_name=None,
        spend_date=datetime.now(),
        daily_spend=1.0,
        cumulative_spend=2.0,
        budget_period_spend=3.0,
        budget_id="budget-1",
        budget_category="cli",
        user_id=None,
        provider_subject_id="provider-1",
    )

    await repository.insert_project_budget_entries(session, [row])

    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_insert_member_budget_entries_executes_upsert_and_commit():
    repository = ProjectSpendTrackingRepository()
    session = AsyncMock()
    row = SimpleNamespace(
        id="row-1",
        project_name="proj-a",
        cost_center_id=None,
        cost_center_name=None,
        spend_date=datetime.now(),
        daily_spend=1.0,
        cumulative_spend=2.0,
        budget_period_spend=3.0,
        budget_id="budget-1",
        budget_category="cli",
        user_id="user-1",
        provider_subject_id="provider-1",
    )

    await repository.insert_member_budget_entries(session, [row])

    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()
