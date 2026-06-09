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

"""Facade use-case for updating a file-type knowledge-base datasource."""

from __future__ import annotations

from codemie.core.ability import Ability, Action
from fastapi import BackgroundTasks, status

from codemie.core.exceptions import ExtendedHTTPException
from codemie.core.models import BaseResponse
from codemie.datasource.file.file_datasource_update_processor import FileDatasourceUpdateProcessor
from codemie.rest_api.models.index import UpdateKnowledgeBaseFileRequest
from codemie.rest_api.security.user import User
from codemie.service.datasource.file_datasource_service import FileDatasourceService

_EDIT_SUCCESSFUL = "Edit successful"
_ACCESS_DENIED_MESSAGE = "Access denied"
_CHECK_PERMISSIONS_MESSAGE = "Please check your user permissions or contact an administrator for assistance."


class UpdateFileDatasourceUseCase:
    """Facade that orchestrates the entire update flow for file-type datasources.

    Responsibilities:
    - Resolve and validate inputs by delegating to :class:`FileDatasourceService`.
    - Choose between the metadata-only path and the file-reindex path.
    - Register the background task (FastAPI infrastructure concern kept out of the service).

    The service layer handles all business logic and storage operations; this class
    only coordinates the sequence of calls and converts the result to a
    :class:`BaseResponse`.
    """

    def __init__(self, service: FileDatasourceService) -> None:
        self._service = service

    def execute(
        self,
        request: UpdateKnowledgeBaseFileRequest,
        user: User,
        background_tasks: BackgroundTasks,
        request_uuid: str,
    ) -> BaseResponse:
        # 1. Resolve the datasource record.
        index = self._service.find_or_raise(request.project_name, request.name)

        if not Ability(user).can(Action.WRITE, index):
            raise ExtendedHTTPException(
                code=status.HTTP_403_FORBIDDEN,
                message=_ACCESS_DENIED_MESSAGE,
                details=f"You don't have permission to update the index '{request.name}'.",
                help=_CHECK_PERMISSIONS_MESSAGE,
            )

        # 2. Parse request parameters that require deserialization.
        uploaded_files_to_keep = self._service.parse_uploaded_files(request.uploaded_files, index)
        guardrail_assignments = self._service.parse_guardrail_assignments(request.guardrail_assignments)

        # 3. Compute which files were removed and whether file changes are present.
        changes = self._service.compute_file_changes(request.files, uploaded_files_to_keep, index)

        # 4. Business validations.
        self._service.validate_project_change(request.new_project_name, request.project_name, request.name, user)

        # 5a. Metadata-only path — no background task needed.
        if not changes.has_file_changes:
            self._service.update_metadata_only(
                index=index,
                user=user,
                description=request.description,
                project_space_visible=request.project_space_visible,
                new_project_name=request.new_project_name,
                guardrail_assignments=guardrail_assignments,
            )
            return BaseResponse(message=_EDIT_SUCCESSFUL)

        # 5b. File-changes path — upload new files and schedule re-indexing.
        prepared = self._service.upload_and_prepare_files(
            new_files=request.files or [],
            user=user,
            uploaded_files_to_keep=uploaded_files_to_keep,
            index=index,
        )
        # Persist the authoritative post-update state synchronously before the response
        # is returned, so the DB is consistent before the background task starts.
        processor = FileDatasourceUpdateProcessor(
            datasource_name=request.name,
            user=user,
            files_paths=prepared.all_files_paths,
            project_name=request.project_name,
            description=request.description,
            project_space_visible=request.project_space_visible,
            index=index,
            csv_separator=request.csv_separator,
            csv_start_row=request.csv_start_row,
            csv_rows_per_document=request.csv_rows_per_document,
            request_uuid=request_uuid,
            embedding_model=request.embedding_model,
            guardrail_assignments=guardrail_assignments,
            include_email_attachments=request.include_email_attachments,
            uploaded_files=prepared.uploaded_files,
            new_files_paths=prepared.new_files_paths,
            removed_files=changes.removed_files,
        )
        processor.init_index()
        processor.schedule(background_tasks, func=processor.reprocess)
        return BaseResponse(message=processor.started_message)
