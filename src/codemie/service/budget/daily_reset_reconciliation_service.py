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

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from codemie.clients.postgres import get_async_session
from codemie.configs import logger
from codemie.repository.budget_repository import budget_repository
from codemie.repository.project_budget_repository import (
    ParentMemberResetPairRow,
    project_member_budget_assignment_repository,
)
from codemie.service.budget.provider import BudgetResetReconciliationTarget
from codemie.service.budget.provider_registry import get_active_provider


def _metadata_value(metadata: dict[str, Any], key: str) -> Any:
    if key in metadata:
        return metadata[key]
    raw = metadata.get("raw")
    if isinstance(raw, dict):
        return raw.get(key)
    return None


@dataclass
class DailyBudgetResetReconciliationSummary:
    updated: int = 0
    failed: int = 0
    mismatch_warnings: int = 0


class DailyBudgetResetReconciliationService:
    @staticmethod
    def _parse_reset_at(value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @staticmethod
    def _build_budget_target(budget: Any) -> BudgetResetReconciliationTarget:
        metadata = budget.provider_metadata or {}
        return BudgetResetReconciliationTarget(
            entity_type="budget",
            budget_id=budget.budget_id,
            provider_budget_ref=_metadata_value(metadata, "provider_budget_ref"),
            budget_reset_at=budget.budget_reset_at,
            metadata=metadata,
        )

    @staticmethod
    def _build_member_target(allocation: Any) -> BudgetResetReconciliationTarget:
        metadata = allocation.provider_metadata or {}
        return BudgetResetReconciliationTarget(
            entity_type="member_allocation",
            budget_id=allocation.id,
            provider_budget_ref=_metadata_value(metadata, "provider_budget_id"),
            provider_member_ref=_metadata_value(metadata, "provider_member_ref"),
            project_budget_id=allocation.project_budget_id,
            budget_reset_at=allocation.budget_reset_at,
            metadata=metadata,
        )

    def _log_parent_member_mismatches(self, pairs: list[ParentMemberResetPairRow]) -> int:
        warnings = 0
        threshold_seconds = 5 * 60

        for pair in pairs:
            parent_dt = self._parse_reset_at(pair.parent_budget_reset_at)
            member_dt = self._parse_reset_at(pair.member_budget_reset_at)
            if parent_dt is None or member_dt is None:
                continue

            delta_seconds = abs((parent_dt - member_dt).total_seconds())
            if delta_seconds > threshold_seconds:
                warnings += 1
                logger.warning(
                    "budget_reset_reconciliation_mismatch_detected: "
                    f"budget_id={pair.budget_id!r}, allocation_id={pair.allocation_id!r}, "
                    f"parent_budget_reset_at={pair.parent_budget_reset_at!r}, "
                    f"member_budget_reset_at={pair.member_budget_reset_at!r}, "
                    f"delta_seconds={delta_seconds:.0f}"
                )

        return warnings

    async def run(self) -> DailyBudgetResetReconciliationSummary:
        summary = DailyBudgetResetReconciliationSummary()
        now = datetime.now(UTC)

        async with get_async_session() as session:
            overdue_budgets = await budget_repository.list_overdue_reset_budgets(session, now)
            overdue_members = await project_member_budget_assignment_repository.list_overdue_reset_member_allocations(
                session,
                now,
            )

            if not overdue_budgets and not overdue_members:
                logger.info("Daily budget reset reconciliation skipped: no overdue entities")
                return summary

            mismatch_pairs = await project_member_budget_assignment_repository.list_parent_member_reset_pairs(
                session,
                [budget.budget_id for budget in overdue_budgets],
            )
            summary.mismatch_warnings = self._log_parent_member_mismatches(mismatch_pairs)

            targets = [self._build_budget_target(budget) for budget in overdue_budgets]
            targets.extend(self._build_member_target(allocation) for allocation in overdue_members)

            result = await get_active_provider().reconcile_budget_reset_timestamps(targets=targets)

            for item in result.items:
                if item.error:
                    summary.failed += 1
                    logger.error(
                        "budget_reset_reconciliation_item_failed: "
                        f"entity_type={item.entity_type!r}, budget_id={item.budget_id!r}, "
                        f"provider_budget_ref={item.provider_budget_ref!r}, "
                        f"provider_member_ref={item.provider_member_ref!r}, error={item.error}"
                    )
                    continue

                if not item.refreshed_budget_reset_at:
                    summary.failed += 1
                    logger.error(
                        "budget_reset_reconciliation_item_failed: "
                        f"entity_type={item.entity_type!r}, budget_id={item.budget_id!r}, "
                        f"provider_budget_ref={item.provider_budget_ref!r}, "
                        f"provider_member_ref={item.provider_member_ref!r}, "
                        "error='provider returned empty budget_reset_at'"
                    )
                    continue

                if item.entity_type == "budget":
                    updated = await budget_repository.update_budget_reset_at(
                        session,
                        budget_id=item.budget_id,
                        budget_reset_at=item.refreshed_budget_reset_at,
                    )
                else:
                    updated = await project_member_budget_assignment_repository.update_budget_reset_at(
                        session,
                        allocation_id=item.budget_id,
                        budget_reset_at=item.refreshed_budget_reset_at,
                    )

                if updated is None:
                    summary.failed += 1
                    logger.error(
                        "budget_reset_reconciliation_item_failed: "
                        f"entity_type={item.entity_type!r}, budget_id={item.budget_id!r}, "
                        f"provider_budget_ref={item.provider_budget_ref!r}, "
                        f"provider_member_ref={item.provider_member_ref!r}, "
                        "error='local entity missing during persistence'"
                    )
                    continue

                summary.updated += 1

            await session.commit()

        logger.info(
            "daily_budget_reset_reconciliation_completed: "
            f"updated={summary.updated}, failed={summary.failed}, "
            f"mismatch_warnings={summary.mismatch_warnings}"
        )
        return summary


daily_budget_reset_reconciliation_service = DailyBudgetResetReconciliationService()
