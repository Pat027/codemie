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

"""End-to-end integration tests: FastAPI app + JwksValidatingIdp + real JWT
+ pytest-httpx fake JWKS server.

These tests mount a tiny FastAPI app whose protected endpoint depends on the
JwksValidatingIdp wrapper. Network calls to the JWKS endpoint go through
pytest-httpx; TestClient calls to the app itself bypass the network entirely
(in-process ASGI transport)."""

from __future__ import annotations

import time

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

pytest.importorskip("codemie_enterprise.idp.jwks", reason="requires codemie-enterprise with JWKS support")

from codemie.core.exceptions import ExtendedHTTPException  # noqa: E402
from codemie.rest_api.security.idp.base import BaseIdp  # noqa: E402
from codemie.rest_api.security.idp.jwks_validating import JwksValidatingIdp  # noqa: E402
from codemie.rest_api.security.user import User  # noqa: E402
from codemie_enterprise.idp.jwks import JwksClient, TokenSignatureValidator  # noqa: E402


@pytest.fixture
def non_mocked_hosts() -> list[str]:
    """Tell pytest-httpx not to intercept TestClient's in-process calls."""
    return ["testserver"]


class _StubInnerIdp(BaseIdp):
    """Minimal inner IDP that returns a static User if authenticate is called.

    In production this would be the real OIDCIdp / KeycloakIdp doing claim
    extraction. For these integration tests we just need *something* that
    returns a User after the validator passes."""

    def get_session_cookie(self) -> str:
        return ""

    async def authenticate(self, request: Request) -> User:
        return User(
            id="u-integration",
            username="u-integration",
            email="u@test.example",
            name="u",
            roles=[],
            project_names=["application_tenant-25"],
            admin_project_names=[],
            knowledge_bases=[],
            is_admin=False,
            is_maintainer=False,
            picture="",
        )


def _build_app(idp: BaseIdp) -> FastAPI:
    app = FastAPI()

    async def authenticate(request: Request) -> User:
        try:
            return await idp.authenticate(request)
        except ExtendedHTTPException as e:
            raise e

    @app.exception_handler(ExtendedHTTPException)
    async def _exc(_request: Request, exc: ExtendedHTTPException):
        return JSONResponse(
            status_code=exc.code,
            content={"message": exc.message, "details": exc.details},
        )

    @app.get("/protected")
    async def protected(user: User = Depends(authenticate)) -> dict:
        return {"user_id": user.id}

    return app


@pytest.fixture
def integration_app(trusted_issuer):
    jwks_client = JwksClient(issuers=[trusted_issuer], ttl_seconds=300)
    validator = TokenSignatureValidator(jwks_client=jwks_client, issuers=[trusted_issuer])
    wrapped = JwksValidatingIdp(inner=_StubInnerIdp(), validator=validator)
    return _build_app(wrapped)


@pytest.fixture
def integration_client(integration_app):
    return TestClient(integration_app)


class TestEndToEndJwksValidation:
    def test_full_request_flow_with_real_rs256_token(
        self,
        integration_client,
        make_jwt,
        jwks_uri,
        jwks_response_one_key,
        httpx_mock,
    ):
        httpx_mock.add_response(url=jwks_uri, json=jwks_response_one_key)
        token = make_jwt()

        resp = integration_client.get("/protected", headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200
        assert resp.json() == {"user_id": "u-integration"}

    def test_full_request_flow_rejects_token_signed_by_untrusted_key(
        self,
        integration_client,
        make_jwt,
        alt_rsa_keypair,
        jwks_uri,
        jwks_response_one_key,
        httpx_mock,
    ):
        """JWKS publishes only the trusted key. Token is signed by an untrusted
        key whose `kid` happens to match. Validator must reject (signature
        verification fails after key lookup)."""
        httpx_mock.add_response(url=jwks_uri, json=jwks_response_one_key)
        # Sign with the untrusted private key but keep the trusted kid
        untrusted_private, _, _ = alt_rsa_keypair
        token = make_jwt(key=untrusted_private)

        resp = integration_client.get("/protected", headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 401
        assert "Invalid or expired credentials" in (resp.json().get("details") or "")

    def test_full_request_flow_handles_jwks_endpoint_5xx(self, integration_client, make_jwt, jwks_uri, httpx_mock):
        httpx_mock.add_response(url=jwks_uri, status_code=503)
        token = make_jwt()

        resp = integration_client.get("/protected", headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 401

    def test_warm_cache_validation_latency_under_budget(
        self,
        integration_client,
        make_jwt,
        jwks_uri,
        jwks_response_one_key,
        httpx_mock,
    ):
        """Sanity-check on the warm-cache latency budget (< ~10ms p95).

        The plan target is < 5ms warm-cache validation, but TestClient adds
        framework overhead and CI nodes vary, so we assert a looser p95 of
        20ms. Anything above this would suggest a real perf regression
        (e.g. JWKS being re-fetched per request, or sig verification on a
        cold key)."""
        httpx_mock.add_response(url=jwks_uri, json=jwks_response_one_key)
        token = make_jwt()
        headers = {"Authorization": f"Bearer {token}"}

        # Warm-up: first call pays the JWKS fetch
        integration_client.get("/protected", headers=headers)

        latencies_ms: list[float] = []
        for _ in range(20):
            t0 = time.perf_counter()
            resp = integration_client.get("/protected", headers=headers)
            latencies_ms.append((time.perf_counter() - t0) * 1000)
            assert resp.status_code == 200

        latencies_ms.sort()
        p95 = latencies_ms[int(len(latencies_ms) * 0.95) - 1]
        assert p95 < 20.0, f"Warm-cache p95 {p95:.2f}ms exceeds 20ms budget; all latencies (sorted, ms): {latencies_ms}"
