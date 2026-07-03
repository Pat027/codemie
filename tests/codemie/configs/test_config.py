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

import pytest
from pydantic import ValidationError

from codemie.configs.config import Config


def test_is_local_local():
    config = Config()
    config.ENV = "local"
    assert config.is_local is True


def test_is_local_prod():
    config = Config()
    config.ENV = "prod"
    assert config.is_local is False


def test_budget_reset_reconciliation_schedule_validation_is_skipped_when_job_disabled():
    config = Config(
        LITELLM_BUDGET_RESET_RECONCILIATION_ENABLED=False,
        LITELLM_BUDGET_RESET_RECONCILIATION_SCHEDULE="not a valid cron",
    )

    assert config.LITELLM_BUDGET_RESET_RECONCILIATION_SCHEDULE == "not a valid cron"


def test_budget_reset_reconciliation_schedule_validation_runs_when_job_enabled():
    with pytest.raises(ValidationError):
        Config(
            LITELLM_BUDGET_RESET_RECONCILIATION_ENABLED=True,
            LITELLM_BUDGET_RESET_RECONCILIATION_SCHEDULE="not a valid cron",
        )


def test_authorized_apps_allowed_key_domains_default():
    config = Config()
    assert config.AUTHORIZED_APPS_ALLOWED_KEY_DOMAINS == []


def test_authorized_apps_allowed_key_domains_env_override(monkeypatch):
    monkeypatch.setenv("AUTHORIZED_APPS_ALLOWED_KEY_DOMAINS", '["trusted.example", "keys.trusted.example"]')
    config = Config()
    assert config.AUTHORIZED_APPS_ALLOWED_KEY_DOMAINS == ["trusted.example", "keys.trusted.example"]
