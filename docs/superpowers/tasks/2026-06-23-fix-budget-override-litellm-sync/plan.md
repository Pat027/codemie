# EPMCDME-12960: Fix budget override clearing — LiteLLM enforcement not updated

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a project member budget override is cleared, immediately sync LiteLLM with the correct equal-split value from the existing shared child budget instead of the stale override value.

**Architecture:** Single-method fix in `ProjectBudgetService.clear_member_override`. Before calling `_ensure_shared_child_budget` and `provider.sync_member_allocation`, load the existing shared child budget from DB to obtain the correct `max_budget` / `soft_budget` already set by the last rebalance. Pass that value explicitly as `effective_max_budget` to the provider sync. Comment out the trailing `rebalance_project_budget` call (rebalancing is a manual admin operation).

**Tech Stack:** Python, SQLAlchemy async, pytest, `unittest.mock` (`AsyncMock`, `patch`)

---

### Task 1: Write failing tests for `clear_member_override` happy-path LiteLLM sync

**Files:**
- Test: `tests/codemie/service/budget/test_project_budget_service_lifecycle.py`

- [ ] **Step 1: Add the two new test functions at the end of the file**

Open `tests/codemie/service/budget/test_project_budget_service_lifecycle.py` and append:

```python
@pytest.mark.asyncio
async def test_clear_member_override_syncs_litellm_with_shared_child_value():
    """When shared child budget exists, provider receives its max_budget — not the stale override value."""
    service = ProjectBudgetService()
    session = AsyncMock()

    # Allocation returned by repo after mode is switched to equal.
    # allocated_max_budget is intentionally stale (50.0 — the old override value).
    allocation = SimpleNamespace(
        id="alloc-1",
        user_id="user-a",
        project_budget_id="proj-budget-1",
        project_name="proj-a",
        budget_category="cli",
        override_budget_id="proj-budget-1:user:user-a",
        shared_budget_id="proj-budget-1:shared",
        effective_budget_id="proj-budget-1:shared",
        allocation_mode=AllocationMode.EQUAL.value,
        allocated_max_budget=50.0,   # stale override value
        allocated_soft_budget=40.0,  # stale override value
        override_reason=None,
    )

    budget = SimpleNamespace(
        budget_id="proj-budget-1",
        budget_type="project",
        budget_category="cli",
        budget_duration="30d",
        budget_reset_at=None,
        max_budget=100.0,
        soft_budget=80.0,
    )
    assignment = SimpleNamespace(project_name="proj-a", budget_category="cli")

    # Shared child budget holds the correct equal-split value from last rebalance.
    existing_shared_child = SimpleNamespace(
        budget_id="proj-budget-1:shared",
        max_budget=25.0,   # correct equal-split
        soft_budget=20.0,
    )

    shared_budget_result = SimpleNamespace(budget_id="proj-budget-1:shared")

    member_state = BudgetProviderMemberState(
        provider="litellm",
        provider_member_ref="ref-1",
        provider_budget_id="provider-bud-1",
        sync_status=SyncStatus.OK,
    )

    mock_provider = SimpleNamespace(sync_member_allocation=AsyncMock(return_value=member_state))

    with (
        patch(
            "codemie.service.budget.project_budget_service.project_member_budget_assignment_repository.clear_member_override",
            new=AsyncMock(return_value=allocation),
        ),
        patch.object(
            service,
            "get_project_budget",
            new=AsyncMock(return_value=(budget, assignment, [])),
        ),
        patch(
            "codemie.service.budget.project_budget_service.budget_repository.get_by_id",
            new=AsyncMock(return_value=existing_shared_child),
        ),
        patch.object(
            service,
            "_ensure_shared_child_budget",
            new=AsyncMock(return_value=shared_budget_result),
        ) as mock_ensure_shared,
        patch(
            "codemie.service.budget.project_budget_service.budget_repository.detach_budget",
            new=AsyncMock(),
        ),
        patch(
            "codemie.service.budget.project_budget_service.project_member_budget_assignment_repository.update_member_budget_routing",
            new=AsyncMock(return_value=allocation),
        ),
        patch(
            "codemie.service.budget.project_budget_service.get_active_provider",
            return_value=mock_provider,
        ),
        patch.object(service, "_persist_child_budget_provider_state", new=AsyncMock()),
        patch(
            "codemie.service.budget.project_budget_service.project_member_budget_assignment_repository.update_provider_metadata",
            new=AsyncMock(),
        ),
        patch.object(service, "rebalance_project_budget", new=AsyncMock()) as mock_rebalance,
    ):
        await service.clear_member_override(
            session=session,
            budget_id="proj-budget-1",
            user_id="user-a",
            actor_id="actor-1",
        )

    # Provider must receive the shared child value (25.0), NOT the stale override (50.0).
    mock_provider.sync_member_allocation.assert_awaited_once()
    call_kwargs = mock_provider.sync_member_allocation.await_args.kwargs
    assert call_kwargs["effective_max_budget"] == 25.0, (
        f"expected effective_max_budget=25.0 (shared child value), got {call_kwargs['effective_max_budget']}"
    )

    # _ensure_shared_child_budget must also use the correct value.
    mock_ensure_shared.assert_awaited_once()
    ensure_kwargs = mock_ensure_shared.await_args.kwargs
    assert ensure_kwargs["per_member_max_budget"] == 25.0
    assert ensure_kwargs["per_member_soft_budget"] == 20.0

    # rebalance must NOT be called (manual operation).
    mock_rebalance.assert_not_awaited()


@pytest.mark.asyncio
async def test_clear_member_override_falls_back_to_allocation_value_when_no_shared_child():
    """When no shared child budget exists yet, provider receives allocation.allocated_max_budget as fallback."""
    service = ProjectBudgetService()
    session = AsyncMock()

    allocation = SimpleNamespace(
        id="alloc-1",
        user_id="user-a",
        project_budget_id="proj-budget-1",
        project_name="proj-a",
        budget_category="cli",
        override_budget_id="proj-budget-1:user:user-a",
        shared_budget_id=None,
        effective_budget_id=None,
        allocation_mode=AllocationMode.EQUAL.value,
        allocated_max_budget=50.0,
        allocated_soft_budget=40.0,
        override_reason=None,
    )

    budget = SimpleNamespace(
        budget_id="proj-budget-1",
        budget_type="project",
        budget_category="cli",
        budget_duration="30d",
        budget_reset_at=None,
        max_budget=100.0,
        soft_budget=80.0,
    )
    assignment = SimpleNamespace(project_name="proj-a", budget_category="cli")
    shared_budget_result = SimpleNamespace(budget_id="proj-budget-1:shared")

    member_state = BudgetProviderMemberState(
        provider="litellm",
        provider_member_ref="ref-1",
        provider_budget_id="provider-bud-1",
        sync_status=SyncStatus.OK,
    )
    mock_provider = SimpleNamespace(sync_member_allocation=AsyncMock(return_value=member_state))

    with (
        patch(
            "codemie.service.budget.project_budget_service.project_member_budget_assignment_repository.clear_member_override",
            new=AsyncMock(return_value=allocation),
        ),
        patch.object(
            service,
            "get_project_budget",
            new=AsyncMock(return_value=(budget, assignment, [])),
        ),
        patch(
            "codemie.service.budget.project_budget_service.budget_repository.get_by_id",
            new=AsyncMock(return_value=None),  # no shared child exists
        ),
        patch.object(
            service,
            "_ensure_shared_child_budget",
            new=AsyncMock(return_value=shared_budget_result),
        ) as mock_ensure_shared,
        patch(
            "codemie.service.budget.project_budget_service.budget_repository.detach_budget",
            new=AsyncMock(),
        ),
        patch(
            "codemie.service.budget.project_budget_service.project_member_budget_assignment_repository.update_member_budget_routing",
            new=AsyncMock(return_value=allocation),
        ),
        patch(
            "codemie.service.budget.project_budget_service.get_active_provider",
            return_value=mock_provider,
        ),
        patch.object(service, "_persist_child_budget_provider_state", new=AsyncMock()),
        patch(
            "codemie.service.budget.project_budget_service.project_member_budget_assignment_repository.update_provider_metadata",
            new=AsyncMock(),
        ),
        patch.object(service, "rebalance_project_budget", new=AsyncMock()),
    ):
        await service.clear_member_override(
            session=session,
            budget_id="proj-budget-1",
            user_id="user-a",
            actor_id="actor-1",
        )

    # Fallback: must use allocation.allocated_max_budget when no shared child.
    call_kwargs = mock_provider.sync_member_allocation.await_args.kwargs
    assert call_kwargs["effective_max_budget"] == 50.0  # fallback to stale allocation value

    ensure_kwargs = mock_ensure_shared.await_args.kwargs
    assert ensure_kwargs["per_member_max_budget"] == 50.0
```

- [ ] **Step 2: Run the new tests to confirm they FAIL (RED)**

```bash
cd /Users/Andriy_Lukashchuk/Dev/code-assistant
poetry run pytest tests/codemie/service/budget/test_project_budget_service_lifecycle.py \
  -k "test_clear_member_override_syncs_litellm or test_clear_member_override_falls_back" \
  -v
```

Expected: both tests FAIL. The first fails because `effective_max_budget` is `None` (not passed currently), so the assertion `call_kwargs["effective_max_budget"] == 25.0` raises `KeyError` or `AssertionError`.

---

### Task 2: Implement the fix in `clear_member_override`

**Files:**
- Modify: `src/codemie/service/budget/project_budget_service.py:1265-1305`

- [ ] **Step 3: Apply the fix**

Locate `clear_member_override` in `project_budget_service.py` (starts at line 1247).

Replace the block from the `get_project_budget` call through the end of the method (lines 1265–1306) with:

```python
        budget, assignment, _allocations = await self.get_project_budget(session, budget_id)
        # Read the correct equal-split value from the existing shared child budget.
        # This is the authoritative value set by the last manual rebalance.
        # Falls back to the stale allocation value when the shared child does not exist yet.
        _shared_child_id = build_shared_project_budget_id(budget.budget_id)
        _existing_shared = await budget_repository.get_by_id(session, _shared_child_id)
        correct_max = _existing_shared.max_budget if _existing_shared else allocation.allocated_max_budget
        correct_soft = _existing_shared.soft_budget if _existing_shared else allocation.allocated_soft_budget
        shared_budget = await self._ensure_shared_child_budget(
            session,
            main_budget=budget,
            project_name=assignment.project_name if assignment else "",
            actor_id=actor_id,
            per_member_soft_budget=correct_soft,
            per_member_max_budget=correct_max,
        )
        if allocation.override_budget_id:
            await budget_repository.detach_budget(session, allocation.override_budget_id)
        allocation = await project_member_budget_assignment_repository.update_member_budget_routing(
            session,
            allocation_id=allocation.id,
            shared_budget_id=shared_budget.budget_id,
            override_budget_id=allocation.override_budget_id,
            effective_budget_id=shared_budget.budget_id,
            allocation_mode=AllocationMode.EQUAL.value,
            override_reason=None,
        )
        provider = get_active_provider()
        member_state = await provider.sync_member_allocation(
            allocation=allocation,
            budget=budget,
            effective_max_budget=correct_max,
        )
        await self._persist_child_budget_provider_state(
            session,
            budget_id=self._effective_member_budget_id(budget.budget_id, allocation),
            member_state=member_state,
        )
        await project_member_budget_assignment_repository.update_provider_metadata(
            session,
            allocation_id=allocation.id,
            provider_metadata=self._build_provider_metadata(
                provider=member_state.provider,
                provider_member_ref=member_state.provider_member_ref,
                provider_budget_id=member_state.provider_budget_id,
                sync_status=member_state.sync_status,
                raw=member_state.metadata,
            ),
            sync_status=member_state.sync_status,
            budget_reset_at=member_state.budget_reset_at,
        )
        # await self.rebalance_project_budget(session, budget_id, actor_id)
        # Commented out: rebalancing is a manual admin operation.
        # Note: allocation.allocated_max_budget remains stale until rebalance runs.
        return allocation
```

- [ ] **Step 4: Run the new tests to confirm they PASS (GREEN)**

```bash
poetry run pytest tests/codemie/service/budget/test_project_budget_service_lifecycle.py \
  -k "test_clear_member_override_syncs_litellm or test_clear_member_override_falls_back" \
  -v
```

Expected: both tests PASS.

- [ ] **Step 5: Run the full lifecycle test file to confirm no regressions**

```bash
poetry run pytest tests/codemie/service/budget/test_project_budget_service_lifecycle.py -v
```

Expected: all tests PASS, including the pre-existing `test_clear_member_override_raises_404_when_member_missing`.

---

### Task 3: Validate and commit

**Files:** all changed files

- [ ] **Step 6: Run the broader budget test suite**

```bash
poetry run pytest tests/codemie/service/budget/ tests/codemie/repository/ -v --tb=short
```

Expected: all tests PASS.

- [ ] **Step 7: Run linting**

```bash
poetry run ruff check src/codemie/service/budget/project_budget_service.py \
  tests/codemie/service/budget/test_project_budget_service_lifecycle.py
```

Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add \
  src/codemie/service/budget/project_budget_service.py \
  tests/codemie/service/budget/test_project_budget_service_lifecycle.py \
  docs/superpowers/tasks/2026-06-23-fix-budget-override-litellm-sync/spec.md \
  docs/superpowers/tasks/2026-06-23-fix-budget-override-litellm-sync/plan.md
git commit -m "EPMCDME-12960: Fix budget override clearing not updating LiteLLM enforcement value"
```

Test-first: yes — Task 1 writes two failing tests before Task 2 touches implementation.
