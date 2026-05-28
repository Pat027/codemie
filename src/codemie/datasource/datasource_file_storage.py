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

from codemie.repository.base_file_repository import FileRepository
from codemie_tools.base.file_object import FileObject


class DatasourceFileStorage:
    """Thin wrapper around FileRepository that fixes the owner to ``datasource-{datasource_id}``.

    Keeps the naming logic in one place so callers never construct the owner string directly.
    """

    def __init__(self, datasource_id: str, file_repo: FileRepository) -> None:
        self._owner = f"datasource-{datasource_id}"
        self._repo = file_repo

    def write_file(self, name: str, mime_type: str, content: bytes) -> FileObject:
        """Upload binary content.

        ``content: bytes`` intentionally narrows ``FileRepository.write_file``'s ``content: Any``;
        this wrapper is for binary image content only.
        """
        return self._repo.write_file(name=name, mime_type=mime_type, owner=self._owner, content=content)
