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

"""Tests for SvnClient."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from codemie.datasource.loader.svn_client import SVNClientError, SvnClient
from codemie.rest_api.models.settings import SVNAuthType, SVNCredentials


class TestSvnIsAvailable:
    def test_returns_true_when_svn_on_path(self):
        with patch("codemie.datasource.loader.svn_client.shutil.which", return_value="/usr/bin/svn"):
            assert SvnClient.svn_is_available() is True

    def test_returns_false_when_svn_not_on_path(self):
        with patch("codemie.datasource.loader.svn_client.shutil.which", return_value=None):
            assert SvnClient.svn_is_available() is False


class TestBuildAuthFlags:
    def test_basic_auth_includes_username_password_no_cache(self):
        creds = SVNCredentials(auth_type=SVNAuthType.BASIC, username="alice", password="secret")
        flags = SvnClient._build_auth_flags(creds)
        assert "--username" in flags
        assert "alice" in flags
        assert "--password" in flags
        assert "secret" in flags
        assert "--no-auth-cache" in flags

    def test_basic_auth_without_username_omits_credential_flags(self):
        creds = SVNCredentials(auth_type=SVNAuthType.BASIC, username=None, password=None)
        flags = SvnClient._build_auth_flags(creds)
        assert "--username" not in flags
        assert "--password" not in flags


class TestSvnClientGetLatestRevnum:
    _URL = "https://svn.example.com/repos/test/trunk"

    def _make_creds(self):
        return SVNCredentials(auth_type=SVNAuthType.BASIC, username="u", password="p")

    def _info_xml(self, revision: int) -> bytes:
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<info><entry kind="dir" path="." revision="{revision}">'
            f'<commit revision="{revision - 1}"/></entry></info>'
        ).encode()

    def test_returns_entry_revision(self):
        client = SvnClient(self._URL, self._make_creds())
        mock_result = MagicMock()
        mock_result.stdout = self._info_xml(42)
        with patch("subprocess.run", return_value=mock_result):
            rev = client.get_latest_revnum()
        assert rev == 42

    def test_passes_url_and_auth_flags_to_subprocess(self):
        client = SvnClient(self._URL, self._make_creds())
        mock_result = MagicMock()
        mock_result.stdout = self._info_xml(1)
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            client.get_latest_revnum()
        cmd = mock_run.call_args[0][0]
        assert cmd[:3] == ["svn", "info", "--xml"]
        assert self._URL in cmd
        assert "--non-interactive" in cmd

    def test_raises_on_non_zero_exit(self):
        client = SvnClient(self._URL, self._make_creds())
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "svn", stderr=b"auth failed")):
            with pytest.raises(SVNClientError, match="svn info failed"):
                client.get_latest_revnum()


class TestSvnClientGetDir:
    _URL = "https://svn.example.com/repos/test/trunk"

    def _make_creds(self):
        return SVNCredentials(auth_type=SVNAuthType.BASIC, username="u", password="p")

    def _list_xml(self, entries: list[dict]) -> bytes:
        items = ""
        for e in entries:
            size_tag = f"<size>{e['size']}</size>" if e["kind"] == "file" else ""
            items += f'<entry kind="{e["kind"]}"><name>{e["name"]}</name>{size_tag}</entry>'
        return f'<?xml version="1.0"?><lists><list path="{self._URL}">{items}</list></lists>'.encode()

    def test_returns_file_and_dir_entries(self):
        client = SvnClient(self._URL, self._make_creds())
        xml = self._list_xml(
            [
                {"kind": "file", "name": "README.md", "size": 1024},
                {"kind": "dir", "name": "src", "size": 0},
            ]
        )
        mock_result = MagicMock(stdout=xml)
        with patch("subprocess.run", return_value=mock_result):
            result = client.get_dir("", 10)
        assert result["README.md"] == {"kind": "file", "size": 1024}
        assert result["src"] == {"kind": "dir", "size": 0}

    def test_empty_directory_returns_empty_dict(self):
        client = SvnClient(self._URL, self._make_creds())
        xml = f'<?xml version="1.0"?><lists><list path="{self._URL}"></list></lists>'.encode()
        mock_result = MagicMock(stdout=xml)
        with patch("subprocess.run", return_value=mock_result):
            result = client.get_dir("", 5)
        assert result == {}

    def test_root_path_uses_url_without_slash(self):
        client = SvnClient(self._URL, self._make_creds())
        xml = self._list_xml([])
        mock_result = MagicMock(stdout=xml)
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            client.get_dir("", 7)
        cmd = mock_run.call_args[0][0]
        assert f"{self._URL}@7" in cmd
        assert f"{self._URL}/@7" not in cmd

    def test_sub_path_appended_to_url(self):
        client = SvnClient(self._URL, self._make_creds())
        xml = self._list_xml([])
        mock_result = MagicMock(stdout=xml)
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            client.get_dir("subdir", 3)
        cmd = mock_run.call_args[0][0]
        assert f"{self._URL}/subdir@3" in cmd

    def test_raises_on_non_zero_exit(self):
        client = SvnClient(self._URL, self._make_creds())
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "svn", stderr=b"not found")):
            with pytest.raises(SVNClientError, match="svn list failed"):
                client.get_dir("", 1)


class TestSvnClientGetFile:
    _URL = "https://svn.example.com/repos/test/trunk"

    def _make_creds(self):
        return SVNCredentials(auth_type=SVNAuthType.BASIC, username="u", password="p")

    def test_returns_stdout_bytes(self):
        client = SvnClient(self._URL, self._make_creds())
        mock_result = MagicMock(stdout=b"def hello(): pass\n")
        with patch("subprocess.run", return_value=mock_result):
            content = client.get_file("src/main.py", 10)
        assert content == b"def hello(): pass\n"

    def test_command_includes_target_with_revision(self):
        client = SvnClient(self._URL, self._make_creds())
        mock_result = MagicMock(stdout=b"")
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            client.get_file("lib/util.py", 5)
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "svn"
        assert cmd[1] == "cat"
        assert f"{self._URL}/lib/util.py@5" in cmd

    def test_raises_on_non_zero_exit(self):
        client = SvnClient(self._URL, self._make_creds())
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "svn", stderr=b"not found")):
            with pytest.raises(SVNClientError, match="svn cat failed"):
                client.get_file("missing.py", 1)
