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

from datetime import datetime
from typing import List, Optional, Any

from codemie.core.constants import CodeIndexType, DatasourceTypes
from codemie.core.models import SVNRepo
from codemie.datasource.base_datasource_processor import BaseDatasourceProcessor
from codemie.datasource.datasources_config import SVN_CONFIG
from codemie.datasource.loader.svn_loader import SVNBatchLoader
from codemie.rest_api.models.guardrail import GuardrailAssignmentItem
from codemie.rest_api.models.index import IndexInfo
from codemie.rest_api.security.user import User
from codemie.service.settings.settings import SettingsService


class SVNDatasourceProcessor(BaseDatasourceProcessor):
    loader: Optional[Any] = None

    def __init__(
        self,
        repo: SVNRepo,
        user: User,
        index: Optional[IndexInfo] = None,
        request_uuid: Optional[str] = None,
        guardrail_assignments: Optional[List[GuardrailAssignmentItem]] = None,
    ):
        super().__init__(
            datasource_name=repo.name,
            index=index,
            user=user,
            request_uuid=request_uuid,
            guardrail_assignments=guardrail_assignments,
        )
        self.repo = repo

    @property
    def _index_name(self) -> str:
        return self.repo.get_identifier()

    @property
    def _processing_batch_size(self) -> int:
        return SVN_CONFIG.loader_batch_size

    @classmethod
    def create_processor(
        cls,
        svn_repo: SVNRepo,
        user: User | None = None,
        index: Optional[IndexInfo] = None,
        request_uuid: Optional[str] = None,
        guardrail_assignments: Optional[List[GuardrailAssignmentItem]] = None,
    ) -> "SVNDatasourceProcessor":
        if svn_repo.index_type == CodeIndexType.CODE:
            return cls(
                repo=svn_repo,
                user=user,
                index=index,
                request_uuid=request_uuid,
                guardrail_assignments=guardrail_assignments,
            )
        elif svn_repo.index_type == CodeIndexType.SUMMARY:
            from codemie.datasource.code.code_summary_datasource_processor import CodeSummaryDatasourceProcessor

            return CodeSummaryDatasourceProcessor(
                repo=svn_repo,
                user=user,
                index=index,
                request_uuid=request_uuid,
                guardrail_assignments=guardrail_assignments,
            )
        elif svn_repo.index_type == CodeIndexType.CHUNK_SUMMARY:
            from codemie.datasource.code.code_summary_datasource_processor import CodeChunkSummaryDatasourceProcessor

            return CodeChunkSummaryDatasourceProcessor(
                repo=svn_repo,
                user=user,
                index=index,
                request_uuid=request_uuid,
                guardrail_assignments=guardrail_assignments,
            )
        else:
            raise NotImplementedError(f"Unsupported SVN index type: {svn_repo.index_type}")

    def _on_process_start(self):
        self.repo.save()

    def _on_process_end(self):
        stats = self.loader.fetch_remote_stats() if self.loader else {}
        head_revision = stats.get(SVNBatchLoader.HEAD_REVISION_KEY)
        if head_revision is not None:
            self.repo.last_indexed_revision = head_revision
        self.repo.save()

    def _init_loader(self) -> SVNBatchLoader:
        creds = SettingsService.get_svn_creds(
            user_id=self.user.id,
            project_name=self.index.project_name,
            repo_link=self.repo.link,
            setting_id=self.index.setting_id,
        )
        return SVNBatchLoader.create_loader(
            svn_repo=self.repo,
            creds=creds,
            request_uuid=self.request_uuid,
            datasource_id=self.index.id or "" if self.index else "",
        )

    def _init_index(self):
        if not self.index:
            self.index = IndexInfo.new(
                project_name=self.repo.app_id,
                repo_name=self.repo.name,
                description=self.repo.description,
                branch=self.repo.branch,
                link=self.repo.link,
                files_filter=self.repo.files_filter,
                index_type=self.repo.index_type.value,
                vcs_type=DatasourceTypes.SVN,
                prompt=self.repo.prompt,
                project_space_visible=self.repo.project_space_visible,
                docs_generation=self.repo.docs_generation,
                embeddings_model=self.repo.embeddings_model,
                summarization_model=self.repo.summarization_model,
                user=self.user,
                setting_id=self.repo.setting_id,
            )
        else:
            self.index.date = datetime.now()

        self._assign_and_sync_guardrails()
