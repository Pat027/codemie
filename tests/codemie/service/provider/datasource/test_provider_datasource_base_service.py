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

import pytest

from codemie.rest_api.models.provider import (
    ProviderDataSourceTypeSchema,
    ProviderToolkitConfigParameter,
)
from codemie.service.provider.datasource.provider_datasource_base_service import ProviderDatasourceBaseService


def test_run():
    with pytest.raises(NotImplementedError):
        ProviderDatasourceBaseService().run()


def _param(name, *, required=False, default_value=None, enum=None, parameter_type=None):
    """Builds a schema parameter for _extract_params tests."""
    return ProviderDataSourceTypeSchema.Parameter(
        name=name,
        description="",
        required=required,
        parameter_type=parameter_type or ProviderToolkitConfigParameter.ParameterType.NUMBER,
        enum=enum,
        default_value=default_value,
    )


def test_extract_params_uses_default_value_when_omitted():
    """default_value is applied when the user omits the field entirely."""
    param = _param("temperature", default_value="0.0", enum=["0.0", "0.5"])

    result = ProviderDatasourceBaseService()._extract_params({}, [param])

    assert result == {"temperature": "0.0"}


def test_extract_params_skips_optional_without_default():
    """Backward compat: optional field without a default is simply skipped (no error)."""
    param = _param("temperature", required=False, default_value=None)

    result = ProviderDatasourceBaseService()._extract_params({}, [param])

    assert result == {}


def test_extract_params_explicit_value_overrides_default():
    """A value provided by the user takes precedence over default_value."""
    param = _param("top_k", default_value="3")

    result = ProviderDatasourceBaseService()._extract_params({"top_k": "5"}, [param])

    assert result == {"top_k": "5"}


def test_extract_params_default_not_in_enum_is_accepted():
    """default_value is not validated against enum; it is applied as-is."""
    param = _param("temperature", default_value="99", enum=["0.0", "0.5"])

    result = ProviderDatasourceBaseService()._extract_params({}, [param])

    assert result == {"temperature": "99"}


def test_extract_params_required_without_default_raises():
    """Required non-secret field with neither value nor default still errors."""
    param = _param("top_k", required=True, default_value=None)

    with pytest.raises(ValueError, match="Missing required parameter: top_k"):
        ProviderDatasourceBaseService()._extract_params({}, [param])


def test_extract_params_default_used_when_required_and_omitted():
    """A required field falls back to its default before raising."""
    param = _param("top_k", required=True, default_value="3")

    result = ProviderDatasourceBaseService()._extract_params({}, [param])

    assert result == {"top_k": "3"}
