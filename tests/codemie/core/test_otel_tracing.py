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

from unittest.mock import patch


from codemie.core.otel_tracing import get_traceparent_headers


class TestGetTraceparentHeaders:
    """Unit tests for get_traceparent_headers()."""

    def test_returns_traceparent_when_active_span(self):
        def fake_inject(carrier, *a, **kw):
            carrier["traceparent"] = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

        with patch("opentelemetry.propagate.inject", side_effect=fake_inject):
            result = get_traceparent_headers()

        assert result == {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}

    def test_returns_empty_when_no_active_span(self):
        # propagate.inject adds nothing when no valid span is active
        with patch("opentelemetry.propagate.inject"):
            result = get_traceparent_headers()

        assert result == {}

    def test_swallows_exceptions_and_returns_empty(self):
        with patch("opentelemetry.propagate.inject", side_effect=RuntimeError("OTEL failure")):
            result = get_traceparent_headers()

        assert result == {}
