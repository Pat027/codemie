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

import logging
from typing import Any, Type

from codemie.clients.provider.client.models.tool_invocation_response import ToolInvocationResponse
from codemie.core.models import AssistantChatRequest
from codemie.rest_api.models.hedging import HedgingConfig
from codemie.rest_api.models.index import ProviderIndexInfo
from codemie.rest_api.models.provider import Provider
from codemie.rest_api.security.user import User
from codemie.service.provider.provider_tool_factory import ProviderToolFactory
from codemie.service.tools.dynamic_value_utils import process_string
from codemie_tools.base import toolkit_provider
from codemie_tools.base.codemie_hedge_tool import CodeMieHedgeTool, HedgeToolResult

from codemie.workflows.utils.safe_eval import SafeEvalError, safe_eval

logger = logging.getLogger(__name__)


class HedgingToolService:
    @classmethod
    def get_tool_definition(cls, tool_name: str) -> Type[CodeMieHedgeTool] | None:
        """Return the tool_class for a registered CodeMieHedgeTool, or None."""
        for toolkit in toolkit_provider.get_hedgeable_toolkits():
            for tool in toolkit.tools:
                if tool.name == tool_name:
                    return tool.tool_class
        return None

    @classmethod
    def instantiate(cls, hedging_cfg: HedgingConfig) -> CodeMieHedgeTool:
        """Instantiate a CodeMieHedgeTool by name; configuration comes from the tool's own .env-backed defaults.

        Raises ValueError if the tool is not found in the registry.
        """
        tool_name = hedging_cfg.tool.name
        tool_class = cls.get_tool_definition(tool_name)
        if tool_class is None:
            raise ValueError(
                f"Hedgeable tool '{tool_name}' not found in registry. "
                "Ensure it extends CodeMieHedgeTool and is registered in a toolkit."
            )
        return tool_class()

    @staticmethod
    def build_template_context(
        request: AssistantChatRequest,
        user: User,
        request_headers: dict,
    ) -> dict[str, Any]:
        """Build a Jinja2 template context from the current request, user, and extracted headers.

        Available template variables in input_mapping:
          {{query}}            — request.text
          {{conversation_id}}  — request.conversation_id
          {{user.id}}          — user.id
          {{user.name}}        — user.name
          {{user.username}}    — user.username
          {{user.email}}       — user.email
          {{user.token}}       — user.auth_token (bearer token)
          {{headers.x-foo}}    — HTTP header x-foo (from extract_custom_headers)
          {{metadata.key}}     — request.metadata["key"]

        Security note: {{user.token}} exposes the user's bearer token. Only map it to
        trusted internal provider tools.
        """
        return {
            "query": request.text or "",
            "conversation_id": request.conversation_id or "",
            "user": {
                "id": user.id or "",
                "name": user.name or "",
                "username": user.username or "",
                "email": user.email or "",
                "token": user.auth_token or "",
            },
            "headers": request_headers or {},
            "metadata": request.metadata or {},
        }

    @classmethod
    def invoke_provider_tool(
        cls,
        cfg: HedgingConfig,
        template_context: dict[str, Any],
        user: User,
        project_id: str,
        request_uuid: str,
    ) -> HedgeToolResult:
        """Resolve the provider tool from the DB and invoke it via ProviderToolFactory.

        The DB lookups and named-datasource resolution are hedging-specific; the HTTP
        invocation itself is delegated to ProviderToolFactory.invoke so it lives in the
        provider module and is shared with the agent tool path.

        Raises ValueError if the provider, toolkit, tool, or named datasource is not found.
        """
        p_cfg = cfg.provider_tool

        provider = Provider.get_by_fields({"name": p_cfg.provider_name})
        if provider is None:
            raise ValueError(f"Provider '{p_cfg.provider_name}' not found in DB")

        toolkit = next((t for t in provider.provided_toolkits if t.name == p_cfg.toolkit_name), None)
        if toolkit is None:
            raise ValueError(f"Toolkit '{p_cfg.toolkit_name}' not found on provider '{p_cfg.provider_name}'")

        tool = next((t for t in toolkit.provided_tools if t.name == p_cfg.tool_name), None)
        if tool is None:
            raise ValueError(f"Tool '{p_cfg.tool_name}' not found in toolkit '{p_cfg.toolkit_name}'")

        resolved_params = {k: process_string(v, template_context) for k, v in cfg.input_mapping.items()}
        datasource = cls._resolve_datasource(p_cfg.datasource_name, project_id)

        response: ToolInvocationResponse = ProviderToolFactory(provider, toolkit, tool, datasource=datasource).invoke(
            user=user,
            project_id=project_id,
            request_uuid=request_uuid,
            params=resolved_params,
            headers=template_context.get("headers") or None,
            datasource=datasource,
        )

        return cls._extract_provider_result(response, cfg.output_field, p_cfg.result_condition)

    @staticmethod
    def _resolve_datasource(datasource_name: str | None, project_id: str) -> ProviderIndexInfo | None:
        """Resolve a named datasource to its ProviderIndexInfo for the given project.

        Returns None when no datasource is configured. Raises ValueError if a name is given
        but no matching datasource exists. Decryption of the datasource configuration is
        handled downstream by ProviderToolFactory.invoke.
        """
        if not datasource_name:
            return None

        results = ProviderIndexInfo.filter_by_project_and_repo(
            project_name=project_id,
            repo_name=datasource_name,
        )
        if not results:
            raise ValueError(f"[HEDGED] Datasource '{datasource_name}' not found for project '{project_id}'")

        return results[0]

    @staticmethod
    def _evaluate_result_condition(result: Any, condition: str) -> bool:
        """Evaluate a configurable boolean expression against the raw provider tool result.

        Dict keys are exposed as top-level variables. JSON-style false/true/null aliases are injected.
        Returns False (fail-safe) if evaluation raises.
        """

        ctx: dict[str, Any] = result if isinstance(result, dict) else {"result": result}
        ctx = {"false": False, "true": True, "null": None, **ctx}
        try:
            return bool(safe_eval(condition, ctx))
        except SafeEvalError as e:
            logger.warning(
                f"[HEDGED] Expression contains unsafe construct, result_condition={condition!r} evaluation failed: {e}"
            )
            return False
        except SyntaxError as e:
            logger.warning(
                f"[HEDGED] Expression has invalid syntax, result_condition={condition!r} evaluation failed: {e}"
            )
            return False
        except Exception as e:
            logger.warning(
                f"[HEDGED] Failed to evaluate expression, result_condition={condition!r} evaluation failed: {e}"
            )
            return False

    @staticmethod
    def _traverse_field_path(result, output_field: str):
        """Walk a dot-notation path through nested dicts/lists. Returns (_missing, sentinel) on failure."""
        _missing = object()
        for part in output_field.split("."):
            if isinstance(result, dict):
                result = result.get(part, _missing)
            elif isinstance(result, (list, tuple)):
                try:
                    result = result[int(part)]
                except (IndexError, ValueError):
                    result = _missing
            else:
                result = _missing
            if result is _missing:
                return None, True
        return result, False

    @classmethod
    def _extract_provider_result(
        cls,
        response: ToolInvocationResponse,
        output_field: str | None,
        result_condition: str | None = None,
    ) -> HedgeToolResult:
        """Extract result data from a ToolInvocationResponse and wrap in HedgeToolResult."""
        if response.status != "Completed" or response.result is None:
            return HedgeToolResult(empty=True)

        if result_condition is not None and not cls._evaluate_result_condition(response.result, result_condition):
            return HedgeToolResult(empty=True)

        result = response.result
        if output_field:
            result, missing = cls._traverse_field_path(result, output_field)
            if missing:
                return HedgeToolResult(empty=True)

        if result is None:
            return HedgeToolResult(empty=True)
        return HedgeToolResult(empty=False, data=result)
