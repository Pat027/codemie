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
import io
import mimetypes
import os
import stat
import tempfile
from contextlib import contextmanager
from typing import Any, Iterator

import subvertpy.ra as svn_ra
from subvertpy import NODE_DIR, NODE_FILE
from subvertpy.ra import DIRENT_KIND, DIRENT_SIZE

from langchain_core.documents import Document

from codemie.configs import logger
from codemie.core.models import SVNRepo
from codemie.core.utils import check_file_type
from codemie.datasource.datasources_config import CODE_CONFIG, SVN_CONFIG
from codemie.datasource.loader.base_datasource_loader import BaseDatasourceLoader
from codemie.datasource.loader.file_extraction_utils import extract_documents_from_bytes, is_binary_extractable
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


def _ssl_server_trust_prompt(realm, failures, cert_info, may_save):
    return failures, False


def _build_remote_access(url: str, creds: SVNCredentials) -> svn_ra.RemoteAccess:
    """Create an authenticated subvertpy RemoteAccess connection."""
    providers = [svn_ra.get_ssl_server_trust_prompt_provider(_ssl_server_trust_prompt)]

    if creds.auth_type == SVNAuthType.BASIC and creds.username:
        username = creds.username
        password = creds.password or ""

        def simple_prompt(realm, uname, may_save):
            return username, password, False

        providers.append(svn_ra.get_simple_prompt_provider(simple_prompt, 0))

    auth = svn_ra.Auth(providers)
    return svn_ra.RemoteAccess(url, auth=auth)


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
        """Verify connectivity using subvertpy and return the HEAD revision."""
        branch_url = _build_branch_url(url.rstrip("/"), branch.strip("/"))
        with _svn_ssh_context(creds):
            conn = _build_remote_access(branch_url, creds)
            head_revision = conn.get_latest_revnum()
        return {cls.HEAD_REVISION_KEY: head_revision}

    # ------------------------------------------------------------------
    # BaseDatasourceLoader interface
    # ------------------------------------------------------------------

    def fetch_remote_stats(self) -> dict[str, Any]:
        """Verify connectivity using subvertpy and return HEAD revision."""
        with _svn_ssh_context(self._creds):
            conn = _build_remote_access(self._branch_url, self._creds)
            head_revision = conn.get_latest_revnum()
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
        """Fetch SVN repository contents in-memory and yield one Document per file."""
        with _svn_ssh_context(self._creds):
            conn = _build_remote_access(self._branch_url, self._creds)
            revision = conn.get_latest_revnum()
            yield from self._walk_remote(conn, "", revision, "")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _walk_remote(
        self,
        conn: svn_ra.RemoteAccess,
        remote_path: str,
        revision: int,
        rel_prefix: str,
    ) -> Iterator[Document]:
        dirents, _fetched_rev, _props = conn.get_dir(remote_path, revision, DIRENT_KIND | DIRENT_SIZE)
        for name, dirent in dirents.items():
            kind = dirent.get("kind")
            child_remote = f"{remote_path}/{name}" if remote_path else name
            child_rel = f"{rel_prefix}/{name}" if rel_prefix else name
            if kind == NODE_DIR:
                yield from self._walk_remote(conn, child_remote, revision, child_rel)
            elif kind == NODE_FILE:
                size_kb = (dirent.get("size") or 0) / 1024
                if not self._should_skip(child_rel, size_kb):
                    yield from self._fetch_and_process(conn, child_remote, revision, child_rel, name)

    def _fetch_and_process(
        self,
        conn: svn_ra.RemoteAccess,
        remote_path: str,
        revision: int,
        rel_path: str,
        fname: str,
    ) -> list[Document]:
        try:
            buf = io.BytesIO()
            conn.get_file(remote_path, buf, revision)
            content = buf.getvalue()
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
