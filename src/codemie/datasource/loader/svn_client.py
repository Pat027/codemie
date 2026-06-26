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
import xml.etree.ElementTree as ElementTree

from codemie.rest_api.models.settings import SVNAuthType, SVNCredentials


class SVNClientError(RuntimeError):
    """Raised when an svn CLI command fails or returns unexpected output."""


class SvnClient:
    """Read-only SVN client backed by subprocess calls to the svn CLI with BASIC authentication."""

    def __init__(self, url: str, creds: SVNCredentials) -> None:
        """Initialise a client for *url* using *creds* for authentication."""
        self._url = url.rstrip("/")
        self._auth_flags = self._build_auth_flags(creds)

    @classmethod
    def svn_is_available(cls) -> bool:
        """Return True if the svn CLI is present on PATH."""
        return shutil.which("svn") is not None

    def get_latest_revnum(self) -> int:
        """Return the HEAD revision number of the repository."""
        try:
            result = subprocess.run(
                ["svn", "info", "--xml"] + self._auth_flags + ["--", self._url],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode(errors="replace")[:500]
            raise SVNClientError(f"svn info failed for {self._url} (exit {e.returncode}): {stderr}") from None

        root = ElementTree.fromstring(result.stdout)
        entry = root.find(".//entry")

        if entry is None:
            raise SVNClientError(f"svn info --xml returned no <entry> element for {self._url}")

        return int(entry.attrib["revision"])

    def get_dir(self, path: str, revision: int) -> dict[str, dict]:
        """List directory entries at *path*@*revision*; returns ``{name: {kind, size}}``."""
        target = self._target(path, revision)

        try:
            result = subprocess.run(
                ["svn", "list", "--xml"] + self._auth_flags + ["--", target],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode(errors="replace")[:500]
            raise SVNClientError(f"svn list failed for {target} (exit {e.returncode}): {stderr}") from None

        root = ElementTree.fromstring(result.stdout)
        entries = {}
        for entry in root.findall(".//entry"):
            name_el = entry.find("name")

            if name_el is None or not name_el.text:
                continue

            size_el = entry.find("size")
            entries[name_el.text] = {
                "kind": entry.attrib.get("kind", ""),
                "size": int(size_el.text) if size_el is not None and size_el.text else 0,
            }

        return entries

    def get_file(self, path: str, revision: int) -> bytes:
        """Return the raw bytes of *path*@*revision*."""
        try:
            result = subprocess.run(
                ["svn", "cat"] + self._auth_flags + ["--", self._target(path, revision)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode(errors="replace")[:500]
            raise SVNClientError(
                f"svn cat failed for {self._target(path, revision)} (exit {e.returncode}): {stderr}"
            ) from None

        return result.stdout

    @staticmethod
    def _build_auth_flags(creds: SVNCredentials) -> list[str]:
        """Build the CLI flags for authentication and SSL trust."""
        flags = ["--non-interactive", "--trust-server-cert", "--trust-server-cert-failures=unknown-ca"]

        if creds.auth_type == SVNAuthType.BASIC and creds.username:
            flags += ["--username", creds.username, "--password", creds.password or "", "--no-auth-cache"]

        return flags

    def _target(self, path: str, revision: int) -> str:
        """Build a pegged URL: ``<url>/<path>@<rev>`` or ``<url>@<rev>`` for root."""
        base = f"{self._url}/{path}" if path else self._url
        return f"{base}@{revision}"
