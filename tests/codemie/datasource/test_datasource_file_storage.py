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

from unittest.mock import MagicMock

from codemie.datasource.datasource_file_storage import DatasourceFileStorage


class TestDatasourceFileStorage:
    def _make_storage(self, datasource_id: str = "abc-123"):
        mock_repo = MagicMock()
        return DatasourceFileStorage(datasource_id=datasource_id, file_repo=mock_repo), mock_repo

    def test_owner_prefixed_with_datasource(self):
        storage, _ = self._make_storage("550e8400-e29b-41d4-a716-446655440000")
        assert storage._owner == "datasource-550e8400-e29b-41d4-a716-446655440000"

    def test_empty_datasource_id_still_adds_prefix(self):
        storage, _ = self._make_storage("")
        assert storage._owner == "datasource-"

    def test_write_file_delegates_to_repo_with_correct_owner(self):
        storage, mock_repo = self._make_storage("my-uuid")
        content = b"image bytes"
        storage.write_file(name="photo.jpg", mime_type="image/jpeg", content=content)
        mock_repo.write_file.assert_called_once_with(
            name="photo.jpg",
            mime_type="image/jpeg",
            owner="datasource-my-uuid",
            content=content,
        )

    def test_write_file_returns_file_object(self):
        storage, mock_repo = self._make_storage()
        mock_file_obj = MagicMock()
        mock_repo.write_file.return_value = mock_file_obj
        result = storage.write_file(name="f.png", mime_type="image/png", content=b"data")
        assert result is mock_file_obj

    def test_different_datasource_ids_produce_different_owners(self):
        s1, _ = self._make_storage("id-1")
        s2, _ = self._make_storage("id-2")
        assert s1._owner != s2._owner
        assert s1._owner == "datasource-id-1"
        assert s2._owner == "datasource-id-2"
