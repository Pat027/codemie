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

"""
Loader for the client-neutral managed MCP server catalog.

The catalog file (`managed-mcp-servers.yaml`) is NOT committed to this
repository — it is supplied per deployment as a key in the
`codemie-customer-config` ConfigMap, mounted at `CUSTOMER_CONFIG_DIR`. This
loader is intentionally resilient: a missing or malformed file yields an empty
list rather than raising, so the endpoint degrades to "no managed MCPs".
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from codemie.configs.config import config
from codemie.configs.logger import logger

MANAGED_MCP_FILENAME = "managed-mcp-servers.yaml"


class ManagedMcpServer(BaseModel):
    """A client-neutral managed MCP server entry. Remote-only in v1."""

    name: str
    transport: Literal["http", "sse"]
    url: str
    auth: Literal["oauth", "none"] = "none"
    description: Optional[str] = None
    clients: Optional[List[str]] = None

    model_config = ConfigDict(extra="ignore")


def load_managed_mcp_servers(
    client: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> List[ManagedMcpServer]:
    """
    Load managed MCP servers from the customer ConfigMap directory.

    Args:
        client: optional client id; entries are kept when they have no
            `clients` targeting (apply to all) or include this client.
        base_dir: override the config directory (defaults to CUSTOMER_CONFIG_DIR).

    Returns:
        Validated entries; never raises (missing/corrupt file -> []).
    """
    directory = Path(base_dir) if base_dir is not None else Path(config.CUSTOMER_CONFIG_DIR)
    path = directory / MANAGED_MCP_FILENAME
    if not path.exists():
        return []

    try:
        data = yaml.safe_load(path.read_text())
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
        # Resilience contract: a missing/unreadable/corrupt file degrades to
        # "no managed MCPs" rather than raising. OSError covers Permission/
        # IsADirectory/TOCTOU-FileNotFound; UnicodeDecodeError covers binary
        # content (it is a ValueError subclass, not an OSError subclass).
        logger.warning(f"Failed to read/parse {MANAGED_MCP_FILENAME}: {exc}")
        return []

    raw = data.get("servers", []) if isinstance(data, dict) else []
    if not isinstance(raw, list):
        return []

    servers: List[ManagedMcpServer] = []
    for item in raw:
        try:
            servers.append(ManagedMcpServer(**item))
        except (ValidationError, TypeError) as exc:
            # v1 entries carry no secrets/tokens, so logging the raw entry is
            # safe. Revisit if a credential-bearing field is ever added.
            logger.warning(f"Skipping invalid managed MCP entry {item!r}: {exc}")

    if client:
        # `not s.clients` covers both None (no targeting) and [] — both mean
        # "applies to all clients" by design.
        servers = [s for s in servers if not s.clients or client in s.clients]
    return servers
