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

from __future__ import annotations

import asyncio
import threading
from typing import Any

from fastapi import FastAPI

from codemie.configs import config, logger


_thread_metrics_registered = False


def configure_prometheus_http_metrics(app: FastAPI) -> None:
    """Instrument the FastAPI app for HTTP metrics collection.

    Metrics are served on a separate internal port via start_metrics_server(),
    not on the main application port.
    """
    if not config.PROMETHEUS_ENABLED:
        return

    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_instrument_requests_inprogress=True,
    ).instrument(app)

    _register_thread_metrics()


async def start_metrics_server() -> tuple[asyncio.Task, Any]:
    """Start an isolated Uvicorn server serving Prometheus metrics on a separate port.

    Returns (task, server) so the caller can signal graceful shutdown via
    server.should_exit = True.
    """
    import uvicorn
    from prometheus_client import make_asgi_app

    metrics_app = make_asgi_app()
    server_config = uvicorn.Config(
        app=metrics_app,
        host=config.PROMETHEUS_METRICS_HOST,
        port=config.PROMETHEUS_METRICS_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(server_config)
    task = asyncio.create_task(server.serve(), name="prometheus_metrics_server")
    logger.info(
        f"Prometheus metrics server started on {config.PROMETHEUS_METRICS_HOST}:{config.PROMETHEUS_METRICS_PORT}"
    )
    return task, server


def register_prometheus_db_pool_metrics() -> None:
    """Register DB connection pool gauges after engines are created."""
    if not config.PROMETHEUS_ENABLED:
        return

    try:
        from prometheus_client import Gauge

        from codemie.clients.postgres import PostgresClient

        sync_pool = PostgresClient.get_engine().pool
        async_pool = PostgresClient.get_async_engine().sync_engine.pool

        for prefix, pool in [("sync", sync_pool), ("async", async_pool)]:
            Gauge(f"db_{prefix}_pool_size", f"DB {prefix} pool configured size").set_function(lambda p=pool: p.size())
            Gauge(f"db_{prefix}_pool_checked_out", f"DB {prefix} active connections").set_function(
                lambda p=pool: p.checkedout()
            )
            Gauge(f"db_{prefix}_pool_overflow", f"DB {prefix} pool overflow connections").set_function(
                lambda p=pool: p.overflow()
            )
    except ValueError:
        pass
    except Exception as e:
        logger.warning(f"Failed to register DB pool metrics: {e}")


def _register_thread_metrics() -> None:
    """Register Python thread metrics once per process."""
    global _thread_metrics_registered

    if _thread_metrics_registered:
        return

    from prometheus_client import Counter, Gauge

    Gauge("python_active_threads", "Number of active Python threads").set_function(threading.active_count)

    threads_created = Counter("python_threads_created_total", "Total Python threads created since startup")
    original_thread_start = threading.Thread.start

    def _patched_thread_start(self, *args, **kwargs):
        threads_created.inc()
        original_thread_start(self, *args, **kwargs)

    threading.Thread.start = _patched_thread_start

    active_running = Gauge("python_threads_active_running", "Threads currently executing Thread.run()")
    original_thread_run = threading.Thread.run

    def _patched_thread_run(self):
        active_running.inc()
        try:
            original_thread_run(self)
        finally:
            active_running.dec()

    threading.Thread.run = _patched_thread_run
    _thread_metrics_registered = True
