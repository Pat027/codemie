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

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import yaml

from codemie.configs import config
from codemie.configs.logger import logger
from codemie.service.subagents.builtin_subagents import BuiltinSubagent


@dataclass(frozen=True)
class BuiltinSubagentInfo:
    id: BuiltinSubagent
    display_name: str


class BuiltinSubagentsRegistryError(RuntimeError):
    pass


class BuiltinSubagentsRegistry:
    """Loads and serves built-in subagent definitions from config/subagents/subagents.yaml."""

    CONFIG_PATH = config.BUILTIN_SUBAGENTS_CONFIG_PATH

    @classmethod
    @lru_cache(maxsize=1)
    def _load_raw(cls) -> dict[str, Any]:
        try:
            with open(cls.CONFIG_PATH, "r", encoding="utf-8") as f:
                payload = yaml.safe_load(f) or {}
        except FileNotFoundError as e:
            raise BuiltinSubagentsRegistryError(f"Builtin subagents config not found at {cls.CONFIG_PATH}") from e
        except Exception as e:
            raise BuiltinSubagentsRegistryError(
                f"Failed to read builtin subagents config at {cls.CONFIG_PATH}: {e}"
            ) from e

        if not isinstance(payload, dict) or "subagents" not in payload:
            raise BuiltinSubagentsRegistryError(
                "Invalid builtin subagents config structure: expected top-level "
                f"'subagents' mapping at {cls.CONFIG_PATH}"
            )

        subagents = payload.get("subagents")
        if not isinstance(subagents, dict):
            raise BuiltinSubagentsRegistryError(
                f"Invalid builtin subagents config structure: 'subagents' must be a mapping at {cls.CONFIG_PATH}"
            )

        return payload

    @classmethod
    def list_available(cls) -> list[BuiltinSubagentInfo]:
        raw = cls._load_raw().get("subagents", {})
        result: list[BuiltinSubagentInfo] = []
        for item in BuiltinSubagent:
            entry = raw.get(item.value)
            if not isinstance(entry, dict):
                logger.warning(
                    f"Builtin subagent '{item.value}' is missing from config {cls.CONFIG_PATH}; skipping from catalog"
                )
                continue
            display_name = str(entry.get("display_name") or "").strip()
            if not display_name:
                logger.warning(
                    f"Builtin subagent '{item.value}' has empty display_name in config {cls.CONFIG_PATH}; "
                    "skipping from catalog"
                )
                continue
            result.append(BuiltinSubagentInfo(id=item, display_name=display_name))
        return result

    @classmethod
    def get_system_prompt(cls, subagent: BuiltinSubagent) -> str:
        return cls._get_entry_field(subagent, "system_prompt")

    @classmethod
    def get_display_name(cls, subagent: BuiltinSubagent) -> str:
        return cls._get_entry_field(subagent, "display_name")

    @classmethod
    def _get_entry_field(cls, subagent: BuiltinSubagent, field: str) -> str:
        raw = cls._load_raw().get("subagents", {})
        entry = raw.get(subagent.value)
        if not isinstance(entry, dict):
            raise BuiltinSubagentsRegistryError(
                f"Builtin subagent '{subagent.value}' is not configured under 'subagents' in {cls.CONFIG_PATH}"
            )
        value = str(entry.get(field) or "").strip()
        if not value:
            raise BuiltinSubagentsRegistryError(
                f"Builtin subagent '{subagent.value}' has empty {field} in {cls.CONFIG_PATH}"
            )
        return value
