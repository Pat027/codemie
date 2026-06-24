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

"""Provider-agnostic discovery of datasources that exist on a provider.

An *import source* knows how to list the datasources that already exist on one provider so
CodeMie can back-fill ``index_info`` rows for the ones it doesn't track yet.

Discovery is capability-based: ``GenericSpiCatalogImportSource`` works with ANY provider whose
descriptor advertises a datasource-unscoped ``CATALOG`` tool (``Purpose.CATALOG``) and invokes
it over the SPI. Adding a new provider therefore requires no CodeMie code — it only needs to
expose the CATALOG capability. ``resolve_import_source`` returns a source for such a provider,
or ``None`` when the provider has no listing capability (e.g. it isn't importable)
so the import flow degrades gracefully.
"""

import json
from typing import Any, List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from codemie.clients.provider.client import ToolInvocationRequest, ToolkitConfiguration
from codemie.configs import logger
from codemie.clients.provider import client as provider_client
from codemie.rest_api.models.provider import ProviderBase
from codemie.rest_api.security.user import User
from codemie.service.provider.provider_api_client import ProviderAPIClient


# --- CATALOG capability response contract -------------------------------------------------------
# ``list_datasources`` tool must satisfy. It is validated on the way in (see
# ``GenericSpiCatalogImportSource._parse``) because the tool runs on a remote provider and may
# return anything. A full description for provider implementers lives in ``catalog_capability.md``
# next to this module. Expected JSON shape:
#
#   {
#     "status": "success",                       # optional, ignored
#     "datasources": [
#       {
#         "datasource_id": "<id>",               # required ("id" accepted as an alias)
#         "name": "<display name>",              # optional (falls back to the id)
#         "description": "<text>",               # optional
#         "status": "ready" | "indexed" | ...,   # optional (only READY datasources are imported)
#         "project": "<project>" | null,         # optional (child datasources inherit the parent's)
#         "member_datasource_ids": ["<id>", ...] # optional (ids of contained datasources)
#       }
#     ]
#   }


class ExternalDatasource(BaseModel):
    """A datasource that exists on a provider, normalized across import sources.

    This is also the per-entry schema for a CATALOG tool response: lenient on input — accepts
    ``id`` as an alias for ``datasource_id``, ignores unknown keys, and normalizes missing values
    (null name falls back to the id, null description/members become empty) — so providers can
    return richer payloads without breaking import.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    datasource_id: str = Field(validation_alias=AliasChoices("datasource_id", "id"))
    name: str = ""
    description: str = ""
    status: Optional[str] = None
    project: Optional[str] = None
    member_datasource_ids: List[str] = Field(
        default_factory=list,
        description="A list of IDs of members who are members of this datasource.",
    )

    @field_validator("datasource_id", mode="before")
    @classmethod
    def _stringify_id(cls, value: Any) -> Optional[str]:
        return str(value) if value is not None else value

    @field_validator("name", "description", mode="before")
    @classmethod
    def _none_to_empty(cls, value: Any) -> str:
        return value or ""

    @field_validator("member_datasource_ids", mode="before")
    @classmethod
    def _stringify_member_ids(cls, value: Any) -> List[str]:
        return [str(member) for member in (value or [])]

    @model_validator(mode="after")
    def _default_name_to_id(self) -> "ExternalDatasource":
        if not self.name:
            self.name = self.datasource_id
        return self


class CatalogToolResponse(BaseModel):
    """Envelope returned by a provider's CATALOG ``list_datasources`` tool."""

    model_config = ConfigDict(extra="ignore")

    datasources: List[ExternalDatasource] = Field(default_factory=list)


class ProviderDatasourceImportSource:
    """Base class: lists the datasources that exist on a single provider."""

    def __init__(self, provider: ProviderBase, user: User):
        self.provider = provider
        self.user = user

    def list_external_datasources(self) -> List[ExternalDatasource]:
        raise NotImplementedError


class GenericSpiCatalogImportSource(ProviderDatasourceImportSource):
    """Lists datasources via a provider's SPI ``CATALOG`` capability.

    Provider-agnostic: any provider that advertises a datasource-unscoped tool with
    ``Purpose.CATALOG`` in its descriptor can be imported with no CodeMie-side changes.
    """

    @staticmethod
    def find_catalog_tool(provider: ProviderBase) -> Optional[tuple]:
        """Return ``(toolkit, tool)`` for the provider's catalog tool, or ``None``."""
        for toolkit in provider.provided_toolkits:
            tool = next((t for t in toolkit.provided_tools if t.is_catalog_tool), None)
            if tool:
                return toolkit, tool
        return None

    def list_external_datasources(self) -> List[ExternalDatasource]:
        found = self.find_catalog_tool(self.provider)
        if not found:
            return []
        toolkit, tool = found

        log_prefix = f"{self.provider.name} [catalog]:"
        api_client: provider_client.ToolInvocationManagementApi = ProviderAPIClient(
            user=self.user,
            url=str(self.provider.service_location_url),
            provider_security_config=self.provider.configuration,
            log_prefix=log_prefix,
        ).build()

        payload = ToolInvocationRequest(
            user_id=self.user.id,
            project_id="",
            configuration=ToolkitConfiguration(configuration_type="catalog", parameters={}),
            parameters={},
        )
        response = api_client.invoke_tool(
            toolkit_name=toolkit.name,
            tool_name=tool.name,
            tool_invocation_request=payload,
        )
        external_datasources = self._parse(getattr(response, "result", response))

        return external_datasources

    @staticmethod
    def _parse(result: Any) -> List[ExternalDatasource]:
        """Validate a CATALOG tool response against the schema and normalize it.

        The tool executes on a remote provider, so the payload is untrusted: it is parsed as JSON
        if needed and validated against ``CatalogToolResponse``. A non-JSON, non-dict or
        schema-invalid response is logged and treated as "nothing to import" rather than raising.
        """
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except ValueError:
                logger.error("Catalog tool returned non-JSON result")
                return []

        if not isinstance(result, dict):
            logger.error("Catalog tool returned unexpected result type: %s", type(result).__name__)
            return []

        try:
            catalog = CatalogToolResponse.model_validate(result)
        except ValidationError as exc:
            logger.error("Catalog tool response failed schema validation: %s", exc)
            return []

        return catalog.datasources


def resolve_import_source(provider: ProviderBase, user: User) -> Optional[ProviderDatasourceImportSource]:
    """Return an import source for a provider, or ``None`` if it isn't importable.

    A provider is importable only if it advertises a SPI ``CATALOG`` capability in its descriptor.
    """
    if GenericSpiCatalogImportSource.find_catalog_tool(provider):
        return GenericSpiCatalogImportSource(provider, user)
    return None
