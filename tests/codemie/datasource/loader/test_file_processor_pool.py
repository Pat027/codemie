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
from concurrent.futures.process import BrokenProcessPool
from unittest.mock import MagicMock, patch


def _noop(*args, **kwargs):
    return "result"


@pytest.fixture(autouse=True)
def reset_pool_state():
    """Reset FileProcessPoolManager class-level state between tests."""
    from codemie.datasource.loader.file_processor_pool import FileProcessPoolManager

    original_initialized = FileProcessPoolManager._initialized
    original_executor = FileProcessPoolManager._executor
    original_instance = FileProcessPoolManager._instance
    yield
    FileProcessPoolManager._initialized = original_initialized
    FileProcessPoolManager._executor = original_executor
    FileProcessPoolManager._instance = original_instance


class TestMaybePoolSubmit:
    def test_inline_when_disabled(self):
        """When ENABLE_FILE_MULTIPROCESSING=False, fn is called directly."""
        from codemie.datasource.loader.file_processor_pool import maybe_pool_submit

        called_with = []

        def fn(a, b):
            called_with.append((a, b))
            return "inline"

        with patch("codemie.datasource.loader.file_processor_pool.config") as mock_config:
            mock_config.ENABLE_FILE_MULTIPROCESSING = False
            result = maybe_pool_submit(fn, 1, b=2)

        assert result == "inline"
        assert called_with == [(1, 2)]

    def test_inline_when_not_initialized(self):
        """When pool is not initialized, fn is called directly."""
        from codemie.datasource.loader.file_processor_pool import maybe_pool_submit, FileProcessPoolManager

        FileProcessPoolManager._initialized = False

        def fn():
            return "inline"

        with patch("codemie.datasource.loader.file_processor_pool.config") as mock_config:
            mock_config.ENABLE_FILE_MULTIPROCESSING = True
            result = maybe_pool_submit(fn)

        assert result == "inline"

    def test_broken_pool_reinits_and_retries(self):
        """On BrokenProcessPool: reinit called, retry submitted, result returned."""
        from codemie.datasource.loader.file_processor_pool import maybe_pool_submit, FileProcessPoolManager

        FileProcessPoolManager._initialized = True

        mock_future_first = MagicMock()
        mock_future_first.result.side_effect = BrokenProcessPool("pool broken")

        mock_future_retry = MagicMock()
        mock_future_retry.result.return_value = "retry_result"

        mock_executor = MagicMock()
        mock_executor.submit.side_effect = [mock_future_first, mock_future_retry]
        FileProcessPoolManager._executor = mock_executor

        with (
            patch("codemie.datasource.loader.file_processor_pool.config") as mock_config,
            patch("codemie.datasource.loader.file_processor_pool._reinitialize_pool") as mock_reinit,
        ):
            mock_config.ENABLE_FILE_MULTIPROCESSING = True
            result = maybe_pool_submit(_noop, "arg1")

        mock_reinit.assert_called_once()
        assert mock_executor.submit.call_count == 2
        assert result == "retry_result"

    def test_reinit_failure_raises(self):
        """If _reinitialize_pool raises, the exception propagates."""
        from codemie.datasource.loader.file_processor_pool import maybe_pool_submit, FileProcessPoolManager

        FileProcessPoolManager._initialized = True

        mock_future = MagicMock()
        mock_future.result.side_effect = BrokenProcessPool("pool broken")

        mock_executor = MagicMock()
        mock_executor.submit.return_value = mock_future
        FileProcessPoolManager._executor = mock_executor

        with (
            patch("codemie.datasource.loader.file_processor_pool.config") as mock_config,
            patch(
                "codemie.datasource.loader.file_processor_pool._reinitialize_pool",
                side_effect=RuntimeError("reinit failed"),
            ),
        ):
            mock_config.ENABLE_FILE_MULTIPROCESSING = True
            with pytest.raises(RuntimeError, match="reinit failed"):
                maybe_pool_submit(_noop)

    def test_retry_failure_raises(self):
        """If reinit succeeds but retry submit raises, exception propagates."""
        from codemie.datasource.loader.file_processor_pool import maybe_pool_submit, FileProcessPoolManager

        FileProcessPoolManager._initialized = True

        mock_future_first = MagicMock()
        mock_future_first.result.side_effect = BrokenProcessPool("pool broken")

        mock_future_retry = MagicMock()
        mock_future_retry.result.side_effect = OSError("worker killed")

        mock_executor = MagicMock()
        mock_executor.submit.side_effect = [mock_future_first, mock_future_retry]
        FileProcessPoolManager._executor = mock_executor

        with (
            patch("codemie.datasource.loader.file_processor_pool.config") as mock_config,
            patch("codemie.datasource.loader.file_processor_pool._reinitialize_pool"),
        ):
            mock_config.ENABLE_FILE_MULTIPROCESSING = True
            with pytest.raises(OSError, match="worker killed"):
                maybe_pool_submit(_noop)

    def test_non_pool_exception_raises_unchanged(self):
        """Non-BrokenProcessPool exceptions from the future propagate directly."""
        from codemie.datasource.loader.file_processor_pool import maybe_pool_submit, FileProcessPoolManager

        FileProcessPoolManager._initialized = True

        mock_future = MagicMock()
        mock_future.result.side_effect = ValueError("bad input")

        mock_executor = MagicMock()
        mock_executor.submit.return_value = mock_future
        FileProcessPoolManager._executor = mock_executor

        with patch("codemie.datasource.loader.file_processor_pool.config") as mock_config:
            mock_config.ENABLE_FILE_MULTIPROCESSING = True
            with pytest.raises(ValueError, match="bad input"):
                maybe_pool_submit(_noop)


class TestReinitializePool:
    def test_calls_shutdown_then_initialize(self):
        from codemie.datasource.loader import file_processor_pool

        with (
            patch.object(file_processor_pool.file_process_pool, "shutdown") as mock_shutdown,
            patch.object(file_processor_pool.file_process_pool, "initialize") as mock_initialize,
            patch("codemie.datasource.loader.file_processor_pool.config") as mock_config,
        ):
            mock_config.FILE_DATASOURCE_MULTIPROCESSING_MAX_WORKERS = 2
            mock_config.FILE_MULTIPROCESSING_MAX_EXECUTED_TASK_PER_WORKER = 100
            file_processor_pool._reinitialize_pool()

        mock_shutdown.assert_called_once_with(wait=False)
        mock_initialize.assert_called_once_with(
            max_workers=2,
            max_tasks_per_child=100,
            force=True,
        )
