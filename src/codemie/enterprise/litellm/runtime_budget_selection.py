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

from enum import StrEnum

from pydantic import BaseModel


class RuntimeBudgetMode(StrEnum):
    USER_CREDENTIALS_BYPASS = "user_credentials_bypass"
    PROJECT_BUDGET_PROJECT_ONLY = "project_budget_project_only"
    PROJECT_BUDGET_WITH_MEMBER_TRACKING = "project_budget_with_member_tracking"
    GLOBAL_OR_PERSONAL_BUDGET = "global_or_personal_budget"


class RuntimeBudgetSelection(BaseModel):
    mode: RuntimeBudgetMode
    project_member_tracking_enabled: bool = False


def select_runtime_budget_mode(
    *,
    has_user_litellm_credentials: bool,
    project_name: str | None,
    project_member_tracking_enabled: bool,
    resolved_project_budget: bool,
) -> RuntimeBudgetSelection:
    if has_user_litellm_credentials:
        return RuntimeBudgetSelection(mode=RuntimeBudgetMode.USER_CREDENTIALS_BYPASS)
    if project_name and resolved_project_budget and project_member_tracking_enabled:
        return RuntimeBudgetSelection(
            mode=RuntimeBudgetMode.PROJECT_BUDGET_WITH_MEMBER_TRACKING,
            project_member_tracking_enabled=True,
        )
    if project_name and resolved_project_budget:
        return RuntimeBudgetSelection(mode=RuntimeBudgetMode.PROJECT_BUDGET_PROJECT_ONLY)
    return RuntimeBudgetSelection(mode=RuntimeBudgetMode.GLOBAL_OR_PERSONAL_BUDGET)
