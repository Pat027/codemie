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

__all__ = [
    "ToolsService",
    "ToolkitLookupService",
    "ToolkitService",
    "ToolkitSettingService",
    "ToolsInfoService",
    "ToolsPreprocessorFactory",
]


def __getattr__(name: str):
    if name == "ToolsService":
        from .tool_service import ToolsService

        return ToolsService
    if name == "ToolkitLookupService":
        from .toolkit_lookup_service import ToolkitLookupService

        return ToolkitLookupService
    if name == "ToolkitService":
        from .toolkit_service import ToolkitService

        return ToolkitService
    if name == "ToolkitSettingService":
        from .toolkit_settings_service import ToolkitSettingService

        return ToolkitSettingService
    if name == "ToolsInfoService":
        from .tools_info_service import ToolsInfoService

        return ToolsInfoService
    if name == "ToolsPreprocessorFactory":
        from .tools_preprocessing import ToolsPreprocessorFactory

        return ToolsPreprocessorFactory
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
