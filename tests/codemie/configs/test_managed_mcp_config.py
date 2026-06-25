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

from pathlib import Path

from codemie.configs.managed_mcp_config import (
    ManagedMcpServer,
    load_managed_mcp_servers,
)

SAMPLE_YAML = """
servers:
  - name: sample
    transport: http
    url: https://mcp.example.com/mcp/sample
    auth: oauth
    clients: [claude-desktop, codex]
  - name: globalmcp
    transport: http
    url: https://mcp.example.com/mcp/global
    auth: oauth
"""


def _write(dir_path: Path, text: str) -> Path:
    (dir_path / "managed-mcp-servers.yaml").write_text(text)
    return dir_path


def test_missing_file_returns_empty(tmp_path: Path):
    assert load_managed_mcp_servers(base_dir=tmp_path) == []


def test_loads_and_parses_entries(tmp_path: Path):
    _write(tmp_path, SAMPLE_YAML)
    servers = load_managed_mcp_servers(base_dir=tmp_path)
    assert [s.name for s in servers] == ["sample", "globalmcp"]
    assert servers[0].url == "https://mcp.example.com/mcp/sample"
    assert servers[0].auth == "oauth"


def test_skips_malformed_entries(tmp_path: Path):
    _write(
        tmp_path,
        "servers:\n  - {name: ok, transport: http, url: https://a}\n  - {name: bad, transport: ftp, url: https://b}\n",
    )
    servers = load_managed_mcp_servers(base_dir=tmp_path)
    assert [s.name for s in servers] == ["ok"]


def test_filters_by_client(tmp_path: Path):
    _write(tmp_path, SAMPLE_YAML)
    codex = load_managed_mcp_servers(client="codex", base_dir=tmp_path)
    assert {s.name for s in codex} == {"sample", "globalmcp"}
    _write(tmp_path, "servers:\n  - {name: only_cd, transport: http, url: https://x, clients: [claude-desktop]}\n")
    assert load_managed_mcp_servers(client="codex", base_dir=tmp_path) == []
    assert [s.name for s in load_managed_mcp_servers(client="claude-desktop", base_dir=tmp_path)] == ["only_cd"]


def test_corrupt_yaml_returns_empty(tmp_path: Path):
    _write(tmp_path, "servers: [unclosed")
    assert load_managed_mcp_servers(base_dir=tmp_path) == []


def test_returns_typed_models(tmp_path: Path):
    _write(tmp_path, SAMPLE_YAML)
    servers = load_managed_mcp_servers(base_dir=tmp_path)
    assert all(isinstance(s, ManagedMcpServer) for s in servers)


def test_path_is_directory_returns_empty(tmp_path: Path):
    # A directory at the catalog path raises IsADirectoryError (an OSError);
    # the loader must still return [] rather than propagate.
    (tmp_path / "managed-mcp-servers.yaml").mkdir()
    assert load_managed_mcp_servers(base_dir=tmp_path) == []


def test_non_dict_root_returns_empty(tmp_path: Path):
    _write(tmp_path, "just a string")
    assert load_managed_mcp_servers(base_dir=tmp_path) == []


def test_non_list_servers_returns_empty(tmp_path: Path):
    _write(tmp_path, "servers: not-a-list")
    assert load_managed_mcp_servers(base_dir=tmp_path) == []


def test_non_dict_entry_is_skipped(tmp_path: Path):
    _write(tmp_path, "servers:\n  - just-a-string\n  - {name: ok, transport: http, url: https://a}\n")
    servers = load_managed_mcp_servers(base_dir=tmp_path)
    assert [s.name for s in servers] == ["ok"]


def test_example_file_is_valid():
    from pathlib import Path

    import codemie

    repo_root = Path(codemie.__file__).resolve().parents[2]
    example = repo_root / "config" / "customer" / "managed-mcp-servers.example.yaml"
    assert example.exists(), f"example file missing at {example}"

    import yaml

    data = yaml.safe_load(example.read_text())
    assert isinstance(data, dict) and isinstance(data.get("servers"), list)
    for item in data["servers"]:
        ManagedMcpServer(**item)

    # The loader reads `managed-mcp-servers.yaml`, so the `.example.yaml` file
    # is documentation only and must NOT be picked up.
    servers = load_managed_mcp_servers(base_dir=example.parent)
    assert servers == []
