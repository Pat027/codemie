# Copyright 2026 EPAM Systems, Inc. ("EPAM")
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Process-level singletons for the JWKS validator and JWKS client.

The IdpFactory creates a fresh IDP instance per request (`return idp_class()`
in factory.py), so JWKS state must NOT live inside an IDP — it would never be
reused. These module-level lazy singletons give every wrapper IDP the same
underlying validator + cache."""

from __future__ import annotations

import asyncio
import functools
import json
from typing import TYPE_CHECKING

from codemie.configs import config
from codemie.configs.logger import logger
from codemie.enterprise.loader import HAS_IDP

if TYPE_CHECKING:
    from codemie_enterprise.idp.jwks import JwksClient, TokenSignatureValidator


def _build() -> tuple[JwksClient, TokenSignatureValidator]:
    if not HAS_IDP:
        raise RuntimeError(
            "JWKS validation requires the codemie-enterprise package. Install it or set JWKS_VALIDATION_ENABLED=false."
        )
    from codemie_enterprise.idp.jwks import JwksClient, TokenSignatureValidator, TrustedIssuer

    raw = (config.JWKS_TRUSTED_ISSUERS or "").strip()
    if not raw:
        raise ValueError(
            "JWKS validation is enabled but JWKS_TRUSTED_ISSUERS is empty. "
            "Set JWKS_TRUSTED_ISSUERS to a JSON list of {issuer, audience, "
            "jwks_uri|discovery_url} entries."
        )
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"JWKS_TRUSTED_ISSUERS is not valid JSON: {e}") from e
    if not isinstance(items, list):
        raise ValueError("JWKS_TRUSTED_ISSUERS must be a JSON list")

    seen_issuers: set[str] = set()
    issuers: list[TrustedIssuer] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"JWKS_TRUSTED_ISSUERS entry {i} must be a JSON object, got {type(item).__name__}")
        trusted = TrustedIssuer(**item)
        if trusted.issuer in seen_issuers:
            raise ValueError(f"JWKS_TRUSTED_ISSUERS contains duplicate issuer: {trusted.issuer!r}")
        seen_issuers.add(trusted.issuer)
        issuers.append(trusted)

    if not issuers:
        raise ValueError("JWKS validation is enabled but JWKS_TRUSTED_ISSUERS parsed to an empty list.")

    client = JwksClient(
        issuers=issuers,
        ttl_seconds=config.JWKS_CACHE_TTL_SECONDS,
        http_timeout=config.JWKS_HTTP_TIMEOUT_SECONDS,
    )
    validator = TokenSignatureValidator(
        jwks_client=client,
        issuers=issuers,
        leeway_seconds=config.JWKS_LEEWAY_SECONDS,
    )
    return client, validator


@functools.lru_cache(maxsize=1)
def _get_singletons() -> tuple[JwksClient, TokenSignatureValidator]:
    return _build()


def get_global_jwks_client() -> JwksClient:
    return _get_singletons()[0]


def get_global_validator() -> TokenSignatureValidator:
    return _get_singletons()[1]


async def jwks_warmup() -> None:
    """Prefetch JWKS for all configured trusted issuers. Called from main.py
    lifespan so the first inbound request doesn't pay the JWKS round-trip.

    Failures here are non-fatal — the runtime path will retry on demand. We
    log them so deployment misconfigs surface immediately instead of waiting
    for the first user request to fail with a 401.
    """
    if not config.JWKS_VALIDATION_ENABLED:
        return
    try:
        client = get_global_jwks_client()
    except (ValueError, RuntimeError) as e:
        logger.error(f"JWKS validation is enabled but config is invalid: {e}")
        return
    try:
        await client.warm_up()
        logger.info("JWKS warm-up complete")
    except BaseException as e:  # warm-up is best-effort; BaseException catches CancelledError
        if isinstance(e, asyncio.CancelledError):
            logger.warning("JWKS warm-up cancelled during shutdown")
            raise
        logger.warning(f"JWKS warm-up failed (will retry on demand): {e}")


def reset_for_tests() -> None:
    """Test-only: drop the cached singletons so the next call re-reads config."""
    _get_singletons.cache_clear()
