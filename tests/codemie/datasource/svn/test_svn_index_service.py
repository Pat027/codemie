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

"""Tests for SVNIndexService."""

from unittest.mock import patch

import pytest

from codemie.core.exceptions import ExtendedHTTPException
from codemie.datasource.svn.svn_index_service import SVNIndexService


# --- validate_credentials ---


class TestValidateCredentials:
    def test_no_setting_id_skips_validation(self):
        with patch("codemie.datasource.svn.svn_index_service.SettingsService") as mock_svc:
            SVNIndexService.validate_credentials(
                user_id="u1", project_name="proj", repo_link="http://svn", setting_id=None
            )
        mock_svc.get_svn_creds.assert_not_called()

    def test_empty_setting_id_skips_validation(self):
        with patch("codemie.datasource.svn.svn_index_service.SettingsService") as mock_svc:
            SVNIndexService.validate_credentials(
                user_id="u1", project_name="proj", repo_link="http://svn", setting_id=""
            )
        mock_svc.get_svn_creds.assert_not_called()

    def test_valid_setting_id_calls_get_svn_creds(self):
        with patch("codemie.datasource.svn.svn_index_service.SettingsService") as mock_svc:
            SVNIndexService.validate_credentials(
                user_id="u1",
                project_name="proj",
                repo_link="http://svn",
                setting_id="s1",
            )
        mock_svc.get_svn_creds.assert_called_once_with(
            user_id="u1",
            project_name="proj",
            repo_link="http://svn",
            setting_id="s1",
        )

    def test_get_svn_creds_raises_becomes_extended_http_exception(self):
        with patch("codemie.datasource.svn.svn_index_service.SettingsService") as mock_svc:
            mock_svc.get_svn_creds.side_effect = Exception("bad creds")
            with pytest.raises(ExtendedHTTPException) as exc_info:
                SVNIndexService.validate_credentials(
                    user_id="u1", project_name="proj", repo_link="http://svn", setting_id="s1"
                )
        assert exc_info.value.code == 422
        assert "SVN Integration Error" in exc_info.value.message

    def test_exception_message_included_in_details(self):
        with patch("codemie.datasource.svn.svn_index_service.SettingsService") as mock_svc:
            mock_svc.get_svn_creds.side_effect = Exception("connection refused")
            with pytest.raises(ExtendedHTTPException) as exc_info:
                SVNIndexService.validate_credentials(
                    user_id="u1", project_name="proj", repo_link="http://svn", setting_id="s1"
                )
        assert "connection refused" in exc_info.value.details
