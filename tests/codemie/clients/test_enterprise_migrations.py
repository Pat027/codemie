# Copyright 2026 EPAM Systems, Inc. (“EPAM”)
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

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from codemie.configs import config


def test_enterprise_migration_lock_id_is_stable_signed_big_endian():
    from codemie.clients.postgres import _enterprise_migration_lock_id

    expected = int.from_bytes(
        hashlib.sha256(b"codemie_enterprise:mcp-auth:migrations").digest()[:8],
        byteorder="big",
        signed=True,
    )

    assert _enterprise_migration_lock_id("mcp-auth") == expected


def test_alembic_upgrade_enterprise_postgres_skips_when_disabled(monkeypatch):
    from codemie.clients.postgres import alembic_upgrade_enterprise_postgres

    monkeypatch.setattr("codemie.enterprise.loader.HAS_MCP_AUTH", True)
    monkeypatch.setattr(
        "codemie.enterprise.loader.enterprise_mcp_auth_alembic_locations",
        MagicMock(),
    )
    monkeypatch.setattr(config, "MCP_AUTH_ENABLED", False)
    monkeypatch.setattr(config, "MCP_AUTH_TMS_ENABLED", True)

    with patch("codemie.clients.postgres.PostgresClient.get_engine") as get_engine:
        with patch("alembic.command.upgrade") as upgrade:
            alembic_upgrade_enterprise_postgres()

    get_engine.assert_not_called()
    upgrade.assert_not_called()


def test_alembic_upgrade_enterprise_postgres_fails_closed_when_enabled_without_enterprise(monkeypatch):
    from codemie.clients.postgres import alembic_upgrade_enterprise_postgres

    monkeypatch.setattr("codemie.enterprise.loader.HAS_MCP_AUTH", False)
    monkeypatch.setattr(
        "codemie.enterprise.loader.enterprise_mcp_auth_alembic_locations",
        None,
    )
    monkeypatch.setattr(config, "MCP_AUTH_ENABLED", True)
    monkeypatch.setattr(config, "MCP_AUTH_TMS_ENABLED", True)

    with patch("codemie.clients.postgres.PostgresClient.get_engine") as get_engine:
        with patch("alembic.command.upgrade") as upgrade:
            with pytest.raises(RuntimeError, match="enterprise MCP auth package"):
                alembic_upgrade_enterprise_postgres()

    get_engine.assert_not_called()
    upgrade.assert_not_called()


def test_alembic_upgrade_enterprise_postgres_fails_closed_when_enabled_without_provider(monkeypatch):
    from codemie.clients.postgres import alembic_upgrade_enterprise_postgres

    monkeypatch.setattr("codemie.enterprise.loader.HAS_MCP_AUTH", True)
    monkeypatch.setattr("codemie.enterprise.loader.enterprise_mcp_auth_alembic_locations", None)
    monkeypatch.setattr(config, "MCP_AUTH_ENABLED", True)
    monkeypatch.setattr(config, "MCP_AUTH_TMS_ENABLED", True)

    with patch("codemie.clients.postgres.PostgresClient.get_engine") as get_engine:
        with patch("alembic.command.upgrade") as upgrade:
            with pytest.raises(RuntimeError, match="enterprise MCP auth migrations"):
                alembic_upgrade_enterprise_postgres()

    get_engine.assert_not_called()
    upgrade.assert_not_called()


def test_alembic_upgrade_enterprise_postgres_runs_discovered_locations(monkeypatch):
    from codemie.clients.postgres import (
        _enterprise_migration_lock_id,
        alembic_upgrade_enterprise_postgres,
    )

    location = SimpleNamespace(name="mcp-auth", script_location="/enterprise/mcp_auth/alembic")
    connection = MagicMock()
    engine = MagicMock()
    location_context_active = False

    @contextmanager
    def enterprise_locations():
        nonlocal location_context_active
        location_context_active = True
        yield [location]
        location_context_active = False

    @contextmanager
    def transaction():
        yield connection

    def assert_upgrade_config(alembic_cfg, revision):
        assert location_context_active is True
        assert revision == "head"
        assert alembic_cfg.get_main_option("script_location") == location.script_location
        assert alembic_cfg.attributes["connection"] is connection
        assert alembic_cfg.attributes["schema_name"] == config.DEFAULT_DB_SCHEMA

    engine.begin.side_effect = transaction

    monkeypatch.setattr("codemie.enterprise.loader.HAS_MCP_AUTH", True)
    monkeypatch.setattr(
        "codemie.enterprise.loader.enterprise_mcp_auth_alembic_locations",
        enterprise_locations,
    )
    monkeypatch.setattr(config, "MCP_AUTH_ENABLED", True)
    monkeypatch.setattr(config, "MCP_AUTH_TMS_ENABLED", True)
    monkeypatch.setattr(config, "ALEMBIC_INI_PATH", Path("src/external/alembic/alembic.ini"))

    with patch("codemie.clients.postgres.PostgresClient.get_engine", return_value=engine):
        with patch("alembic.command.upgrade", side_effect=assert_upgrade_config) as upgrade:
            alembic_upgrade_enterprise_postgres()

    upgrade.assert_called_once()
    connection.execute.assert_called_once()
    statement, params = connection.execute.call_args.args
    assert str(statement) == "select pg_advisory_xact_lock(:lock_id)"
    assert params == {"lock_id": _enterprise_migration_lock_id(location.name)}
