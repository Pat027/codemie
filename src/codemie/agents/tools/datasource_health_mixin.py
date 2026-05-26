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

from codemie.configs import logger
from codemie.rest_api.models.index import IndexInfo


class DatasourceHealthMixin:
    @staticmethod
    def _classify_health(index_info: IndexInfo) -> str:
        if index_info.error:
            return "FAILED"
        if not index_info.completed:
            return "REINDEXING"
        if (
            index_info.last_reindex_triggered_at
            and index_info.update_date
            and index_info.last_reindex_triggered_at > index_info.update_date
        ):
            return "STALE"
        return "OK"

    def _build_health_notice(self) -> str:
        if not self.index_info:
            return ""
        status = self._classify_health(self.index_info)
        if status == "FAILED":
            error_detail = f" Error: {self.index_info.text}." if self.index_info.text else ""
            return (
                f"The datasource '{self.index_info.repo_name}' last indexing attempt failed.{error_detail} "
                "Results may be incomplete, stale, or missing entirely.\n\n"
            )
        if status == "REINDEXING":
            return (
                f"The datasource '{self.index_info.repo_name}' is currently being re-indexed. "
                "Results may be incomplete or reflect outdated data.\n\n"
            )
        if status == "STALE":
            return (
                f"The datasource '{self.index_info.repo_name}' had a scheduled reindex that did not complete. "
                "Results may reflect outdated data.\n\n"
            )
        return ""

    @staticmethod
    def _build_description_health_prefix(index_info: IndexInfo) -> str:
        status = DatasourceHealthMixin._classify_health(index_info)
        if status == "FAILED":
            return (
                "[DATASOURCE STATUS: FAILED] "
                "Results may be incomplete or missing. "
                "Always inform the user about potential data quality issues. "
            )
        if status == "REINDEXING":
            return (
                "[DATASOURCE STATUS: REINDEXING] "
                "This datasource is currently being re-indexed — results may be incomplete. "
                "Always inform the user that data may be partial. "
            )
        if status == "STALE":
            return (
                "[DATASOURCE STATUS: STALE] "
                "A scheduled reindex did not complete — results may be outdated. "
                "Always inform the user that data may not reflect recent changes. "
            )
        return ""

    def _wrap_result(self, result, notice: str):
        if not notice:
            return result
        if isinstance(result, str):
            return notice + result
        logger.warning(f"Health notice suppressed: result type is {type(result).__name__}, not str")
        return result
