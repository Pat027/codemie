# Copyright 2026 EPAM Systems, Inc. ("EPAM")
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""JWKS-based JWT signature validation (opt-in, Serrala integration).

Implementation lives in codemie-enterprise (codemie_enterprise.idp.jwks).
This module re-exports the public surface and exposes process-level lifecycle
helpers (get_global_validator, jwks_warmup).
"""

from codemie.rest_api.security.jwks import runtime
from codemie.rest_api.security.jwks.runtime import (
    get_global_jwks_client,
    get_global_validator,
    jwks_warmup,
)

_ENTERPRISE_EXPORTS = frozenset(
    {
        "InvalidAlgorithmError",
        "JwksClient",
        "JwksError",
        "JwksFetchError",
        "KidNotFoundError",
        "TokenSignatureValidator",
        "TrustedIssuer",
        "UnknownIssuerError",
    }
)

__all__ = [
    "InvalidAlgorithmError",
    "JwksClient",
    "JwksError",
    "JwksFetchError",
    "KidNotFoundError",
    "TokenSignatureValidator",
    "TrustedIssuer",
    "UnknownIssuerError",
    "get_global_jwks_client",
    "get_global_validator",
    "jwks_warmup",
]


def __getattr__(name: str) -> object:
    if name in _ENTERPRISE_EXPORTS:
        if runtime.HAS_IDP:
            import codemie_enterprise.idp.jwks as _jwks

            return getattr(_jwks, name)
        return None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
