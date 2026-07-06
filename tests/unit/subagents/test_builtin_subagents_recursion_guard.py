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

from __future__ import annotations

import unittest
from dataclasses import dataclass

from codemie.service.subagents.builtin_subagents import BuiltinSubagent


@dataclass
class _FakeAssistant:
    enabled_builtin_subagents: list[str]
    skill_ids: list[str]
    custom_metadata: dict | None


def _should_merge_skill_builtins(custom_metadata: dict | None) -> bool:
    if not isinstance(custom_metadata, dict):
        return True
    return custom_metadata.get("__disable_skill_builtin_subagents") is not True


class TestBuiltinSubagentsRecursionGuard(unittest.TestCase):
    def test_guard_disables_skill_level_builtins_for_builtin_clone(self):
        assistant = _FakeAssistant(
            enabled_builtin_subagents=[],
            skill_ids=["s1"],
            custom_metadata={"__disable_skill_builtin_subagents": True},
        )
        self.assertFalse(_should_merge_skill_builtins(assistant.custom_metadata))

    def test_guard_allows_skill_level_builtins_for_normal_assistant(self):
        assistant = _FakeAssistant(
            enabled_builtin_subagents=[],
            skill_ids=["s1"],
            custom_metadata=None,
        )
        self.assertTrue(_should_merge_skill_builtins(assistant.custom_metadata))

    def test_builtin_value_constant(self):
        self.assertEqual(BuiltinSubagent.GENERAL_PURPOSE_SUBAGENT.value, "GENERAL_PURPOSE_SUBAGENT")


if __name__ == "__main__":
    unittest.main()
