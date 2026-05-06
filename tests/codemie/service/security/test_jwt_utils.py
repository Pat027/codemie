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

import base64
import json
from datetime import UTC, datetime

from codemie.service.security.jwt_utils import parse_jwt_exp


def _make_jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).rstrip(b"=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    sig = base64.urlsafe_b64encode(b"fakesig").rstrip(b"=")
    return f"{header.decode()}.{body.decode()}.{sig.decode()}"


def test_parse_jwt_exp_valid():
    exp_ts = 1735689600  # 2025-01-01 00:00:00 UTC
    token = _make_jwt({"sub": "user1", "exp": exp_ts})
    result = parse_jwt_exp(token)
    assert result == datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)


def test_parse_jwt_exp_missing_exp_claim():
    token = _make_jwt({"sub": "user1"})
    assert parse_jwt_exp(token) is None


def test_parse_jwt_exp_malformed_not_three_segments():
    assert parse_jwt_exp("only.two") is None
    assert parse_jwt_exp("nope") is None


def test_parse_jwt_exp_non_base64_payload():
    assert parse_jwt_exp("aaa.!!!invalid!!!.bbb") is None


def test_parse_jwt_exp_empty_string():
    assert parse_jwt_exp("") is None
