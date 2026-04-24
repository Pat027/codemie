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

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from codemie.enterprise.litellm import budget_helpers


def test_create_budget_in_litellm_returns_none_when_service_unavailable():
    with patch("codemie.enterprise.litellm.budget_helpers.get_litellm_service_or_none", return_value=None):
        result = budget_helpers.create_budget_in_litellm(
            budget_id="budget-1",
            max_budget=25.0,
            soft_budget=20.0,
            budget_duration="30d",
        )

    assert result is None


def test_create_budget_in_litellm_delegates_to_provider():
    service = MagicMock()
    service.create_managed_budget.return_value = SimpleNamespace(budget_id="budget-1")

    with patch("codemie.enterprise.litellm.budget_helpers.get_litellm_service_or_none", return_value=service):
        result = budget_helpers.create_budget_in_litellm(
            budget_id="budget-1",
            max_budget=25.0,
            soft_budget=20.0,
            budget_duration="30d",
        )

    assert result.budget_id == "budget-1"
    service.create_managed_budget.assert_called_once_with(
        budget_id="budget-1",
        max_budget=25.0,
        soft_budget=20.0,
        budget_duration="30d",
    )


def test_update_budget_in_litellm_returns_none_when_service_unavailable():
    with patch("codemie.enterprise.litellm.budget_helpers.get_litellm_service_or_none", return_value=None):
        result = budget_helpers.update_budget_in_litellm(
            budget_id="budget-1",
            max_budget=25.0,
            soft_budget=20.0,
            budget_duration="30d",
        )

    assert result is None


def test_update_budget_in_litellm_logs_error_when_provider_returns_none():
    service = MagicMock()
    service.update_managed_budget.return_value = None

    with (
        patch("codemie.enterprise.litellm.budget_helpers.get_litellm_service_or_none", return_value=service),
        patch("codemie.enterprise.litellm.budget_helpers.logger") as mock_logger,
    ):
        result = budget_helpers.update_budget_in_litellm(
            budget_id="budget-1",
            max_budget=25.0,
            soft_budget=20.0,
            budget_duration="30d",
        )

    assert result is None
    service.update_managed_budget.assert_called_once_with(
        budget_id="budget-1",
        max_budget=25.0,
        soft_budget=20.0,
        budget_duration="30d",
    )
    mock_logger.error.assert_called_once()


def test_get_budget_reset_at_returns_matching_budget_reset_at():
    budget = SimpleNamespace(budget_id="budget-1", budget_reset_at="2026-04-24T00:00:00Z")
    other_budget = SimpleNamespace(budget_id="budget-2", budget_reset_at="2026-05-01T00:00:00Z")
    service = MagicMock()
    service.get_budget_info.return_value = [other_budget, budget]

    with patch("codemie.enterprise.litellm.budget_helpers.get_litellm_service_or_none", return_value=service):
        result = budget_helpers.get_budget_reset_at("budget-1")

    assert result == "2026-04-24T00:00:00Z"


def test_get_budget_reset_at_returns_none_when_service_unavailable():
    with patch("codemie.enterprise.litellm.budget_helpers.get_litellm_service_or_none", return_value=None):
        result = budget_helpers.get_budget_reset_at("budget-1")

    assert result is None


def test_get_budget_reset_at_returns_none_when_provider_has_no_budgets():
    service = MagicMock()
    service.get_budget_info.return_value = []

    with patch("codemie.enterprise.litellm.budget_helpers.get_litellm_service_or_none", return_value=service):
        result = budget_helpers.get_budget_reset_at("budget-1")

    assert result is None


def test_list_budgets_from_litellm_returns_none_when_service_unavailable():
    with patch("codemie.enterprise.litellm.budget_helpers.get_litellm_service_or_none", return_value=None):
        result = budget_helpers.list_budgets_from_litellm()

    assert result is None


def test_list_budgets_from_litellm_returns_provider_budgets():
    service = MagicMock()
    service.list_managed_budgets.return_value = [SimpleNamespace(budget_id="budget-1")]

    with patch("codemie.enterprise.litellm.budget_helpers.get_litellm_service_or_none", return_value=service):
        result = budget_helpers.list_budgets_from_litellm()

    assert [budget.budget_id for budget in result] == ["budget-1"]


def test_list_budgets_from_litellm_returns_none_when_provider_raises():
    service = MagicMock()
    service.list_managed_budgets.side_effect = RuntimeError("boom")

    with (
        patch("codemie.enterprise.litellm.budget_helpers.get_litellm_service_or_none", return_value=service),
        patch("codemie.enterprise.litellm.budget_helpers.logger") as mock_logger,
    ):
        result = budget_helpers.list_budgets_from_litellm()

    assert result is None
    mock_logger.warning.assert_called_once()


def test_reset_customer_spending_in_litellm_returns_false_when_service_unavailable():
    with patch("codemie.enterprise.litellm.budget_helpers.get_litellm_service_or_none", return_value=None):
        result = budget_helpers.reset_customer_spending_in_litellm(user_id="user-1", budget_id="budget-1")

    assert result is False


def test_reset_customer_spending_in_litellm_returns_true_when_provider_resets_customer():
    service = MagicMock()
    service.reset_customer_spending.return_value = object()

    with patch("codemie.enterprise.litellm.budget_helpers.get_litellm_service_or_none", return_value=service):
        result = budget_helpers.reset_customer_spending_in_litellm(user_id="user-1", budget_id="budget-1")

    assert result is True


def test_reset_customer_spending_in_litellm_returns_false_when_provider_raises():
    service = MagicMock()
    service.reset_customer_spending.side_effect = RuntimeError("boom")

    with (
        patch("codemie.enterprise.litellm.budget_helpers.get_litellm_service_or_none", return_value=service),
        patch("codemie.enterprise.litellm.budget_helpers.logger") as mock_logger,
    ):
        result = budget_helpers.reset_customer_spending_in_litellm(user_id="user-1", budget_id="budget-1")

    assert result is False
    mock_logger.warning.assert_called_once()


def test_update_customer_budget_in_litellm_returns_false_when_service_unavailable():
    with patch("codemie.enterprise.litellm.budget_helpers.get_litellm_service_or_none", return_value=None):
        result = budget_helpers.update_customer_budget_in_litellm(user_id="user-1", budget_id="budget-1")

    assert result is False


def test_update_customer_budget_in_litellm_returns_true_on_success():
    service = MagicMock()
    service.set_customer_budget_assignment.return_value = True

    with patch("codemie.enterprise.litellm.budget_helpers.get_litellm_service_or_none", return_value=service):
        result = budget_helpers.update_customer_budget_in_litellm(user_id="user-1", budget_id="budget-1")

    assert result is True
    service.set_customer_budget_assignment.assert_called_once_with(user_id="user-1", budget_id="budget-1")


def test_update_customer_budget_in_litellm_returns_false_when_provider_raises():
    service = MagicMock()
    service.set_customer_budget_assignment.side_effect = RuntimeError("boom")

    with (
        patch("codemie.enterprise.litellm.budget_helpers.get_litellm_service_or_none", return_value=service),
        patch("codemie.enterprise.litellm.budget_helpers.logger") as mock_logger,
    ):
        result = budget_helpers.update_customer_budget_in_litellm(user_id="user-1", budget_id="budget-1")

    assert result is False
    mock_logger.warning.assert_called_once()
