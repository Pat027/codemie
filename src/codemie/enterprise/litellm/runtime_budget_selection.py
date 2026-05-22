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

from codemie.configs import logger


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
    logger.info(
        f"budget_event=runtime_mode_selection_inputs component=runtime_budget_selection "
        f"project_name={project_name!r} has_user_litellm_credentials={has_user_litellm_credentials} "
        f"resolved_project_budget={resolved_project_budget} "
        f"project_member_tracking_enabled={project_member_tracking_enabled}"
    )
    if has_user_litellm_credentials:
        selection = RuntimeBudgetSelection(mode=RuntimeBudgetMode.USER_CREDENTIALS_BYPASS)
    elif project_name and resolved_project_budget and project_member_tracking_enabled:
        selection = RuntimeBudgetSelection(
            mode=RuntimeBudgetMode.PROJECT_BUDGET_WITH_MEMBER_TRACKING,
            project_member_tracking_enabled=True,
        )
    elif project_name and resolved_project_budget:
        selection = RuntimeBudgetSelection(mode=RuntimeBudgetMode.PROJECT_BUDGET_PROJECT_ONLY)
    else:
        selection = RuntimeBudgetSelection(mode=RuntimeBudgetMode.GLOBAL_OR_PERSONAL_BUDGET)
    logger.info(
        f"budget_event=runtime_mode_selected component=runtime_budget_selection "
        f"project_name={project_name!r} mode={selection.mode!r} "
        f"project_member_tracking_enabled={selection.project_member_tracking_enabled}"
    )
    return selection
