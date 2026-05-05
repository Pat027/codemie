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

"""Centralized user identity resolution for analytics handlers."""

from __future__ import annotations

import logging

from codemie.clients.postgres import get_async_session
from codemie.repository.user_repository import user_repository

logger = logging.getLogger(__name__)

_CODEMIE_SUFFIX_SEP = "_codemie_"
_SENTINEL_VALUES: frozenset[str] = frozenset({"unknown"})


class UserIdentityResolver:
    """Single source of truth for resolving raw user identifiers to emails.

    Resolution steps (applied to each candidate in priority order):
      1. Strip _codemie_* suffix — if result contains @ it is an email, done.
      2. UUID  → bulk lookup by UserDB.id
      3. Name  → bulk lookup by UserDB.username or UserDB.name
    """

    @staticmethod
    async def resolve(*values: str | None) -> str:
        """Resolve the first valid email from the given candidates (tried in order).

        Each value is suffix-stripped; if the result contains @ it is returned
        immediately.  Otherwise all stripped candidates are resolved via a single
        bulk PostgreSQL lookup and the highest-priority match is returned.

        Usage: await UserIdentityResolver.resolve(user_email, user_name, raw_id)
        """
        candidates = [UserIdentityResolver._strip_suffix(v) for v in values if v]

        for c in candidates:
            if UserIdentityResolver._is_email(c):
                logger.debug(f"resolve: email candidate returned as-is: {c}")
                return c

        if not candidates:
            return ""

        async with get_async_session() as session:
            resolved = await user_repository.afind_emails_by_identifiers(session, set(candidates))

        for c in candidates:
            if email := resolved.get(c):
                logger.debug(f"resolve: {c!r} -> {email}")
                return email

        logger.debug(f"resolve: no email found for candidates={candidates}, returning {candidates[0]!r}")
        return candidates[0]

    @staticmethod
    async def resolve_rows(rows: list[dict], *column_keys: str) -> None:
        """Normalise user identifier columns in rows **in-place**.

        For each column in column_keys:
          1. Strip _codemie_* suffix.
          2. Resolve non-email values via a single bulk PostgreSQL lookup.
        """
        UserIdentityResolver._strip_row_identifiers(rows, column_keys)

        to_resolve = UserIdentityResolver._collect_unresolved(rows, column_keys)
        if not to_resolve:
            return

        logger.debug(f"resolve_rows: resolving {len(to_resolve)} non-email identifier(s): {to_resolve}")

        async with get_async_session() as session:
            resolved = await user_repository.afind_emails_by_identifiers(session, to_resolve)

        logger.debug(f"resolve_rows: DB resolved {len(resolved)}/{len(to_resolve)} identifier(s)")
        UserIdentityResolver._apply_resolved(rows, column_keys, resolved)

    @staticmethod
    def _strip_row_identifiers(rows: list[dict], column_keys: tuple[str, ...]) -> None:
        for row in rows:
            for key in column_keys:
                if val := row.get(key):
                    row[key] = UserIdentityResolver._strip_suffix(val)

    @staticmethod
    def _collect_unresolved(rows: list[dict], column_keys: tuple[str, ...]) -> set[str]:
        return {
            row[key]
            for row in rows
            for key in column_keys
            if (val := row.get(key)) and not UserIdentityResolver._is_email(val) and val not in _SENTINEL_VALUES
        }

    @staticmethod
    def _apply_resolved(rows: list[dict], column_keys: tuple[str, ...], resolved: dict[str, str]) -> None:
        for row in rows:
            for key in column_keys:
                val = row.get(key)
                if not val or UserIdentityResolver._is_email(val) or val in _SENTINEL_VALUES:
                    continue
                new_val = resolved.get(val, val)
                if new_val != val:
                    logger.debug(f"resolve_rows[{key}]: {val!r} -> {new_val!r}")
                else:
                    logger.debug(f"resolve_rows[{key}]: {val!r} unresolved, keeping as-is")
                row[key] = new_val

    @staticmethod
    def _strip_suffix(value: str) -> str:
        idx = value.find(_CODEMIE_SUFFIX_SEP)
        return value[:idx] if idx >= 0 else value

    @staticmethod
    def _is_email(value: str) -> bool:
        return "@" in value
