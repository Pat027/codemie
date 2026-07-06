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
from typing import Any

from codemie.core.utils import dedupe_preserve_order
from codemie.repository.skill_repository import SkillRepository
from codemie.rest_api.models.assistant import Assistant, MCPServerDetails, ToolKitDetails
from codemie.rest_api.models.skill import Skill
from codemie.service.subagents.builtin_subagents import BuiltinSubagent


@dataclass(frozen=True)
class SkillContributions:
    """Request-scoped precomputed contributions from attached skills."""

    skills: list[Skill]
    toolkits: list[ToolKitDetails]
    mcp_servers: list[MCPServerDetails]
    builtin_subagents: list[BuiltinSubagent]


class SkillContributionsResolver:
    @staticmethod
    def _safe_get_runtime_attr(obj: Any, name: str, default: Any = None) -> Any:
        """Safely read runtime-only attrs from SQLModel/Pydantic objects.

        Pydantic v2 stores underscore attrs in `__pydantic_private__`. Under some
        SQLModel/SQLAlchemy construction paths, `__pydantic_private__` may be
        `None`, and plain `getattr(obj, "_foo")` can crash with
        `TypeError: 'NoneType' object is not subscriptable` (via Pydantic's
        `BaseModel.__getattr__`).

        We avoid `getattr(obj, name)` and read from `__dict__` /
        `__pydantic_private__` directly.
        """
        dct = getattr(obj, "__dict__", None)
        if isinstance(dct, dict) and name in dct:
            return dct[name]

        private = getattr(obj, "__pydantic_private__", None)
        if isinstance(private, dict) and name in private:
            return private[name]

        return default

    @staticmethod
    def _coerce_list(value) -> list:
        """Best-effort coercion of optional list-like fields.

        In production these fields are expected to be either `list[...]` or `None`.
        In unit tests, assistants/skills are often `Mock(spec=...)` where an
        unset attribute access returns another Mock, which is truthy but not
        iterable in the intended way.
        """
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple | set):
            return list(value)
        # Reject other truthy non-iterables (e.g. unittest.mock.Mock).
        return []

    @staticmethod
    def _coerce_builtin_subagents(items: Any) -> list[BuiltinSubagent]:
        """Coerce a mixed list (strings/enums) into BuiltinSubagent values.

        DB JSONB fields can come back as plain strings; API requests are typically
        parsed as enums. This helper makes request-scoped skill contribution
        resolution tolerant to both representations.
        """
        items = SkillContributionsResolver._coerce_list(items)
        if not items:
            return []

        result: list[BuiltinSubagent] = []
        for item in items:
            if isinstance(item, BuiltinSubagent):
                result.append(item)
                continue
            try:
                result.append(BuiltinSubagent(str(item)))
            except Exception:
                # Ignore unknown/invalid entries for backward/forward compatibility.
                continue
        return result

    @staticmethod
    def resolve_skills_for_assistant(assistant: Assistant) -> list[Skill]:
        """Resolve skills for an assistant, preferring runtime contributions if present.

        Consumers that only need the Skill list (e.g., to merge toolkits/MCP servers
        or builtin subagents) should use this helper to:
        - avoid threading SkillContributions through multiple layers, and
        - avoid repeated DB fetches when contributions were already precomputed for
          this request.
        """
        skill_ids = SkillContributionsResolver._coerce_list(getattr(assistant, "skill_ids", None))
        if not skill_ids:
            return []

        runtime_contribs = SkillContributionsResolver._safe_get_runtime_attr(
            assistant, "_runtime_skill_contributions", None
        )
        if runtime_contribs is not None and getattr(runtime_contribs, "skills", None) is not None:
            return list(runtime_contribs.skills)

        return SkillRepository.get_by_ids(list(skill_ids))

    @staticmethod
    def resolve_for_assistant(assistant: Assistant) -> SkillContributions:
        """
        Resolve skill-contributed configuration for an assistant with a single DB fetch.

        This intentionally does not mutate the Assistant instance; consumers decide how to merge
        with assistant-local config.
        """
        skill_ids = SkillContributionsResolver._coerce_list(getattr(assistant, "skill_ids", None))
        if not skill_ids:
            return SkillContributions(skills=[], toolkits=[], mcp_servers=[], builtin_subagents=[])

        skills = SkillRepository.get_by_ids(skill_ids)

        toolkits: list[ToolKitDetails] = []
        mcp_servers: list[MCPServerDetails] = []
        builtin_subagents: list[BuiltinSubagent] = []

        for skill in skills:
            toolkits.extend(SkillContributionsResolver._coerce_list(getattr(skill, "toolkits", None)))
            mcp_servers.extend(SkillContributionsResolver._coerce_list(getattr(skill, "mcp_servers", None)))
            builtin_subagents.extend(
                SkillContributionsResolver._coerce_builtin_subagents(getattr(skill, "enabled_builtin_subagents", None))
            )

        # De-dupe by stable keys (toolkit name, mcp server name, builtin value).
        toolkits = dedupe_preserve_order(toolkits, key=lambda t: t.toolkit)
        mcp_servers = dedupe_preserve_order(mcp_servers, key=lambda s: s.name)
        builtin_subagents = dedupe_preserve_order(builtin_subagents, key=lambda b: b.value)

        return SkillContributions(
            skills=skills,
            toolkits=toolkits,
            mcp_servers=mcp_servers,
            builtin_subagents=builtin_subagents,
        )
