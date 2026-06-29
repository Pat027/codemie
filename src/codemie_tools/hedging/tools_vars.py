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

from codemie_tools.base.models import ToolMetadata

EXAMPLE_HEDGE_TOOL = ToolMetadata(
    name="example_hedge_tool",
    description="Example hedgeable tool for testing. Randomly returns an empty or non-empty result.",
    label="Example Hedge Tool",
    user_description="Example hedging tool that demonstrates the fast-path pattern.",
)
