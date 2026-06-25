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

"""Schema validation tests for project budget router models."""

import pytest
from pydantic import ValidationError

from codemie.rest_api.routers.project_budget_router import (
    CategoryBudgetSpec,
    CategoryBudgetSpecUpdate,
)


class TestCategoryBudgetSpecValidation:
    """Test CategoryBudgetSpec.pct field validation."""

    def test_accepts_zero_percent(self):
        """CategoryBudgetSpec should accept pct=0 for zero-allocation categories."""
        spec = CategoryBudgetSpec(pct=0.0, soft_budget=None)
        assert spec.pct == 0.0

    def test_accepts_positive_percent(self):
        """CategoryBudgetSpec should accept positive pct values."""
        spec = CategoryBudgetSpec(pct=50.0, soft_budget=None)
        assert spec.pct == 50.0

    def test_rejects_negative_percent(self):
        """CategoryBudgetSpec should reject negative pct values."""
        with pytest.raises(ValidationError) as exc_info:
            CategoryBudgetSpec(pct=-1.0, soft_budget=None)
        errors = exc_info.value.errors()
        assert any("greater than or equal to 0" in str(e) for e in errors)

    def test_rejects_percent_over_100(self):
        """CategoryBudgetSpec should reject pct > 100."""
        with pytest.raises(ValidationError) as exc_info:
            CategoryBudgetSpec(pct=101.0, soft_budget=None)
        errors = exc_info.value.errors()
        assert any("less than or equal to 100" in str(e) for e in errors)


class TestCategoryBudgetSpecUpdateValidation:
    """Test CategoryBudgetSpecUpdate.pct already accepts zero (reference behavior)."""

    def test_update_accepts_zero_percent(self):
        """CategoryBudgetSpecUpdate already accepts pct=0 (no change needed)."""
        spec = CategoryBudgetSpecUpdate(pct=0.0, soft_budget=None)
        assert spec.pct == 0.0
