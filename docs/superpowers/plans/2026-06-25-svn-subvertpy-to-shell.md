# SVN subvertpy → shell replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `subvertpy` C-extension with `subprocess` calls to the `svn` CLI, keeping `SVNBatchLoader`'s public interface identical.

**Architecture:** A new `svn_client.py` file encapsulates `svn_is_available()`, `_build_auth_flags()`, and the `SvnClient` class (three methods). `svn_loader.py` drops all `subvertpy` imports, removes `_build_remote_access`, and wires its three internal call-sites to `SvnClient`. Tests are updated to mock `subprocess.run` / `SvnClient` instead of `subvertpy.ra`.

**Tech Stack:** Python stdlib (`subprocess`, `shutil`, `xml.etree.ElementTree`), pytest, poetry.

---

### Task 1: `svn_client.py` — skeleton + `svn_is_available` + `_build_auth_flags` + `SvnClient` stub

**Files:**
- Create: `src/codemie/datasource/loader/svn_client.py`
- Create: `tests/codemie/datasource/loader/test_svn_client.py`

**Test-first: yes — `svn_is_available` returns True/False based on shutil.which; `_build_auth_flags` emits correct flags per auth type**

- [ ] **Step 1: Write the failing tests**

Create `tests/codemie/datasource/loader/test_svn_client.py`:

```python
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

from codemie.datasource.loader.svn_client import SvnClient, _build_auth_flags, svn_is_available
from codemie.rest_api.models.settings import SVNAuthType, SVNCredentials


class TestSvnIsAvailable:
    def test_returns_true_when_svn_on_path(self):
        with patch("codemie.datasource.loader.svn_client.shutil.which", return_value="/usr/bin/svn"):
            assert svn_is_available() is True

    def test_returns_false_when_svn_not_on_path(self):
        with patch("codemie.datasource.loader.svn_client.shutil.which", return_value=None):
            assert svn_is_available() is False


class TestBuildAuthFlags:
    def test_base_flags_always_present_for_ssh(self):
        creds = SVNCredentials(auth_type=SVNAuthType.SSH_KEY, ssh_key="key")
        flags = _build_auth_flags(creds)
        assert "--non-interactive" in flags
        assert "--trust-server-cert" in flags
        assert "--trust-server-cert-failures=unknown-ca" in flags

    def test_basic_auth_includes_username_password_no_cache(self):
        creds = SVNCredentials(auth_type=SVNAuthType.BASIC, username="alice", password="secret")
        flags = _build_auth_flags(creds)
        assert "--username" in flags
        assert "alice" in flags
        assert "--password" in flags
        assert "secret" in flags
        assert "--no-auth-cache" in flags

    def test_ssh_key_has_no_credential_flags(self):
        creds = SVNCredentials(auth_type=SVNAuthType.SSH_KEY, ssh_key="key")
        flags = _build_auth_flags(creds)
        assert "--username" not in flags
        assert "--password" not in flags
        assert "--no-auth-cache" not in flags

    def test_basic_auth_without_username_omits_credential_flags(self):
        creds = SVNCredentials(auth_type=SVNAuthType.BASIC, username=None, password=None)
        flags = _build_auth_flags(creds)
        assert "--username" not in flags
        assert "--password" not in flags
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
poetry run pytest tests/codemie/datasource/loader/test_svn_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'codemie.datasource.loader.svn_client'`

- [ ] **Step 3: Create `svn_client.py` with the two helpers and a `SvnClient` stub**

Create `src/codemie/datasource/loader/svn_client.py`:

```python
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

import shutil
import subprocess
import xml.etree.ElementTree as ET

from codemie.rest_api.models.settings import SVNAuthType, SVNCredentials


def svn_is_available() -> bool:
    return shutil.which("svn") is not None


def _build_auth_flags(creds: SVNCredentials) -> list[str]:
    flags = ["--non-interactive", "--trust-server-cert", "--trust-server-cert-failures=unknown-ca"]
    if creds.auth_type == SVNAuthType.BASIC and creds.username:
        flags += ["--username", creds.username, "--password", creds.password or "", "--no-auth-cache"]
    return flags


class SvnClient:
    def __init__(self, url: str, creds: SVNCredentials) -> None:
        self._url = url.rstrip("/")
        self._auth_flags = _build_auth_flags(creds)

    def _target(self, path: str, revision: int) -> str:
        base = f"{self._url}/{path}" if path else self._url
        return f"{base}@{revision}"

    def get_latest_revnum(self) -> int:
        raise NotImplementedError

    def get_dir(self, path: str, revision: int) -> dict[str, dict]:
        raise NotImplementedError

    def get_file(self, path: str, revision: int) -> bytes:
        raise NotImplementedError
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
poetry run pytest tests/codemie/datasource/loader/test_svn_client.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/codemie/datasource/loader/svn_client.py tests/codemie/datasource/loader/test_svn_client.py
git commit -m "EPMCDME-13166: Add svn_client.py with svn_is_available, _build_auth_flags, and SvnClient skeleton"
```

---

### Task 2: `SvnClient.get_latest_revnum`

**Files:**
- Modify: `src/codemie/datasource/loader/svn_client.py`
- Modify: `tests/codemie/datasource/loader/test_svn_client.py`

**Test-first: yes — parses `entry[@revision]` from `svn info --xml` stdout; raises on non-zero exit**

- [ ] **Step 1: Add the failing tests**

Append to `test_svn_client.py` (after the `TestBuildAuthFlags` class):

```python
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
        with patch("subprocess.run", return_value=mock_result) as mock_run:
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
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "svn")):
            with pytest.raises(subprocess.CalledProcessError):
                client.get_latest_revnum()
```

- [ ] **Step 2: Run tests to confirm the new ones fail**

```bash
poetry run pytest tests/codemie/datasource/loader/test_svn_client.py::TestSvnClientGetLatestRevnum -v
```

Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement `get_latest_revnum`**

Replace the `get_latest_revnum` stub in `svn_client.py`:

```python
def get_latest_revnum(self) -> int:
    result = subprocess.run(
        ["svn", "info", "--xml", self._url] + self._auth_flags,
        check=True,
        capture_output=True,
    )
    root = ET.fromstring(result.stdout)
    return int(root.find(".//entry").attrib["revision"])
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
poetry run pytest tests/codemie/datasource/loader/test_svn_client.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/codemie/datasource/loader/svn_client.py tests/codemie/datasource/loader/test_svn_client.py
git commit -m "EPMCDME-13166: Implement SvnClient.get_latest_revnum"
```

---

### Task 3: `SvnClient.get_dir`

**Files:**
- Modify: `src/codemie/datasource/loader/svn_client.py`
- Modify: `tests/codemie/datasource/loader/test_svn_client.py`

**Test-first: yes — parses `<entry>` nodes from `svn list --xml` stdout; handles empty dirs; raises on failure**

- [ ] **Step 1: Add the failing tests**

Append to `test_svn_client.py`:

```python
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
        xml = self._list_xml([
            {"kind": "file", "name": "README.md", "size": 1024},
            {"kind": "dir", "name": "src", "size": 0},
        ])
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
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "svn")):
            with pytest.raises(subprocess.CalledProcessError):
                client.get_dir("", 1)
```

- [ ] **Step 2: Run tests to confirm the new ones fail**

```bash
poetry run pytest tests/codemie/datasource/loader/test_svn_client.py::TestSvnClientGetDir -v
```

Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement `get_dir`**

Replace the `get_dir` stub in `svn_client.py`:

```python
def get_dir(self, path: str, revision: int) -> dict[str, dict]:
    result = subprocess.run(
        ["svn", "list", "--xml", self._target(path, revision)] + self._auth_flags,
        check=True,
        capture_output=True,
    )
    root = ET.fromstring(result.stdout)
    entries = {}
    for entry in root.findall(".//entry"):
        name_el = entry.find("name")
        size_el = entry.find("size")
        entries[name_el.text] = {
            "kind": entry.attrib.get("kind", ""),
            "size": int(size_el.text) if size_el is not None and size_el.text else 0,
        }
    return entries
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
poetry run pytest tests/codemie/datasource/loader/test_svn_client.py -v
```

Expected: all 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/codemie/datasource/loader/svn_client.py tests/codemie/datasource/loader/test_svn_client.py
git commit -m "EPMCDME-13166: Implement SvnClient.get_dir"
```

---

### Task 4: `SvnClient.get_file`

**Files:**
- Modify: `src/codemie/datasource/loader/svn_client.py`
- Modify: `tests/codemie/datasource/loader/test_svn_client.py`

**Test-first: yes — returns raw stdout bytes from `svn cat`; raises on non-zero exit**

- [ ] **Step 1: Add the failing tests**

Append to `test_svn_client.py`:

```python
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
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "svn")):
            with pytest.raises(subprocess.CalledProcessError):
                client.get_file("missing.py", 1)
```

- [ ] **Step 2: Run tests to confirm the new ones fail**

```bash
poetry run pytest tests/codemie/datasource/loader/test_svn_client.py::TestSvnClientGetFile -v
```

Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement `get_file`**

Replace the `get_file` stub in `svn_client.py`:

```python
def get_file(self, path: str, revision: int) -> bytes:
    result = subprocess.run(
        ["svn", "cat", self._target(path, revision)] + self._auth_flags,
        check=True,
        capture_output=True,
    )
    return result.stdout
```

- [ ] **Step 4: Run all svn_client tests**

```bash
poetry run pytest tests/codemie/datasource/loader/test_svn_client.py -v
```

Expected: all 17 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/codemie/datasource/loader/svn_client.py tests/codemie/datasource/loader/test_svn_client.py
git commit -m "EPMCDME-13166: Implement SvnClient.get_file"
```

---

### Task 5: Wire `svn_loader.py` to `SvnClient`; update loader tests

**Files:**
- Modify: `src/codemie/datasource/loader/svn_loader.py`
- Modify: `tests/codemie/datasource/loader/test_svn_loader.py`

**Test-first: yes — new guard tests fail first (RuntimeError when svn not available); adapted existing tests go RED until loader is updated**

- [ ] **Step 1: Update `test_svn_loader.py`**

Replace the entire content of `tests/codemie/datasource/loader/test_svn_loader.py` with:

```python
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

"""Tests for SVNBatchLoader."""

import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from codemie.datasource.loader.svn_loader import SVNBatchLoader, _build_branch_url, _svn_ssh_context
from codemie.rest_api.models.settings import SVNAuthType, SVNCredentials


# --- _build_branch_url ---


@pytest.mark.parametrize(
    "base_url,branch,expected",
    [
        (
            "https://svn.example.com/repos/myproject",
            "trunk",
            "https://svn.example.com/repos/myproject/trunk",
        ),
        (
            "https://svn.example.com/repos/myproject/",
            "trunk",
            "https://svn.example.com/repos/myproject/trunk",
        ),
        (
            "https://svn.example.com/repos",
            "branches/feature-x",
            "https://svn.example.com/repos/branches/feature-x",
        ),
        (
            "https://svn.example.com/repos",
            "custom",
            "https://svn.example.com/repos/custom",
        ),
        (
            "https://svn.example.com/repos",
            "/trunk/",
            "https://svn.example.com/repos/trunk",
        ),
    ],
)
def test_build_branch_url(base_url, branch, expected):
    assert _build_branch_url(base_url, branch) == expected


# --- _svn_ssh_context ---


class TestSvnSshContext:
    def test_non_ssh_creds_does_not_modify_svn_ssh_env(self):
        creds = SVNCredentials(auth_type=SVNAuthType.BASIC, username="u", password="p")
        original = os.environ.get("SVN_SSH")
        with _svn_ssh_context(creds):
            assert os.environ.get("SVN_SSH") == original

    def test_ssh_key_creds_sets_svn_ssh_env(self):
        creds = SVNCredentials(auth_type=SVNAuthType.SSH_KEY, ssh_key="my_key")
        with _svn_ssh_context(creds):
            assert "SVN_SSH" in os.environ
            assert "ssh" in os.environ["SVN_SSH"]
            assert "StrictHostKeyChecking=no" in os.environ["SVN_SSH"]
            assert "BatchMode=yes" in os.environ["SVN_SSH"]

    def test_svn_ssh_env_restored_after_context(self):
        original = os.environ.get("SVN_SSH")
        creds = SVNCredentials(auth_type=SVNAuthType.SSH_KEY, ssh_key="my_key")
        with _svn_ssh_context(creds):
            pass
        assert os.environ.get("SVN_SSH") == original

    def test_ssh_key_temp_file_deleted_after_context(self, tmp_path):
        creds = SVNCredentials(auth_type=SVNAuthType.SSH_KEY, ssh_key="my_key")
        captured_path = []
        original_mkstemp = __import__("tempfile").mkstemp

        def capturing_mkstemp(*args, **kwargs):
            fd, path = original_mkstemp(*args, **kwargs)
            captured_path.append(path)
            return fd, path

        with patch("codemie.datasource.loader.svn_loader.tempfile.mkstemp", side_effect=capturing_mkstemp):
            with _svn_ssh_context(creds):
                pass

        assert captured_path, "mkstemp was not called"
        assert not os.path.exists(captured_path[0])

    def test_no_ssh_key_value_does_not_set_svn_ssh(self):
        creds = SVNCredentials(auth_type=SVNAuthType.SSH_KEY, ssh_key=None)
        original = os.environ.get("SVN_SSH")
        with _svn_ssh_context(creds):
            assert os.environ.get("SVN_SSH") == original


# --- _is_unsupported_mime_type ---


class TestIsUnsupportedMimeType:
    def test_python_file_is_supported(self):
        assert SVNBatchLoader._is_unsupported_mime_type("script.py") is False

    def test_text_file_is_supported(self):
        assert SVNBatchLoader._is_unsupported_mime_type("readme.txt") is False

    def test_unknown_extension_is_supported(self):
        assert not SVNBatchLoader._is_unsupported_mime_type("file.unknown123")

    def test_pdf_is_supported_via_binary_extractable(self):
        assert SVNBatchLoader._is_unsupported_mime_type("document.pdf") is False

    def test_jpg_is_supported_via_binary_extractable(self):
        assert SVNBatchLoader._is_unsupported_mime_type("photo.jpg") is False

    def test_docx_is_supported_via_binary_extractable(self):
        assert SVNBatchLoader._is_unsupported_mime_type("report.docx") is False

    def test_mp4_video_is_unsupported(self):
        assert SVNBatchLoader._is_unsupported_mime_type("video.mp4") is True

    def test_mp3_is_supported_binary_extractable(self):
        assert SVNBatchLoader._is_unsupported_mime_type("audio.mp3") is False

    def test_tar_archive_is_unsupported(self):
        assert SVNBatchLoader._is_unsupported_mime_type("archive.tar") is True

    def test_rar_archive_is_unsupported(self):
        assert SVNBatchLoader._is_unsupported_mime_type("archive.rar") is True


# --- _decode_content ---


class TestDecodeContent:
    def test_valid_utf8_content_returns_string(self):
        content = "hello world".encode("utf-8")
        result = SVNBatchLoader._decode_content(content, "test.txt")
        assert result == "hello world"

    def test_utf8_with_invalid_bytes_uses_backslashreplace(self):
        content = b"valid \xff bytes"
        result = SVNBatchLoader._decode_content(content, "test.bin")
        assert result is not None
        assert isinstance(result, str)
        assert "valid" in result

    def test_empty_content_returns_empty_string(self):
        result = SVNBatchLoader._decode_content(b"", "empty.txt")
        assert result == ""


# --- Fixtures ---


@pytest.fixture
def basic_creds():
    return SVNCredentials(auth_type=SVNAuthType.BASIC, username="user", password="pass")


@pytest.fixture
def svn_repo_mock():
    repo = MagicMock()
    repo.link = "https://svn.example.com/repos/test"
    repo.branch = "trunk"
    repo.files_filter = ""
    return repo


@pytest.fixture
def loader(svn_repo_mock, basic_creds):
    return SVNBatchLoader(
        svn_repo=svn_repo_mock,
        creds=basic_creds,
        request_uuid="test-uuid",
        datasource_id="ds-123",
    )


# --- _should_skip ---


class TestShouldSkip:
    def test_oversized_file_is_skipped(self, loader):
        with patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg:
            mock_cfg.max_file_size_kb = 5000
            assert loader._should_skip("bigfile.dat", 5001) is True

    def test_file_within_size_limit_is_not_skipped(self, loader):
        with (
            patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg,
            patch("codemie.datasource.loader.svn_loader.check_file_type", return_value=True),
        ):
            mock_cfg.max_file_size_kb = 5000
            assert loader._should_skip("main.py", 1.0) is False

    def test_unsupported_mime_type_is_skipped(self, loader):
        with patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg:
            mock_cfg.max_file_size_kb = 5000
            assert loader._should_skip("clip.mp4", 100) is True

    def test_filtered_out_file_is_skipped(self, loader):
        with (
            patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg,
            patch("codemie.datasource.loader.svn_loader.check_file_type", return_value=False),
        ):
            mock_cfg.max_file_size_kb = 5000
            assert loader._should_skip("code.py", 10) is True

    def test_zero_size_file_is_not_skipped_by_size(self, loader):
        with (
            patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg,
            patch("codemie.datasource.loader.svn_loader.check_file_type", return_value=True),
        ):
            mock_cfg.max_file_size_kb = 5000
            assert loader._should_skip("empty.py", 0) is False


# --- _process_content ---


class TestProcessContent:
    def test_text_file_returns_document_with_correct_content(self, loader):
        docs = loader._process_content(b"def hello(): pass", "src/module.py", "module.py")
        assert len(docs) == 1
        assert docs[0].page_content == "def hello(): pass"

    def test_text_file_document_has_correct_metadata(self, loader):
        docs = loader._process_content(b"x = 1", "lib/util.py", "util.py")
        assert docs[0].metadata["source"] == "lib/util.py"
        assert docs[0].metadata["file_path"] == "lib/util.py"
        assert docs[0].metadata["file_name"] == "util.py"
        assert docs[0].metadata["file_type"] == ".py"

    def test_decode_returns_none_yields_empty_list(self, loader):
        with patch.object(SVNBatchLoader, "_decode_content", return_value=None):
            docs = loader._process_content(b"data", "bad.txt", "bad.txt")
        assert docs == []

    @patch("codemie.datasource.loader.svn_loader.extract_documents_from_bytes")
    def test_pdf_file_routes_to_binary_extraction(self, mock_extract, loader):
        mock_extract.return_value = [Document(page_content="pdf text", metadata={})]
        docs = loader._process_content(b"%PDF-1.4 content", "docs/doc.pdf", "doc.pdf")
        mock_extract.assert_called_once()
        assert len(docs) == 1


# --- _process_binary_file ---


class TestProcessBinaryFile:
    @patch("codemie.datasource.loader.svn_loader.extract_documents_from_bytes")
    def test_sets_correct_metadata_for_pdf(self, mock_extract, loader):
        raw_doc = Document(page_content="extracted text", metadata={"source": "/tmp/tmpXXX.pdf"})
        mock_extract.return_value = [raw_doc]
        result = loader._process_binary_file(b"%PDF-1.4", "sub/report.pdf", "report.pdf")
        assert len(result) == 1
        assert result[0].metadata["source"] == "sub/report.pdf"
        assert result[0].metadata["file_path"] == "sub/report.pdf"
        assert result[0].metadata["file_name"] == "report.pdf"
        assert result[0].metadata["file_type"] == ".pdf"

    @patch("codemie.datasource.loader.svn_loader.extract_documents_from_bytes")
    def test_extractor_returns_empty_list(self, mock_extract, loader):
        mock_extract.return_value = []
        assert loader._process_binary_file(b"data", "f.docx", "f.docx") == []

    @patch("codemie.datasource.loader.svn_loader.extract_documents_from_bytes")
    def test_passes_correct_args_to_extractor(self, mock_extract, loader):
        mock_extract.return_value = []
        loader._process_binary_file(b"bytes", "sub/doc.docx", "doc.docx")
        mock_extract.assert_called_once_with(
            file_bytes=b"bytes",
            file_name="doc.docx",
            request_uuid="test-uuid",
            datasource_id="ds-123",
        )

    @patch("codemie.datasource.loader.svn_loader.extract_documents_from_bytes", side_effect=Exception("parse error"))
    def test_exception_returns_empty_list(self, mock_extract, loader):
        result = loader._process_binary_file(b"bad data", "broken.pdf", "broken.pdf")
        assert result == []


# --- test_connection ---


class TestTestConnection:
    def test_connection_success_returns_head_revision(self, basic_creds):
        mock_client = MagicMock()
        mock_client.get_latest_revnum.return_value = 100
        with (
            patch("codemie.datasource.loader.svn_loader.svn_is_available", return_value=True),
            patch("codemie.datasource.loader.svn_loader.SvnClient", return_value=mock_client),
        ):
            result = SVNBatchLoader.test_connection("https://svn.example.com/repos/test", "trunk", basic_creds)
        assert result[SVNBatchLoader.HEAD_REVISION_KEY] == 100

    def test_connection_failure_propagates_exception(self, basic_creds):
        mock_client = MagicMock()
        mock_client.get_latest_revnum.side_effect = Exception("Connection refused")
        with (
            patch("codemie.datasource.loader.svn_loader.svn_is_available", return_value=True),
            patch("codemie.datasource.loader.svn_loader.SvnClient", return_value=mock_client),
            pytest.raises(Exception, match="Connection refused"),
        ):
            SVNBatchLoader.test_connection("https://svn.example.com/repos/test", "trunk", basic_creds)

    def test_connection_uses_branch_url(self, basic_creds):
        mock_client = MagicMock()
        mock_client.get_latest_revnum.return_value = 1
        with (
            patch("codemie.datasource.loader.svn_loader.svn_is_available", return_value=True),
            patch("codemie.datasource.loader.svn_loader.SvnClient", return_value=mock_client) as mock_cls,
        ):
            SVNBatchLoader.test_connection("https://svn.example.com/repos/test", "trunk", basic_creds)
        mock_cls.assert_called_once_with("https://svn.example.com/repos/test/trunk", basic_creds)

    def test_raises_runtime_error_when_svn_not_available(self, basic_creds):
        with (
            patch("codemie.datasource.loader.svn_loader.svn_is_available", return_value=False),
            pytest.raises(RuntimeError, match="svn CLI is not installed"),
        ):
            SVNBatchLoader.test_connection("https://svn.example.com/repos/test", "trunk", basic_creds)


# --- fetch_remote_stats ---


class TestFetchRemoteStats:
    def test_returns_head_revision(self, loader):
        mock_client = MagicMock()
        mock_client.get_latest_revnum.return_value = 55
        with (
            patch("codemie.datasource.loader.svn_loader.svn_is_available", return_value=True),
            patch("codemie.datasource.loader.svn_loader.SvnClient", return_value=mock_client),
        ):
            result = loader.fetch_remote_stats()
        assert result[SVNBatchLoader.HEAD_REVISION_KEY] == 55

    def test_raises_on_svn_error(self, loader):
        mock_client = MagicMock()
        mock_client.get_latest_revnum.side_effect = Exception("Connection refused")
        with (
            patch("codemie.datasource.loader.svn_loader.svn_is_available", return_value=True),
            patch("codemie.datasource.loader.svn_loader.SvnClient", return_value=mock_client),
            pytest.raises(Exception, match="Connection refused"),
        ):
            loader.fetch_remote_stats()

    def test_documents_count_is_zero(self, loader):
        mock_client = MagicMock()
        mock_client.get_latest_revnum.return_value = 1
        with (
            patch("codemie.datasource.loader.svn_loader.svn_is_available", return_value=True),
            patch("codemie.datasource.loader.svn_loader.SvnClient", return_value=mock_client),
        ):
            result = loader.fetch_remote_stats()
        assert result[SVNBatchLoader.DOCUMENTS_COUNT_KEY] == 0

    def test_raises_runtime_error_when_svn_not_available(self, loader):
        with (
            patch("codemie.datasource.loader.svn_loader.svn_is_available", return_value=False),
            pytest.raises(RuntimeError, match="svn CLI is not installed"),
        ):
            loader.fetch_remote_stats()


# --- get_load_stats ---


class TestGetLoadStats:
    def test_initial_stats_are_zero(self, loader):
        stats = loader.get_load_stats()
        assert stats[SVNBatchLoader.SKIPPED_DOCUMENTS_KEY] == 0
        assert stats[SVNBatchLoader.FAILED_DOCUMENTS_KEY] == 0

    def test_skipped_count_increments_for_oversized_file(self, loader):
        with patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg:
            mock_cfg.max_file_size_kb = 100
            loader._should_skip("big.dat", 200)
        assert loader.get_load_stats()[SVNBatchLoader.SKIPPED_DOCUMENTS_KEY] == 1

    def test_skipped_count_increments_for_unsupported_mime(self, loader):
        with patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg:
            mock_cfg.max_file_size_kb = 5000
            loader._should_skip("video.mp4", 10)
        assert loader.get_load_stats()[SVNBatchLoader.SKIPPED_DOCUMENTS_KEY] == 1

    def test_skipped_count_increments_for_filtered_file(self, loader):
        with (
            patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg,
            patch("codemie.datasource.loader.svn_loader.check_file_type", return_value=False),
        ):
            mock_cfg.max_file_size_kb = 5000
            loader._should_skip("excluded.py", 1)
        assert loader.get_load_stats()[SVNBatchLoader.SKIPPED_DOCUMENTS_KEY] == 1

    def test_failed_count_increments_on_fetch_error(self, loader):
        mock_client = MagicMock()
        mock_client.get_file.side_effect = Exception("SVN error")
        loader._fetch_and_process(mock_client, "path/file.py", 1, "file.py", "file.py")
        assert loader.get_load_stats()[SVNBatchLoader.FAILED_DOCUMENTS_KEY] == 1

    def test_accumulates_multiple_skips_and_failures(self, loader):
        with patch("codemie.datasource.loader.svn_loader.SVN_CONFIG") as mock_cfg:
            mock_cfg.max_file_size_kb = 100
            loader._should_skip("a.dat", 200)
            loader._should_skip("b.dat", 300)
        mock_client = MagicMock()
        mock_client.get_file.side_effect = Exception("err")
        loader._fetch_and_process(mock_client, "c.py", 1, "c.py", "c.py")
        stats = loader.get_load_stats()
        assert stats[SVNBatchLoader.SKIPPED_DOCUMENTS_KEY] == 2
        assert stats[SVNBatchLoader.FAILED_DOCUMENTS_KEY] == 1

    def test_lazy_load_raises_runtime_error_when_svn_not_available(self, loader):
        with (
            patch("codemie.datasource.loader.svn_loader.svn_is_available", return_value=False),
            pytest.raises(RuntimeError, match="svn CLI is not installed"),
        ):
            list(loader.lazy_load())
```

- [ ] **Step 2: Run loader tests to confirm failures**

```bash
poetry run pytest tests/codemie/datasource/loader/test_svn_loader.py -v
```

Expected: guard tests FAIL (`svn_is_available` not imported in svn_loader yet); adapted mock tests FAIL (patching non-existent `SvnClient` in svn_loader).

- [ ] **Step 3: Rewrite `svn_loader.py`**

Replace the entire content of `src/codemie/datasource/loader/svn_loader.py` with:

```python
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

import contextlib
import mimetypes
import os
import stat
import tempfile
from contextlib import contextmanager
from typing import Any, Iterator

from langchain_core.documents import Document

from codemie.configs import logger
from codemie.core.models import SVNRepo
from codemie.core.utils import check_file_type
from codemie.datasource.datasources_config import CODE_CONFIG, SVN_CONFIG
from codemie.datasource.loader.base_datasource_loader import BaseDatasourceLoader
from codemie.datasource.loader.file_extraction_utils import extract_documents_from_bytes, is_binary_extractable
from codemie.datasource.loader.svn_client import SvnClient, svn_is_available
from codemie.rest_api.models.settings import SVNAuthType, SVNCredentials

# Reuse the same MIME exclusion list as the Git loader
from codemie.datasource.loader.git_loader import excluded_mime_types


def _build_branch_url(base_url: str, branch: str) -> str:
    """Construct the full SVN branch URL.

    trunk → <base>/trunk
    branches/feature-x → <base>/branches/feature-x
    any other value → <base>/<branch>
    """
    base_url = base_url.strip().rstrip("/")
    branch = branch.strip().strip("/")
    return f"{base_url}/{branch}"


@contextmanager
def _svn_ssh_context(creds: SVNCredentials):
    """Context manager for SSH key auth: writes key to a temp file and sets SVN_SSH."""
    if creds.auth_type != SVNAuthType.SSH_KEY or not creds.ssh_key:
        yield
        return

    fd, tmp_key_path = tempfile.mkstemp(prefix="svn_key_", suffix=".pem")
    fd_open = True
    try:
        os.write(fd, creds.ssh_key.encode())
        os.close(fd)
        fd_open = False
        os.chmod(tmp_key_path, stat.S_IRUSR | stat.S_IWUSR)

        ssh_cmd = f"ssh -i {tmp_key_path} -o StrictHostKeyChecking=no -o BatchMode=yes"
        old_svn_ssh = os.environ.get("SVN_SSH")
        os.environ["SVN_SSH"] = ssh_cmd
        try:
            yield
        finally:
            if old_svn_ssh is None:
                os.environ.pop("SVN_SSH", None)
            else:
                os.environ["SVN_SSH"] = old_svn_ssh
    finally:
        if fd_open:
            os.close(fd)
        with contextlib.suppress(OSError):
            os.remove(tmp_key_path)


class SVNBatchLoader(BaseDatasourceLoader):
    FILTERED_DOCUMENTS_KEY = "filtered_documents"
    TOTAL_SIZE_KB_KEY = "total_size_kb"
    HEAD_REVISION_KEY = "head_revision"

    def __init__(
        self,
        svn_repo: SVNRepo,
        creds: SVNCredentials,
        request_uuid: str | None = None,
        datasource_id: str = "",
    ):
        self._repo = svn_repo
        self._creds = creds
        self._request_uuid = request_uuid
        self._datasource_id = datasource_id
        self._branch_url = _build_branch_url(svn_repo.link, svn_repo.branch)
        self._skipped_count = 0
        self._failed_count = 0

    @classmethod
    def create_loader(
        cls,
        svn_repo: SVNRepo,
        creds: SVNCredentials,
        request_uuid: str | None = None,
        datasource_id: str = "",
    ) -> "SVNBatchLoader":
        return cls(
            svn_repo=svn_repo,
            creds=creds,
            request_uuid=request_uuid,
            datasource_id=datasource_id,
        )

    @classmethod
    def test_connection(cls, url: str, branch: str, creds: SVNCredentials) -> dict[str, Any]:
        """Verify connectivity using the svn CLI and return the HEAD revision."""
        if not svn_is_available():
            raise RuntimeError("svn CLI is not installed or not on PATH")
        branch_url = _build_branch_url(url.rstrip("/"), branch.strip("/"))
        with _svn_ssh_context(creds):
            head_revision = SvnClient(branch_url, creds).get_latest_revnum()
        return {cls.HEAD_REVISION_KEY: head_revision}

    # ------------------------------------------------------------------
    # BaseDatasourceLoader interface
    # ------------------------------------------------------------------

    def fetch_remote_stats(self) -> dict[str, Any]:
        """Verify connectivity using the svn CLI and return HEAD revision."""
        if not svn_is_available():
            raise RuntimeError("svn CLI is not installed or not on PATH")
        with _svn_ssh_context(self._creds):
            head_revision = SvnClient(self._branch_url, self._creds).get_latest_revnum()
        logger.info(f"SVN HEAD revision for {self._branch_url}: {head_revision}")
        return {
            self.DOCUMENTS_COUNT_KEY: 0,
            self.HEAD_REVISION_KEY: head_revision,
        }

    def get_load_stats(self) -> dict[str, Any]:
        return {
            self.SKIPPED_DOCUMENTS_KEY: self._skipped_count,
            self.FAILED_DOCUMENTS_KEY: self._failed_count,
        }

    def lazy_load(self) -> Iterator[Document]:
        """Fetch SVN repository contents via svn CLI and yield one Document per file."""
        if not svn_is_available():
            raise RuntimeError("svn CLI is not installed or not on PATH")
        with _svn_ssh_context(self._creds):
            client = SvnClient(self._branch_url, self._creds)
            revision = client.get_latest_revnum()
            yield from self._walk_remote(client, "", revision, "")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _walk_remote(
        self,
        client: SvnClient,
        remote_path: str,
        revision: int,
        rel_prefix: str,
    ) -> Iterator[Document]:
        dirents = client.get_dir(remote_path, revision)
        for name, dirent in dirents.items():
            kind = dirent.get("kind")
            child_remote = f"{remote_path}/{name}" if remote_path else name
            child_rel = f"{rel_prefix}/{name}" if rel_prefix else name
            if kind == "dir":
                yield from self._walk_remote(client, child_remote, revision, child_rel)
            elif kind == "file":
                size_kb = (dirent.get("size") or 0) / 1024
                if not self._should_skip(child_rel, size_kb):
                    yield from self._fetch_and_process(client, child_remote, revision, child_rel, name)

    def _fetch_and_process(
        self,
        client: SvnClient,
        remote_path: str,
        revision: int,
        rel_path: str,
        fname: str,
    ) -> list[Document]:
        try:
            content = client.get_file(remote_path, revision)
            return self._process_content(content, rel_path, fname)
        except Exception:
            logger.error(f"Error fetching SVN file {remote_path}", exc_info=True)
            self._failed_count += 1
            return []

    def _should_skip(self, rel_path: str, size_kb: float) -> bool:
        if size_kb > SVN_CONFIG.max_file_size_kb:
            logger.debug(f"Skip oversized file ({size_kb:.0f} KB): {rel_path}")
            self._skipped_count += 1
            return True

        if self._is_unsupported_mime_type(rel_path):
            logger.debug(f"Skip unsupported MIME type: {rel_path}")
            self._skipped_count += 1
            return True

        if not check_file_type(
            file_name=rel_path,
            files_filter=self._repo.files_filter,
            repo_local_path="",
            excluded_files=CODE_CONFIG.excluded_extensions.get_full_code_exclusions(),
        ):
            logger.debug(f"Skip filtered file: {rel_path}")
            self._skipped_count += 1
            return True

        return False

    @staticmethod
    def _is_unsupported_mime_type(path: str) -> bool:
        if is_binary_extractable(path):
            return False
        mime_type, _ = mimetypes.guess_type(path, strict=False)
        return mime_type in excluded_mime_types or (
            mime_type and mime_type.startswith(("image", "video", "audio", "application/vnd", "application/x-font"))
        )

    def _process_content(self, content: bytes, rel_path: str, fname: str) -> list[Document]:
        if is_binary_extractable(fname):
            return self._process_binary_file(content, rel_path, fname)

        ext = os.path.splitext(fname)[1].lower()
        text = self._decode_content(content, rel_path)
        if text is None:
            return []

        metadata = {
            "source": rel_path,
            "file_path": rel_path,
            "file_name": fname,
            "file_type": ext,
        }
        return [Document(page_content=text, metadata=metadata)]

    def _process_binary_file(self, content: bytes, rel_path: str, fname: str) -> list[Document]:
        try:
            docs = extract_documents_from_bytes(
                file_bytes=content,
                file_name=fname,
                request_uuid=self._request_uuid,
                datasource_id=self._datasource_id,
            )
            for doc in docs:
                doc.metadata["source"] = rel_path
                doc.metadata["file_path"] = rel_path
                doc.metadata["file_name"] = fname
                doc.metadata["file_type"] = os.path.splitext(fname)[1].lower()
            return docs
        except Exception as exc:
            logger.warning(
                f"Failed to extract binary SVN file {rel_path} ({type(exc).__name__}): {exc}",
                exc_info=True,
            )
            return []

    @staticmethod
    def _decode_content(content: bytes, path: str) -> str | None:
        try:
            return content.decode("utf-8", errors="backslashreplace")
        except UnicodeDecodeError:
            logger.error(f"UTF-8 decode error for {path}, retrying with latin-1", exc_info=True)
            try:
                return content.decode("latin-1")
            except UnicodeDecodeError:
                logger.error(f"latin-1 decode error for {path}", exc_info=True)
                return None
```

- [ ] **Step 4: Run loader tests**

```bash
poetry run pytest tests/codemie/datasource/loader/test_svn_loader.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Run the full test suite and lint**

```bash
make ruff && make test
```

Expected: ruff clean, all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/codemie/datasource/loader/svn_loader.py tests/codemie/datasource/loader/test_svn_loader.py
git commit -m "EPMCDME-13166: Replace subvertpy with SvnClient in svn_loader.py"
```

---

### Task 6: Remove `subvertpy` from `pyproject.toml`

**Files:**
- Modify: `pyproject.toml`

**Test-first: no — dependency and lock-file change; verified by `make build` + `make test`**

- [ ] **Step 1: Remove the `subvertpy` dependency line**

In `pyproject.toml` at line 162, delete:

```toml
subvertpy = ">=0.11"
```

- [ ] **Step 2: Remove the `subvertpy` license-allowlist entry**

In `pyproject.toml` at line 265, delete:

```toml
    "subvertpy" # GPLv2+; SVN client library required for SVN datasource support
```

- [ ] **Step 3: Regenerate the lock file**

```bash
poetry lock --no-update
```

Expected: `poetry.lock` updated (subvertpy entry removed).

- [ ] **Step 4: Verify the build and tests still pass**

```bash
make build && make test
```

Expected: package builds cleanly; all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml poetry.lock
git commit -m "EPMCDME-13166: Remove subvertpy dependency from pyproject.toml"
```
