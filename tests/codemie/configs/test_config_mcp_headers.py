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
Test suite for forwarded headers blocklist configuration.

Tests FORWARDED_HEADERS_BLOCKLIST configuration loading and validation.
"""

import os
from unittest.mock import patch


from codemie.configs.config import Config


class TestForwardedHeadersBlocklistConfiguration:
    """Test cases for FORWARDED_HEADERS_BLOCKLIST configuration."""

    def test_default_blocked_headers_list(self):
        """
        Verify default blocked headers list contains expected security-critical headers.

        Priority: High
        """
        # Arrange & Act
        config = Config()

        # Assert
        assert hasattr(config, 'FORWARDED_HEADERS_BLOCKLIST')
        assert isinstance(config.FORWARDED_HEADERS_BLOCKLIST, str)

        # Parse and verify blocked headers
        blocked_headers = [h.strip().lower() for h in config.FORWARDED_HEADERS_BLOCKLIST.split(',')]

        # Verify all security-critical headers are in default blocked list
        expected_headers = [
            'authorization',
            'cookie',
            'set-cookie',
            'x-api-key',
            'x-auth-token',
            'x-internal-secret',
            'x-internal-token',
        ]

        for expected in expected_headers:
            assert expected in blocked_headers, f"Expected '{expected}' to be in blocked headers list"

    @patch.dict(os.environ, {'FORWARDED_HEADERS_BLOCKLIST': 'authorization,custom-blocked,x-special'})
    def test_custom_blocked_headers_from_env(self):
        """
        Verify FORWARDED_HEADERS_BLOCKLIST loads from environment variable.

        Priority: Critical
        """
        # Arrange & Act
        config = Config()

        # Assert
        assert config.FORWARDED_HEADERS_BLOCKLIST == 'authorization,custom-blocked,x-special'

        # Verify parsing works
        blocked_headers = [h.strip().lower() for h in config.FORWARDED_HEADERS_BLOCKLIST.split(',')]
        assert 'authorization' in blocked_headers
        assert 'custom-blocked' in blocked_headers
        assert 'x-special' in blocked_headers

    @patch.dict(os.environ, {'FORWARDED_HEADERS_BLOCKLIST': ''})
    def test_empty_blocked_headers_config(self):
        """
        Verify handling of empty blocked headers configuration.

        Priority: Critical
        """
        # Arrange & Act
        config = Config()

        # Assert - should use default or handle empty string gracefully
        assert isinstance(config.FORWARDED_HEADERS_BLOCKLIST, str)

        # Parsing empty string should not crash
        blocked_headers = [h.strip().lower() for h in config.FORWARDED_HEADERS_BLOCKLIST.split(',') if h.strip()]
        assert isinstance(blocked_headers, list)

    @patch.dict(os.environ, {'FORWARDED_HEADERS_BLOCKLIST': 'authorization, cookie , x-api-key,  ,x-internal'})
    def test_blocked_headers_with_whitespace(self):
        """
        Verify handling of blocked headers with whitespace.

        Priority: Critical
        """
        # Arrange & Act
        config = Config()

        # Assert
        blocked_headers = [h.strip().lower() for h in config.FORWARDED_HEADERS_BLOCKLIST.split(',') if h.strip()]

        # Verify whitespace is handled
        assert 'authorization' in blocked_headers
        assert 'cookie' in blocked_headers
        assert 'x-api-key' in blocked_headers
        assert 'x-internal' in blocked_headers
        assert '' not in blocked_headers  # Empty strings should be filtered

    @patch.dict(os.environ, {'FORWARDED_HEADERS_BLOCKLIST': 'AUTHORIZATION,Cookie,X-API-Key'})
    def test_blocked_headers_case_variations(self):
        """
        Verify case variations in configuration.

        Priority: Critical
        """
        # Arrange & Act
        config = Config()

        # Assert - configuration stores as-is
        assert (
            'AUTHORIZATION' in config.FORWARDED_HEADERS_BLOCKLIST
            or 'authorization' in config.FORWARDED_HEADERS_BLOCKLIST.lower()
        )

        # Verify case-insensitive parsing works
        blocked_headers = [h.strip().lower() for h in config.FORWARDED_HEADERS_BLOCKLIST.split(',')]
        assert 'authorization' in blocked_headers
        assert 'cookie' in blocked_headers
        assert 'x-api-key' in blocked_headers
