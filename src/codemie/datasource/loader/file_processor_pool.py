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

"""Shared process pool for file datasource processing."""

import atexit
import contextlib
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable, Optional

from codemie.configs import logger
from codemie.configs import config
from codemie.configs.pyroscope_config import configure_pyroscope
# from codemie.core.exceptions import CodeMieException


class FileProcessPoolManager:
    """
    Singleton manager for shared ProcessPoolExecutor.

    Manages lifecycle of process pool used for parallel file parsing.
    Reuses same pool across multiple file datasource operations for efficiency.
    """

    _instance: Optional['FileProcessPoolManager'] = None
    _executor: Optional[ProcessPoolExecutor] = None
    _max_workers: int = 4
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def initialize(cls, max_workers: int = 4, max_tasks_per_child: int = 10, force: bool = False) -> None:
        """
        Initialize shared process pool.

        Args:
            max_workers: Number of worker processes
        """
        if cls._initialized and not force:
            return

        cls._max_workers = max_workers

        # Set fork mode for faster startup on Unix systems
        with contextlib.suppress(RuntimeError):
            multiprocessing.set_start_method('fork', force=True)

        if max_tasks_per_child < 0:
            max_tasks_per_child = None
        cls._executor = ProcessPoolExecutor(
            max_workers=max_workers,
            max_tasks_per_child=max_tasks_per_child,
            initializer=configure_pyroscope,
            initargs=({"process_type": "subprocess", "process_pool": cls.__name__},),
        )
        cls._initialized = True

        # Register shutdown on exit
        atexit.register(cls.shutdown)

        start_method = multiprocessing.get_start_method()
        logger.info(f"Initialized file process pool with {max_workers} workers, start_method={start_method}")

    @classmethod
    def get_executor(cls) -> ProcessPoolExecutor:
        """
        Get shared executor instance.

        Returns:
            ProcessPoolExecutor instance

        Raises:
            RuntimeError: If pool not initialized
        """
        if not cls._initialized or cls._executor is None:
            raise RuntimeError("Process pool not initialized. Call initialize() first.")

        return cls._executor

    @classmethod
    def shutdown(cls, wait: bool = True) -> None:
        """
        Shutdown process pool.

        Args:
            wait: Wait for pending tasks to complete
        """
        if cls._executor is not None:
            # logger.info("Shutting down file process pool")
            cls._executor.shutdown(wait=wait)
            cls._executor = None
            cls._initialized = False

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if pool is initialized."""
        return cls._initialized


# Global singleton instance
file_process_pool = FileProcessPoolManager()
if config.ENABLE_FILE_MULTIPROCESSING:
    file_process_pool.initialize(
        max_workers=config.FILE_DATASOURCE_MULTIPROCESSING_MAX_WORKERS,
        max_tasks_per_child=config.FILE_MULTIPROCESSING_MAX_EXECUTED_TASK_PER_WORKER,
    )


def maybe_pool_submit(fn: Callable, *args: Any, **kwargs: Any) -> Any:
    if config.ENABLE_FILE_MULTIPROCESSING and file_process_pool.is_initialized():
        try:
            future = file_process_pool.get_executor().submit(fn, *args, **kwargs)
            return future.result()
        except Exception as e:
            raise e
    return fn(*args, **kwargs)
