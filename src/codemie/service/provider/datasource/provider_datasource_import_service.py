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

"""Imports datasources that already exist on a provider into CodeMie.

Provider-agnostic: for every configured provider that is *importable* (see
``import_sources.resolve_import_source``), this enumerates the datasources on that provider and
back-fills an ``index_info`` row (``index_type="provider"``) for each one not already registered.
Deduped by external datasource id, so re-running only imports newly-appeared datasources.

It never invokes a provider lifecycle tool — the datasources are already built — so the import
only writes CodeMie rows. Providers that aren't installed or aren't importable are simply skipped,
so the feature degrades gracefully (e.g. when AICE isn't installed there is nothing to import).
"""

from typing import List, Optional, Set

from pydantic import BaseModel
from sqlmodel import Session, select

from codemie.configs import logger
from codemie.core.models import CreatedByUser
from codemie.rest_api.models.index import IndexInfo, IndexInfoProviderFields
from codemie.rest_api.models.provider import Provider, ProviderBase
from codemie.rest_api.security.user import User
from codemie.rest_api.utils.default_applications import CODEMIE_PROJECT_NAME, ensure_application_exists
from codemie.service.provider.datasource.constants import PROVIDER_INDEX_TYPE
from codemie.service.provider.datasource.import_sources import ExternalDatasource, resolve_import_source


class ProviderImportResult(BaseModel):
    """Per-provider import outcome."""

    provider_name: str
    imported: int = 0
    skipped: int = 0


class DatasourceImportSummary(BaseModel):
    """Result of a datasource import run across all importable providers."""

    total_imported: int = 0
    total_skipped: int = 0
    providers: List[ProviderImportResult] = []
    errors: List[str] = []


class ProviderDatasourceImportService:
    """Back-fills CodeMie ``index_info`` rows for datasources already present on providers."""

    DESCRIPTION_MAX_LENGTH = 500
    FALLBACK_PROJECT_NAME = CODEMIE_PROJECT_NAME
    MAX_PROVIDERS = 1000

    # Only fully-built datasources are usable; non-ready ones would create rows marked
    # completed=True that fail at retrieval, so they are skipped (counted as skipped).
    READY_STATUSES = {"ready", "indexed"}

    def __init__(self, user: User):
        self.user = user

    @classmethod
    def _all_providers(cls) -> List[ProviderBase]:
        return Provider.get_all(page_number=1, items_per_page=cls.MAX_PROVIDERS)

    @classmethod
    def importable_provider_names(cls, user: User) -> List[str]:
        """Names of installed providers that can be imported from (drives UI availability)."""
        return [p.name for p in cls._all_providers() if resolve_import_source(p, user) is not None]

    def run(self) -> DatasourceImportSummary:
        summary = DatasourceImportSummary()

        # Pass 1: gather datasources from every importable provider and build a project-inheritance
        # map. A datasource that contains others (e.g. a code-exploration workspace) lets its member
        # datasources (e.g. code-analysis datasources, which have no project of their own) inherit
        # its project.
        collected = []
        inherited_projects: dict = {}
        for provider in self._all_providers():
            source = resolve_import_source(provider, self.user)
            if source is None:
                continue
            try:
                externals = source.list_external_datasources()
            except Exception as e:  # noqa: BLE001 - report and continue with other providers
                logger.error(f"Failed to list datasources for provider {provider.name}: {e}")
                summary.errors.append(f"{provider.name}: {e}")
                continue
            collected.append((provider, externals))
            for ext in externals:
                if ext.project:
                    for child_id in ext.member_datasource_ids:
                        inherited_projects.setdefault(child_id, ext.project)

        # Pass 2: import, resolving each datasource's project (own → inherited → fallback).
        for provider, externals in collected:
            result = self._import_for_provider(provider, externals, inherited_projects, summary.errors)
            summary.providers.append(result)
            summary.total_imported += result.imported
            summary.total_skipped += result.skipped

        logger.info(
            "Provider datasource import completed",
            extra={
                "total_imported": summary.total_imported,
                "total_skipped": summary.total_skipped,
                "providers": [p.provider_name for p in summary.providers],
                "errors": len(summary.errors),
            },
        )
        return summary

    def _import_for_provider(
        self,
        provider: ProviderBase,
        externals: List[ExternalDatasource],
        inherited_projects: dict,
        errors: List[str],
    ) -> ProviderImportResult:
        result = ProviderImportResult(provider_name=provider.name)
        toolkit_id = self._resolve_datasource_toolkit_id(provider)
        existing = self._existing_datasource_ids(provider.id)

        for ext in externals:
            if ext.status and ext.status.lower() not in self.READY_STATUSES:
                result.skipped += 1
                continue
            if ext.datasource_id in existing:
                result.skipped += 1
                continue

            project_name = ext.project or inherited_projects.get(ext.datasource_id) or self.FALLBACK_PROJECT_NAME
            try:
                ensure_application_exists(project_name)
                self._build_index_info(provider, toolkit_id, ext, project_name).save()
                existing.add(ext.datasource_id)
                result.imported += 1
            except Exception as e:  # noqa: BLE001 - partial-failure tolerant
                logger.error(f"Failed to import datasource {ext.datasource_id} ({provider.name}): {e}")
                errors.append(f"{provider.name}/{ext.datasource_id}: {e}")

        return result

    @staticmethod
    def _resolve_datasource_toolkit_id(provider: ProviderBase) -> Optional[str]:
        """Return the id of the provider's datasource (lifecycle/retrieval) toolkit.

        Deliberately NOT the catalog toolkit: imported rows store this toolkit_id so they
        remain usable for later data retrieval / reindex via the datasource toolkit.
        """
        toolkit = next(
            (
                tk
                for tk in provider.provided_toolkits
                if any(t.is_datasource_action or t.is_datasource_tool for t in tk.provided_tools)
            ),
            None,
        )
        if toolkit is None and provider.provided_toolkits:
            toolkit = provider.provided_toolkits[0]
        return toolkit.toolkit_id if toolkit else None

    @staticmethod
    def _existing_datasource_ids(provider_id: str) -> Set[str]:
        statement = select(IndexInfo).where(
            IndexInfo.get_field_expression("provider_fields.provider_id") == provider_id
        )
        with Session(IndexInfo.get_engine()) as session:
            rows = session.exec(statement).all()
        return {
            row.provider_fields.base_params.get("datasource_id")
            for row in rows
            if row.provider_fields and row.provider_fields.base_params
            if row.provider_fields.base_params.get("datasource_id")
        }

    def _build_index_info(
        self,
        provider: ProviderBase,
        toolkit_id: Optional[str],
        ext: ExternalDatasource,
        project_name: str,
    ) -> IndexInfo:
        """Construct a 'provider' IndexInfo row for an already-built external datasource.

        The datasource is already built, so the row is marked ready (completed) and usable.
        base_params holds only datasource_id (no secret fields), so no encryption is applied.
        """
        return IndexInfo(
            repo_name=ext.name,
            index_type=PROVIDER_INDEX_TYPE,
            project_name=project_name,
            description=(ext.description or "")[: self.DESCRIPTION_MAX_LENGTH],
            project_space_visible=True,
            completed=True,
            is_fetching=False,
            is_queued=False,
            error=False,
            current_state=0,
            complete_state=0,
            current__chunks_state=0,
            created_by=CreatedByUser(id=self.user.id, username=self.user.username, name=self.user.name).dict(),
            provider_fields=IndexInfoProviderFields(
                provider_id=provider.id,
                toolkit_id=toolkit_id or "",
                base_params={"datasource_id": ext.datasource_id},
                create_params={},
            ),
        )
