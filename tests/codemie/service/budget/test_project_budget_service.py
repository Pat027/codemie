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

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from codemie.core.exceptions import ExtendedHTTPException
from codemie.service.budget.budget_enums import SyncStatus
from codemie.service.budget.project_budget_service import ProjectBudgetService
from codemie.service.budget.provider import BudgetProviderMemberState, BudgetProviderState
from codemie.service.spend_tracking.spend_models import ProjectSpendTracking


@pytest.mark.asyncio
async def test_resync_member_allocations_updates_shared_child_budget_for_equal_members():
    service = ProjectBudgetService()
    session = AsyncMock()
    budget = SimpleNamespace(
        budget_id="proj-budget-1",
        budget_duration="30d",
        budget_reset_at="2026-04-22T10:00:00Z",
    )
    allocation = SimpleNamespace(
        id="alloc-1",
        user_id="user-1",
        allocated_max_budget=25.0,
        allocated_soft_budget=20.0,
        allocation_mode="equal",
    )
    provider = SimpleNamespace(
        sync_member_allocation=AsyncMock(
            return_value=BudgetProviderMemberState(
                provider="litellm",
                provider_member_ref="member-ref-1",
                provider_budget_id="member-budget-1",
                budget_reset_at="2026-04-22T10:00:00Z",
                sync_status=SyncStatus.OK,
                metadata={"internal_budget": True},
            )
        )
    )

    with (
        patch(
            "codemie.service.budget.project_budget_service.project_member_budget_assignment_repository.get_active_by_budget_id",
            new=AsyncMock(return_value=[allocation]),
        ),
        patch(
            "codemie.service.budget.project_budget_service.project_budget_assignment_repository.get_active_by_budget_id",
            new=AsyncMock(return_value=SimpleNamespace(project_name="proj-a")),
        ),
        patch(
            "codemie.service.budget.project_budget_service.project_member_budget_assignment_repository.update_allocation",
            new=AsyncMock(return_value=allocation),
        ),
        patch(
            "codemie.service.budget.project_budget_service.project_member_budget_assignment_repository.update_provider_metadata",
            new=AsyncMock(),
        ) as mock_update_metadata,
        patch.object(service, "_ensure_shared_child_budget", new=AsyncMock()) as mock_ensure_shared_child_budget,
    ):
        await service._resync_member_allocations(
            session=session,
            budget_id="proj-budget-1",
            budget=budget,
            eff_max=25.0,
            eff_soft=20.0,
            provider=provider,
        )

    provider.sync_member_allocation.assert_awaited_once()
    mock_update_metadata.assert_not_awaited()
    mock_ensure_shared_child_budget.assert_awaited_once_with(
        session,
        main_budget=budget,
        project_name="proj-a",
        actor_id="system",
        per_member_soft_budget=20.0,
        per_member_max_budget=25.0,
    )


@pytest.mark.asyncio
async def test_sync_created_project_budget_uses_updated_budget_for_member_sync():
    service = ProjectBudgetService()
    session = AsyncMock()
    created_budget = SimpleNamespace(budget_id="proj-budget-1")
    updated_budget = SimpleNamespace(budget_id="proj-budget-1", budget_reset_at="2026-04-22T10:00:00Z")
    provider = SimpleNamespace(
        ensure_project_budget=AsyncMock(
            return_value=BudgetProviderState(
                provider="litellm",
                provider_budget_ref="provider-budget-1",
                budget_reset_at="2026-04-22T10:00:00Z",
                sync_status=SyncStatus.OK,
                metadata={"source": "test"},
            )
        )
    )
    allocations = [SimpleNamespace(id="alloc-1")]

    with (
        patch(
            "codemie.service.budget.project_budget_service.budget_repository.update",
            new=AsyncMock(return_value=updated_budget),
        ),
        patch.object(service, "_sync_created_member_allocations", new=AsyncMock()) as mock_sync_members,
    ):
        result = await service._sync_created_project_budget(
            session=session,
            provider=provider,
            created_budget=created_budget,
            budget_id="proj-budget-1",
            project_name="proj-a",
            budget_category=SimpleNamespace(value="cli"),
            soft_budget=20.0,
            max_budget=25.0,
            budget_duration="30d",
            models=["gpt-4.1"],
            allocations=allocations,
        )

    assert result is updated_budget
    mock_sync_members.assert_awaited_once_with(
        session=session,
        provider=provider,
        budget=updated_budget,
        allocations=allocations,
    )


def test_changed_project_budget_fields_includes_only_provided_values():
    request = SimpleNamespace(
        name="Updated",
        description=None,
        soft_budget=10.0,
        max_budget=None,
        budget_duration="30d",
    )

    fields = ProjectBudgetService._changed_project_budget_fields(request)

    assert fields == {"name": "Updated", "soft_budget": 10.0, "budget_duration": "30d"}


def test_effective_project_budget_values_fall_back_to_existing_budget_values():
    budget = SimpleNamespace(soft_budget=5.0, max_budget=20.0, budget_duration="7d")
    request = SimpleNamespace(soft_budget=None, max_budget=25.0, budget_duration=None)

    eff_soft, eff_max, eff_duration, amounts_changed = ProjectBudgetService._effective_project_budget_values(
        budget, request
    )

    assert (eff_soft, eff_max, eff_duration, amounts_changed) == (5.0, 25.0, "7d", True)


def test_validate_allocation_mode_rejects_invalid_value():
    with pytest.raises(ExtendedHTTPException) as exc_info:
        ProjectBudgetService._validate_allocation_mode("weighted")

    assert "allocation_mode must be one of" in exc_info.value.message


@pytest.mark.asyncio
async def test_sync_created_member_allocations_marks_failures():
    service = ProjectBudgetService()
    session = AsyncMock()
    allocation = SimpleNamespace(id="alloc-1", user_id="user-1")
    provider = SimpleNamespace(sync_member_allocation=AsyncMock(side_effect=RuntimeError("sync failed")))

    with patch(
        "codemie.service.budget.project_budget_service.project_member_budget_assignment_repository.update_provider_metadata",
        new=AsyncMock(),
    ) as mock_update_metadata:
        await service._sync_created_member_allocations(
            session=session,
            provider=provider,
            budget=SimpleNamespace(),
            allocations=[allocation],
        )

    assert mock_update_metadata.await_args.kwargs["sync_status"] == SyncStatus.FAILED


@pytest.mark.asyncio
async def test_reset_project_budget_persists_provider_budget_id_for_each_member():
    service = ProjectBudgetService()
    session = AsyncMock()
    budget = SimpleNamespace(
        budget_id="proj-budget-1",
        budget_type="project",
        budget_category="cli",
        budget_duration="30d",
        budget_reset_at="2026-04-22T10:00:00Z",
        provider_metadata={"provider": "litellm", "provider_budget_ref": "key-alias-1", "sync_status": "ok"},
        soft_budget=20.0,
        max_budget=25.0,
    )
    assignment = SimpleNamespace(project_name="proj-a", budget_category="cli")
    allocation = SimpleNamespace(id="alloc-1", user_id="user-1", project_budget_id="proj-budget-1")
    provider = SimpleNamespace(
        reset_project_budget_spend=AsyncMock(
            return_value=SimpleNamespace(
                provider="litellm",
                provider_budget_ref="key-alias-1",
                budget_reset_at="2026-04-22T10:00:00Z",
                sync_status=SyncStatus.OK,
                metadata={},
            )
        ),
        sync_member_allocation=AsyncMock(
            return_value=BudgetProviderMemberState(
                provider="litellm",
                provider_member_ref="member-ref-1",
                provider_budget_id="member-budget-1",
                budget_reset_at="2026-04-22T10:00:00Z",
                sync_status=SyncStatus.OK,
                metadata={"internal_budget": True},
            )
        ),
    )

    with (
        patch.object(service, "get_project_budget", new=AsyncMock(return_value=(budget, assignment, [allocation]))),
        patch("codemie.service.budget.project_budget_service.get_active_provider", return_value=provider),
        patch(
            "codemie.service.budget.project_budget_service.budget_repository.update",
            new=AsyncMock(return_value=budget),
        ),
        patch(
            "codemie.service.budget.project_budget_service.project_member_budget_assignment_repository.update_provider_metadata",
            new=AsyncMock(),
        ) as mock_update_metadata,
        patch.object(service, "_persist_child_budget_provider_state", new=AsyncMock()),
        patch(
            "codemie.service.budget.project_budget_service.project_spend_tracking_repository.get_latest_before_by_project_budget_ids",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "codemie.service.budget.project_budget_service.project_spend_tracking_repository.get_latest_before_by_member_budget_ids",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "codemie.service.budget.project_budget_service.project_spend_tracking_repository.insert_project_budget_entries",
            new=AsyncMock(),
        ),
        patch(
            "codemie.service.budget.project_budget_service.project_spend_tracking_repository.insert_member_budget_entries",
            new=AsyncMock(),
        ),
    ):
        await service.reset_project_budget(session=session, budget_id="proj-budget-1", actor_id="actor-1")

    provider.reset_project_budget_spend.assert_awaited_once()
    update_call = mock_update_metadata.await_args.kwargs
    assert update_call["provider_metadata"]["raw"]["provider_budget_id"] == "member-budget-1"


def _make_tracking_row(
    project_name, budget_id, budget_period_spend, cumulative_spend, spend_subject_type="project_budget", user_id=None
):
    return ProjectSpendTracking(
        id=uuid4(),
        project_name=project_name,
        budget_id=budget_id,
        budget_category="cli",
        spend_subject_type=spend_subject_type,
        spend_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
        budget_period_spend=Decimal(str(budget_period_spend)),
        daily_spend=Decimal(str(budget_period_spend)),
        cumulative_spend=Decimal(str(cumulative_spend)),
        user_id=user_id,
    )


@pytest.mark.asyncio
async def test_reset_project_budget_writes_zero_marker_rows():
    """After reset, a zero project_budget and member_budget marker row must be inserted."""
    service = ProjectBudgetService()
    session = AsyncMock()

    budget = SimpleNamespace(
        budget_id="proj-budget-1",
        budget_type="project",
        budget_category="cli",
        budget_duration="30d",
        budget_reset_at="2026-07-01T00:00:00Z",
        provider_metadata={"provider": "litellm", "provider_budget_ref": "key-1", "sync_status": "ok"},
        soft_budget=20.0,
        max_budget=100.0,
    )
    assignment = SimpleNamespace(project_name="proj-a", budget_category="cli")
    allocation = SimpleNamespace(
        id="alloc-1",
        user_id="user-1",
        project_name="proj-a",
        project_budget_id="proj-budget-1",
        budget_category="cli",
    )

    prev_project_row = _make_tracking_row("proj-a", "proj-budget-1", "50.00", "150.00", "project_budget")
    prev_member_row = _make_tracking_row("proj-a", "proj-budget-1", "30.00", "90.00", "member_budget", user_id="user-1")

    provider = SimpleNamespace(
        reset_project_budget_spend=AsyncMock(
            return_value=SimpleNamespace(
                provider="litellm",
                provider_budget_ref="key-1",
                budget_reset_at="2026-08-01T00:00:00Z",
                sync_status=SyncStatus.OK,
                metadata={},
            )
        ),
        sync_member_allocation=AsyncMock(
            return_value=BudgetProviderMemberState(
                provider="litellm",
                provider_member_ref="member-ref-1",
                provider_budget_id="member-budget-1",
                budget_reset_at="2026-08-01T00:00:00Z",
                sync_status=SyncStatus.OK,
                metadata={},
            )
        ),
    )

    mock_insert_project = AsyncMock()
    mock_insert_member = AsyncMock()

    with (
        patch.object(service, "get_project_budget", new=AsyncMock(return_value=(budget, assignment, [allocation]))),
        patch("codemie.service.budget.project_budget_service.get_active_provider", return_value=provider),
        patch(
            "codemie.service.budget.project_budget_service.budget_repository.update", new=AsyncMock(return_value=budget)
        ),
        patch(
            "codemie.service.budget.project_budget_service.project_member_budget_assignment_repository.update_provider_metadata",
            new=AsyncMock(),
        ),
        patch.object(service, "_persist_child_budget_provider_state", new=AsyncMock()),
        patch(
            "codemie.service.budget.project_budget_service.project_spend_tracking_repository.get_latest_before_by_project_budget_ids",
            new=AsyncMock(return_value={("proj-a", "proj-budget-1"): prev_project_row}),
        ),
        patch(
            "codemie.service.budget.project_budget_service.project_spend_tracking_repository.get_latest_before_by_member_budget_ids",
            new=AsyncMock(return_value={("proj-a", "proj-budget-1", "user-1"): prev_member_row}),
        ),
        patch(
            "codemie.service.budget.project_budget_service.project_spend_tracking_repository.insert_project_budget_entries",
            new=mock_insert_project,
        ),
        patch(
            "codemie.service.budget.project_budget_service.project_spend_tracking_repository.insert_member_budget_entries",
            new=mock_insert_member,
        ),
    ):
        await service.reset_project_budget(session=session, budget_id="proj-budget-1", actor_id="actor-1")

    mock_insert_project.assert_awaited_once()
    proj_rows = mock_insert_project.await_args[0][1]
    assert len(proj_rows) == 1
    assert proj_rows[0].budget_period_spend == Decimal("0")
    assert proj_rows[0].daily_spend == Decimal("0")
    assert proj_rows[0].cumulative_spend == Decimal("150.00")
    assert proj_rows[0].project_name == "proj-a"
    assert proj_rows[0].budget_id == "proj-budget-1"

    mock_insert_member.assert_awaited_once()
    member_rows = mock_insert_member.await_args[0][1]
    assert len(member_rows) == 1
    assert member_rows[0].budget_period_spend == Decimal("0")
    assert member_rows[0].daily_spend == Decimal("0")
    assert member_rows[0].cumulative_spend == Decimal("90.00")
    assert member_rows[0].user_id == "user-1"


@pytest.mark.asyncio
async def test_reset_project_budget_no_marker_when_no_prior_row():
    """No marker rows written if there are no prior project_spend_tracking rows."""
    service = ProjectBudgetService()
    session = AsyncMock()

    budget = SimpleNamespace(
        budget_id="proj-budget-2",
        budget_type="project",
        budget_category="cli",
        budget_duration="30d",
        budget_reset_at="2026-07-01T00:00:00Z",
        provider_metadata={"provider": "litellm", "provider_budget_ref": "key-2", "sync_status": "ok"},
        soft_budget=10.0,
        max_budget=50.0,
    )
    assignment = SimpleNamespace(project_name="proj-b", budget_category="cli")
    allocation = SimpleNamespace(
        id="alloc-2",
        user_id="user-2",
        project_name="proj-b",
        project_budget_id="proj-budget-2",
        budget_category="cli",
    )

    provider = SimpleNamespace(
        reset_project_budget_spend=AsyncMock(
            return_value=SimpleNamespace(
                provider="litellm",
                provider_budget_ref="key-2",
                budget_reset_at="2026-08-01T00:00:00Z",
                sync_status=SyncStatus.OK,
                metadata={},
            )
        ),
        sync_member_allocation=AsyncMock(
            return_value=BudgetProviderMemberState(
                provider="litellm",
                provider_member_ref="m-ref",
                provider_budget_id="m-b-2",
                budget_reset_at="2026-08-01T00:00:00Z",
                sync_status=SyncStatus.OK,
                metadata={},
            )
        ),
    )

    mock_insert_project = AsyncMock()
    mock_insert_member = AsyncMock()

    with (
        patch.object(service, "get_project_budget", new=AsyncMock(return_value=(budget, assignment, [allocation]))),
        patch("codemie.service.budget.project_budget_service.get_active_provider", return_value=provider),
        patch(
            "codemie.service.budget.project_budget_service.budget_repository.update", new=AsyncMock(return_value=budget)
        ),
        patch(
            "codemie.service.budget.project_budget_service.project_member_budget_assignment_repository.update_provider_metadata",
            new=AsyncMock(),
        ),
        patch.object(service, "_persist_child_budget_provider_state", new=AsyncMock()),
        patch(
            "codemie.service.budget.project_budget_service.project_spend_tracking_repository.get_latest_before_by_project_budget_ids",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "codemie.service.budget.project_budget_service.project_spend_tracking_repository.get_latest_before_by_member_budget_ids",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "codemie.service.budget.project_budget_service.project_spend_tracking_repository.insert_project_budget_entries",
            new=mock_insert_project,
        ),
        patch(
            "codemie.service.budget.project_budget_service.project_spend_tracking_repository.insert_member_budget_entries",
            new=mock_insert_member,
        ),
    ):
        await service.reset_project_budget(session=session, budget_id="proj-budget-2", actor_id="actor-1")

    mock_insert_project.assert_awaited_once()
    assert mock_insert_project.await_args[0][1] == []
    mock_insert_member.assert_awaited_once()
    assert mock_insert_member.await_args[0][1] == []
