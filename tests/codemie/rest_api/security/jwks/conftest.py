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

"""Fixtures for JWKS integration tests (test_integration.py).

Unit-level JWKS fixtures (validator, stub_jwks_client, fake_clock, etc.)
live in codemie-enterprise/tests/idp/jwks/conftest.py alongside the unit tests.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import jwt
import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture
def rsa_keypair() -> tuple[str, str, dict]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    nums = public_key.public_numbers()
    jwk = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": "test-kid-1",
        "n": _b64url_uint(nums.n),
        "e": _b64url_uint(nums.e),
    }
    return private_pem, public_pem, jwk


@pytest.fixture
def alt_rsa_keypair() -> tuple[str, str, dict]:
    """A second, unrelated keypair for negative tests (untrusted-key rejection)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    nums = public_key.public_numbers()
    jwk = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": "test-kid-untrusted",
        "n": _b64url_uint(nums.n),
        "e": _b64url_uint(nums.e),
    }
    return private_pem, public_pem, jwk


@pytest.fixture
def issuer_url() -> str:
    return "https://auth.test.serrala.cloud/as"


@pytest.fixture
def audience() -> str:
    return "codemie-platform"


@pytest.fixture
def make_jwt(rsa_keypair, issuer_url, audience) -> Callable[..., str]:
    private_pem, _, _ = rsa_keypair

    def _make(
        claims_overrides: dict | None = None,
        key: str | None = None,
    ) -> str:
        now = datetime.now(timezone.utc)
        claims: dict[str, Any] = {
            "iss": issuer_url,
            "sub": "test-user-id",
            "email": "user@test.example",
            "aud": audience,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "groups": [],
        }
        if claims_overrides:
            claims.update(claims_overrides)
        return jwt.encode(claims, key or private_pem, algorithm="RS256", headers={"kid": "test-kid-1"})

    return _make


@pytest.fixture
def jwks_uri(issuer_url) -> str:
    return f"{issuer_url}/.well-known/jwks.json"


@pytest.fixture
def trusted_issuer(issuer_url, audience, jwks_uri):
    from codemie_enterprise.idp.jwks import TrustedIssuer

    return TrustedIssuer(
        issuer=issuer_url,
        audience=audience,
        jwks_uri=jwks_uri,
    )


@pytest.fixture
def jwks_response_one_key(rsa_keypair) -> dict:
    """JWKS body with a single RSA signing key (kid=test-kid-1)."""
    _, _, jwk = rsa_keypair
    return {"keys": [jwk]}
