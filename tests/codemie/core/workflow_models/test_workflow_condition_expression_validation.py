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

"""
Test suite validating that condition.expression / switch.cases[].condition strings
use Python-compatible syntax. CodeMie evaluates these expressions with Python's
eval(), so YAML-style boolean literals (true/false) must be rejected in favor of
Python-style literals (True/False) at config-validation time, per EPMCDME-13294.
"""

import pytest
from pydantic import ValidationError

from codemie.core.workflow_models.workflow_models import (
    WorkflowStateCondition,
    WorkflowStateSwitchCondition,
)


class TestWorkflowStateConditionExpressionValidation:
    def test_rejects_lowercase_true(self):
        with pytest.raises(ValidationError) as exc:
            WorkflowStateCondition(expression="valid == true", then="a", otherwise="b")

        assert "True" in str(exc.value)
        assert "true" in str(exc.value)

    def test_rejects_lowercase_false(self):
        with pytest.raises(ValidationError) as exc:
            WorkflowStateCondition(expression="valid == false", then="a", otherwise="b")

        assert "False" in str(exc.value)
        assert "false" in str(exc.value)

    def test_accepts_uppercase_true(self):
        condition = WorkflowStateCondition(expression="valid == True", then="a", otherwise="b")
        assert condition.expression == "valid == True"

    def test_accepts_uppercase_false(self):
        condition = WorkflowStateCondition(expression="valid == False", then="a", otherwise="b")
        assert condition.expression == "valid == False"

    def test_allows_quoted_true_string_literal(self):
        # 'true' inside a string literal is a value comparison, not a YAML/Python
        # boolean literal mistake, and must not be flagged.
        condition = WorkflowStateCondition(expression="status == 'true'", then="a", otherwise="b")
        assert condition.expression == "status == 'true'"

    def test_rejects_invalid_python_syntax(self):
        with pytest.raises(ValidationError) as exc:
            WorkflowStateCondition(expression="valid ==", then="a", otherwise="b")

        assert "syntax" in str(exc.value).lower()


class TestWorkflowStateSwitchConditionExpressionValidation:
    def test_rejects_lowercase_true(self):
        with pytest.raises(ValidationError) as exc:
            WorkflowStateSwitchCondition(condition="x == true", state_id="a")

        assert "True" in str(exc.value)

    def test_rejects_lowercase_false(self):
        with pytest.raises(ValidationError) as exc:
            WorkflowStateSwitchCondition(condition="x == false", state_id="a")

        assert "False" in str(exc.value)

    def test_accepts_valid_expression(self):
        switch_condition = WorkflowStateSwitchCondition(condition="x == 1", state_id="a")
        assert switch_condition.condition == "x == 1"
