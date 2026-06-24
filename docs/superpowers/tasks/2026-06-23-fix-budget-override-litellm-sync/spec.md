# EPMCDME-12960: Fix budget override clearing — LiteLLM enforcement not updated

## Problem

When an admin clears a project member's budget override, LiteLLM continues to enforce
the stale override limit until the affected user makes their next LLM request (lazy
runtime re-sync). This only manifests when `enforce_member_spend_limits` is enabled.

**Root cause — two compounding bugs in `project_budget_service.clear_member_override`:**

1. `_ensure_shared_child_budget` is called with `allocation.allocated_max_budget` (the
   stale override value, e.g. 50) instead of the correct equal-split value already stored
   on the shared child budget in `codemie.budgets`.

2. `provider.sync_member_allocation` is called immediately after with the same stale
   value — no `effective_max_budget` override is passed, so the adapter falls back to
   `allocation.allocated_max_budget = 50`. LiteLLM is synced with the wrong limit.

The `rebalance_project_budget` call that follows does correct the Codemie DB records but
does not re-sync LiteLLM for equal-mode members (Gap B — tracked separately).

**Resulting state after a cleared override:**

| Store                                                        | Value | Correct |
|--------------------------------------------------------------|-------|---------|
| `project_member_budget_assignments.allocated_max_budget`     | 25    | ✓       |
| `codemie.budgets` shared child `max_budget`                  | 25    | ✓       |
| LiteLLM internal `max_budget`                                | 50    | ✗       |

## Scope

Fix is confined to `project_budget_service.clear_member_override`. No other methods
are modified in this ticket.

Out of scope:
- Gap B: `_resync_member_allocation` not syncing equal-mode members during rebalance
  (separate ticket).
- `repo.clear_member_override` not resetting `allocated_max_budget` — mitigated by the
  service fix; deferred.

## Solution

### Source of truth for the correct equal-split value

Read from the existing shared child budget row in `codemie.budgets` (identified by
`build_shared_project_budget_id(budget.budget_id)`). This row holds the value set by
the last manual rebalance and is authoritative for all equal-mode members.

**Edge case:** If the shared child does not yet exist (unusual — implies no prior
rebalance with equal-mode members), fall back to `allocation.allocated_max_budget`.
A subsequent manual rebalance will correct it.

### New execution order in `clear_member_override`

```
1. repo.clear_member_override()
      → allocation_mode = "equal", override_reason = None
      → allocated_max_budget remains stale (unchanged by repo)

2. get_project_budget()
      → reload budget, assignment

3. Load existing shared child budget from DB
      correct_max  = shared_child.max_budget  (or fallback to allocation value)
      correct_soft = shared_child.soft_budget (or fallback)

4. _ensure_shared_child_budget(
       per_member_max_budget  = correct_max,   ← was: stale allocation value
       per_member_soft_budget = correct_soft,
   )
      → shared child in codemie.budgets = correct_max ✓

5. detach_budget(allocation.override_budget_id)
      → Codemie soft-delete only (detached_at set)

6. update_member_budget_routing(
       effective_budget_id = shared_budget.budget_id,
       allocation_mode     = EQUAL,
       override_reason     = None,
       ...
   )

7. provider.sync_member_allocation(
       allocation          = allocation,
       budget              = budget,
       effective_max_budget = correct_max,    ← NEW: explicit correct value
   )
      → LiteLLM shared budget updated to correct_max ✓
      → Customer pointer switched from override-xxx to shared-yyy ✓

8. Persist child budget provider state + update provider metadata

# await self.rebalance_project_budget(...)
#   Commented out — rebalancing is a manual admin operation.
#   allocated_max_budget on the assignment row remains stale until rebalance runs.
```

### Post-fix state

| Store                                                        | Value | Correct |
|--------------------------------------------------------------|-------|---------|
| `project_member_budget_assignments.allocated_max_budget`     | 50*   | —       |
| `codemie.budgets` shared child `max_budget`                  | 25    | ✓       |
| LiteLLM internal `max_budget`                                | 25    | ✓       |

*Stale until a manual rebalance is triggered. Not observable by LiteLLM enforcement.

## Affected files

| File | Change |
|------|--------|
| `src/codemie/service/budget/project_budget_service.py` | `clear_member_override`: read shared child, pass `effective_max_budget`, comment out rebalance |
| `tests/codemie/service/budget/test_project_budget_service_lifecycle.py` | Add happy-path tests per acceptance criteria |

## Acceptance criteria

- Clearing a member budget override immediately updates LiteLLM with the correct
  equal-split value when `enforce_member_spend_limits` is enabled.
- `codemie.budgets` shared child `max_budget` equals the pre-existing equal-split value
  immediately after the override is cleared.
- LiteLLM does not continue enforcing the stale override value after
  `DELETE /v1/admin/project-budget/{budget_id}/members/{user_id}/override`.
- No user LLM request is required to trigger re-sync.
- Existing behaviour for fixed-mode overrides is unchanged.
- Regression tests cover: set override → clear override (enforce enabled) → verify
  LiteLLM receives correct equal-split value.
