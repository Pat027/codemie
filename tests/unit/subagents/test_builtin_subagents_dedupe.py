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

import unittest

from codemie.service.subagents.builtin_subagents import BuiltinSubagent


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


class TestBuiltinSubagentsDedupe(unittest.TestCase):
    def test_dedupe_preserves_order(self):
        items = [
            BuiltinSubagent.GENERAL_PURPOSE_SUBAGENT.value,
            BuiltinSubagent.GENERAL_PURPOSE_SUBAGENT.value,
        ]
        self.assertEqual(_dedupe_preserve_order(items), [BuiltinSubagent.GENERAL_PURPOSE_SUBAGENT.value])
