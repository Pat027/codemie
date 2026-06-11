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

"""Service for detecting and marking stale datasources.

This module implements the business logic for identifying datasources
that haven't been used for a configurable period and marking them
with the appropriate lifecycle state.
"""

from __future__ import annotations

from datetime import datetime, timedelta, UTC
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, or_

from codemie.configs import logger, config
from codemie.repository.metrics_elastic_repository import MetricsElasticRepository
from codemie.rest_api.models.index import IndexInfo, LifecycleState


class StaleDatasourceService:
    """Service for detecting and marking stale datasources.

    Identifies datasources that:
    1. Have no usage metrics in Elasticsearch for X days, OR
    2. Haven't been updated in Y days (for datasources without metrics)
    3. Are not in grace period (created within Z days)

    Then marks them with lifecycle_state = "stale".
    """

    def __init__(
        self,
        session: AsyncSession,
        metrics_repository: MetricsElasticRepository,
    ):
        """Initialize service with database session and metrics repository.

        Args:
            session: AsyncIO SQLAlchemy session for database operations
            metrics_repository: Repository for querying Elasticsearch metrics
        """
        self.session = session
        self.metrics_repository = metrics_repository

    async def detect_and_mark_stale_datasources(self) -> dict:
        """Main entry point: detect and mark stale datasources.

        Returns:
            dict: Summary statistics with keys:
                - total_evaluated: Number of datasources evaluated
                - newly_marked_stale: Number newly marked as stale
                - already_stale: Number already marked stale
                - errors: Number of errors encountered
        """
        logger.info("Starting stale datasource detection")

        stats = {
            "total_evaluated": 0,
            "newly_marked_stale": 0,
            "already_stale": 0,
            "errors": 0,
        }

        try:
            # Get candidate datasources for staleness check
            candidates = await self._get_candidate_datasources()
            stats["total_evaluated"] = len(candidates)

            logger.info(f"Evaluating {len(candidates)} candidate datasources")

            # Fetch usage metrics for all candidates from Elasticsearch
            usage_map = await self._fetch_usage_metrics(candidates)

            # Evaluate each datasource and mark if stale
            for datasource in candidates:
                try:
                    if datasource.lifecycle_state == LifecycleState.STALE:
                        stats["already_stale"] += 1
                        continue

                    is_stale = self._is_datasource_stale(datasource, usage_map.get(datasource.id))

                    if is_stale:
                        self._mark_as_stale(datasource)
                        stats["newly_marked_stale"] += 1
                        logger.info(
                            f"Marked datasource as stale: {datasource.repo_name} "
                            f"(project: {datasource.project_name}, id: {datasource.id})"
                        )

                except Exception as e:
                    stats["errors"] += 1
                    logger.error(
                        f"Error evaluating datasource {datasource.id}: {e}",
                        exc_info=True,
                    )

            await self.session.commit()

            logger.info(
                f"Stale datasource detection completed: "
                f"{stats['newly_marked_stale']} newly marked stale, "
                f"{stats['already_stale']} already stale, "
                f"{stats['errors']} errors"
            )

        except Exception as e:
            logger.error(f"Stale datasource detection failed: {e}", exc_info=True)
            await self.session.rollback()
            raise

        return stats

    async def _get_candidate_datasources(self) -> list[IndexInfo]:
        """Get datasources that should be evaluated for staleness.

        Includes:
        - Active datasources (lifecycle_state = 'active')
        - Completed datasources (not currently processing)
        - Not in error state
        - Not currently being fetched
        - Not in grace period (created > X days ago)

        Returns:
            List of IndexInfo objects
        """
        grace_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=config.STALE_DATASOURCE_GRACE_DAYS)

        statement = (
            select(IndexInfo)
            .where(IndexInfo.lifecycle_state == LifecycleState.ACTIVE)
            .where(IndexInfo.completed == True)  # noqa: E712
            .where(IndexInfo.error == False)  # noqa: E712
            .where(
                or_(
                    IndexInfo.is_fetching == False,  # noqa: E712
                    IndexInfo.is_fetching.is_(None),
                )
            )
            .where(IndexInfo.date < grace_cutoff)
        )

        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def _fetch_usage_metrics(self, datasources: list[IndexInfo]) -> dict[str, Optional[datetime]]:
        """Fetch last usage timestamp for each datasource from Elasticsearch.

        Queries the codemie_metrics_logs index for datasource_tokens_usage metrics,
        aggregating by datasource to get the most recent usage timestamp.

        Args:
            datasources: List of datasources to check

        Returns:
            dict mapping datasource.id -> last_usage_timestamp (or None)
        """
        if not datasources:
            return {}

        datasource_filters, datasource_lookup = self._build_datasource_filters(datasources)
        base_query = self._build_base_usage_query(datasource_filters)

        usage_map: dict[str, Optional[datetime]] = {}

        try:
            after_key: Optional[dict] = None
            while True:
                query_body = self._build_usage_aggregation_query(base_query, after_key)
                result = await self.metrics_repository.execute_aggregation_query(
                    body=query_body,
                    request_timeout=60,
                )
                agg = result.get("aggregations", {}).get("by_datasource", {})
                buckets = agg.get("buckets", [])

                self._merge_usage_buckets(buckets, datasource_lookup, usage_map)

                # Composite aggregations require paging via after_key until either
                # no after_key is returned or the page is empty.
                next_after = agg.get("after_key")
                if not next_after or not buckets:
                    break
                after_key = next_after

            logger.info(f"Found usage metrics for {len(usage_map)} datasources")
            return usage_map

        except Exception as e:
            logger.error(f"Failed to fetch usage metrics from Elasticsearch: {e}", exc_info=True)
            # Return empty map - datasources will be evaluated based on update_date
            return {}

    @staticmethod
    def _build_datasource_filters(
        datasources: list[IndexInfo],
    ) -> tuple[list[dict], dict[tuple[str, str], str]]:
        """Build per-datasource ES bool filters and a (project, repo) -> id lookup."""
        datasource_filters: list[dict] = []
        datasource_lookup: dict[tuple[str, str], str] = {}
        for ds in datasources:
            datasource_lookup[(ds.project_name, ds.repo_name)] = ds.id
            datasource_filters.append(
                {
                    "bool": {
                        "must": [
                            {"term": {"attributes.project.keyword": ds.project_name}},
                            {"term": {"attributes.repo_name.keyword": ds.repo_name}},
                        ]
                    }
                }
            )
        return datasource_filters, datasource_lookup

    @staticmethod
    def _build_base_usage_query(datasource_filters: list[dict]) -> dict:
        return {
            "bool": {
                "must": [{"term": {"metric_name.keyword": "datasource_tokens_usage"}}],
                "should": datasource_filters,
                "minimum_should_match": 1,
            }
        }

    @staticmethod
    def _build_usage_aggregation_query(base_query: dict, after_key: Optional[dict]) -> dict:
        composite_agg: dict = {
            "size": config.STALE_DATASOURCE_BATCH_SIZE,
            "sources": [
                {"project": {"terms": {"field": "attributes.project.keyword"}}},
                {"repo": {"terms": {"field": "attributes.repo_name.keyword"}}},
            ],
        }
        if after_key is not None:
            composite_agg["after"] = after_key

        return {
            "size": 0,
            "query": base_query,
            "aggs": {
                "by_datasource": {
                    "composite": composite_agg,
                    "aggs": {"latest_usage": {"max": {"field": "@timestamp"}}},
                }
            },
        }

    @staticmethod
    def _merge_usage_buckets(
        buckets: list[dict],
        datasource_lookup: dict[tuple[str, str], str],
        usage_map: dict[str, Optional[datetime]],
    ) -> None:
        for bucket in buckets:
            latest_ts_ms = bucket["latest_usage"]["value"]
            if not latest_ts_ms:
                continue
            datasource_id = datasource_lookup.get((bucket["key"]["project"], bucket["key"]["repo"]))
            if datasource_id:
                usage_map[datasource_id] = datetime.fromtimestamp(latest_ts_ms / 1000.0, tz=UTC)

    def _is_datasource_stale(self, datasource: IndexInfo, last_usage: Optional[datetime]) -> bool:
        """Determine if a datasource is stale based on usage and update metrics.

        Staleness criteria (evaluated in order):
        1. If usage metrics exist: stale if last_usage > X days ago
        2. If no usage metrics: stale if update_date > Y days ago
        3. If no update_date: stale (edge case, shouldn't happen)

        Args:
            datasource: The datasource to evaluate
            last_usage: Last usage timestamp from Elasticsearch (if any)

        Returns:
            True if datasource is stale, False otherwise
        """
        now = datetime.now(UTC).replace(tzinfo=None)

        # Criterion 1: Check usage metrics
        if last_usage:
            # Ensure last_usage is naive for comparison
            if last_usage.tzinfo is not None:
                last_usage = last_usage.replace(tzinfo=None)

            days_since_usage = (now - last_usage).days
            is_stale = days_since_usage >= config.STALE_DATASOURCE_NO_USAGE_DAYS

            if is_stale:
                logger.debug(
                    f"Datasource {datasource.id} is stale: "
                    f"no usage for {days_since_usage} days "
                    f"(threshold: {config.STALE_DATASOURCE_NO_USAGE_DAYS})"
                )

            return is_stale

        # Criterion 2: Check update_date as fallback
        if datasource.update_date:
            # Ensure update_date is naive for comparison
            update_date = datasource.update_date
            if update_date.tzinfo is not None:
                update_date = update_date.replace(tzinfo=None)

            days_since_update = (now - update_date).days
            is_stale = days_since_update >= config.STALE_DATASOURCE_NO_UPDATE_DAYS

            if is_stale:
                logger.debug(
                    f"Datasource {datasource.id} is stale: "
                    f"no update for {days_since_update} days "
                    f"(threshold: {config.STALE_DATASOURCE_NO_UPDATE_DAYS}, "
                    f"no usage metrics found)"
                )

            return is_stale

        # Criterion 3: No usage and no update_date (edge case)
        logger.warning(f"Datasource {datasource.id} has no usage metrics and no update_date, marking as stale")
        return True

    def _mark_as_stale(self, datasource: IndexInfo) -> None:
        """Mark a datasource as stale in the database.

        Args:
            datasource: The datasource to mark as stale
        """
        datasource.lifecycle_state = LifecycleState.STALE
        datasource.marked_stale_at = datetime.now(UTC).replace(tzinfo=None)
        self.session.add(datasource)
