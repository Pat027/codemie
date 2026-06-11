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

"""Unit tests for LeaderboardScheduler."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codemie.service.leaderboard.scheduler import LeaderboardScheduler

MODULE = "codemie.service.leaderboard.scheduler"


@pytest.fixture
def mock_scheduler():
    """APScheduler mock."""
    sched = MagicMock()
    sched.running = False
    return sched


@pytest.fixture
def leaderboard_scheduler(mock_scheduler):
    return LeaderboardScheduler(scheduler=mock_scheduler)


# ── start() ──────────────────────────────────────────────────────────


@patch(f"{MODULE}.config")
def test_start_does_nothing_when_disabled(mock_config, leaderboard_scheduler, mock_scheduler):
    # Arrange
    mock_config.LEADERBOARD_ENABLED = False

    # Act
    leaderboard_scheduler.start()

    # Assert
    mock_scheduler.add_job.assert_not_called()
    mock_scheduler.start.assert_not_called()


@patch(f"{MODULE}.logger")
@patch(f"{MODULE}.config")
def test_start_logs_error_on_invalid_cron(mock_config, mock_logger, leaderboard_scheduler, mock_scheduler):
    # Arrange
    mock_config.LEADERBOARD_ENABLED = True
    mock_config.LEADERBOARD_SCHEDULE = "0 2 *"  # only 3 parts, need 5

    # Act
    leaderboard_scheduler.start()

    # Assert
    mock_logger.error.assert_called_once()
    assert "Invalid LEADERBOARD_SCHEDULE" in mock_logger.error.call_args[0][0]
    mock_scheduler.add_job.assert_not_called()


@patch(f"{MODULE}.logger")
@patch(f"{MODULE}.config")
def test_start_registers_job_with_valid_cron(mock_config, mock_logger, leaderboard_scheduler, mock_scheduler):
    # Arrange
    mock_config.LEADERBOARD_ENABLED = True
    mock_config.LEADERBOARD_SCHEDULE = "30 2 * * *"

    # Act
    leaderboard_scheduler.start()

    # Assert
    mock_scheduler.add_job.assert_called_once()
    call_kwargs = mock_scheduler.add_job.call_args
    assert call_kwargs[1]["id"] == "leaderboard_computation"
    assert call_kwargs[1]["replace_existing"] is True
    assert call_kwargs[1]["name"] == "Leaderboard Computation"
    assert call_kwargs[0][0] == leaderboard_scheduler._run_leaderboard_computation
    mock_logger.info.assert_called_once()


@patch(f"{MODULE}.CronTrigger")
@patch(f"{MODULE}.config")
def test_start_builds_utc_cron_trigger(mock_config, mock_trigger_cls, leaderboard_scheduler, mock_scheduler):
    # Arrange
    mock_config.LEADERBOARD_ENABLED = True
    mock_config.LEADERBOARD_SCHEDULE = "15 4 1 */2 1-5"

    # Act
    leaderboard_scheduler.start()

    # Assert
    mock_trigger_cls.assert_called_once_with(
        minute="15",
        hour="4",
        day="1",
        month="*/2",
        day_of_week="1-5",
        timezone="UTC",
    )


@patch(f"{MODULE}.logger")
@patch(f"{MODULE}.config")
def test_start_starts_scheduler_when_not_running(mock_config, mock_logger, leaderboard_scheduler, mock_scheduler):
    # Arrange
    mock_config.LEADERBOARD_ENABLED = True
    mock_config.LEADERBOARD_SCHEDULE = "0 3 * * *"
    mock_scheduler.running = False

    # Act
    leaderboard_scheduler.start()

    # Assert
    mock_scheduler.start.assert_called_once()


@patch(f"{MODULE}.logger")
@patch(f"{MODULE}.config")
def test_start_skips_start_when_already_running(mock_config, mock_logger, leaderboard_scheduler, mock_scheduler):
    # Arrange
    mock_config.LEADERBOARD_ENABLED = True
    mock_config.LEADERBOARD_SCHEDULE = "0 3 * * *"
    mock_scheduler.running = True

    # Act
    leaderboard_scheduler.start()

    # Assert
    mock_scheduler.start.assert_not_called()


# ── _run_leaderboard_computation() ───────────────────────────────────


@asynccontextmanager
async def _fake_session():
    yield AsyncMock()


def _async_lock_cm(acquired: bool):
    """Build an async context manager that yields `acquired`."""

    @asynccontextmanager
    async def _cm(_lock_id):
        yield acquired

    return _cm


@pytest.mark.asyncio
@patch(f"{MODULE}.async_leader_lock", side_effect=_async_lock_cm(acquired=False))
async def test_run_computation_skips_when_lock_not_acquired(mock_lock_cm, leaderboard_scheduler):
    # Act
    result = await leaderboard_scheduler._run_leaderboard_computation()

    # Assert
    assert result is None
    mock_lock_cm.assert_called_once()


@pytest.mark.asyncio
@patch(f"{MODULE}.async_leader_lock", side_effect=_async_lock_cm(acquired=True))
@patch(f"{MODULE}.MetricsElasticRepository")
@patch(f"{MODULE}.LeaderboardService")
@patch(f"{MODULE}.get_async_session", side_effect=_fake_session)
@patch(f"{MODULE}.config")
async def test_run_computation_calls_service_when_lock_acquired(
    mock_config, mock_get_session, mock_service_cls, mock_elastic_repo, mock_lock_cm, leaderboard_scheduler
):
    # Arrange
    mock_config.LEADERBOARD_PERIOD_DAYS = 30

    mock_service = AsyncMock()
    mock_service.compute_rolling_snapshot.return_value = "snap-1"
    mock_service.compute_missing_archives.return_value = ["arch-1"]
    mock_service_cls.return_value = mock_service

    # Act
    await leaderboard_scheduler._run_leaderboard_computation()

    # Assert
    mock_service.compute_rolling_snapshot.assert_awaited_once_with(period_days=30)
    mock_service.compute_missing_archives.assert_awaited_once()
    mock_lock_cm.assert_called_once()


@pytest.mark.asyncio
@patch(f"{MODULE}.logger")
@patch(f"{MODULE}.async_leader_lock", side_effect=_async_lock_cm(acquired=True))
@patch(f"{MODULE}.LeaderboardService")
@patch(f"{MODULE}.get_async_session", side_effect=_fake_session)
@patch(f"{MODULE}.config")
async def test_run_computation_releases_lock_on_exception(
    mock_config, mock_get_session, mock_service_cls, mock_lock_cm, mock_logger, leaderboard_scheduler
):
    # Arrange
    mock_config.LEADERBOARD_PERIOD_DAYS = 30
    mock_service = AsyncMock()
    mock_service.compute_rolling_snapshot.side_effect = RuntimeError("DB down")
    mock_service_cls.return_value = mock_service

    # Act - should not raise; async_leader_lock's finally still runs
    await leaderboard_scheduler._run_leaderboard_computation()

    # Assert
    mock_lock_cm.assert_called_once()
    mock_logger.error.assert_called_once()


# ── stop() ───────────────────────────────────────────────────────────


@patch(f"{MODULE}.logger")
def test_stop_shuts_down_when_running(mock_logger, leaderboard_scheduler, mock_scheduler):
    # Arrange
    mock_scheduler.running = True

    # Act
    leaderboard_scheduler.stop()

    # Assert
    mock_scheduler.shutdown.assert_called_once_with(wait=False)
    mock_logger.info.assert_called_once_with("LeaderboardScheduler stopped")


def test_stop_does_nothing_when_not_running(leaderboard_scheduler, mock_scheduler):
    # Arrange
    mock_scheduler.running = False

    # Act
    leaderboard_scheduler.stop()

    # Assert
    mock_scheduler.shutdown.assert_not_called()
