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

"""Verify workflow_evaluation_service can be imported without the langfuse package installed."""

import importlib
import sys


def test_workflow_evaluation_service_importable_without_langfuse():
    """Module must not require langfuse at import time (langfuse is a transitive dep of codemie-enterprise)."""
    sys.modules.pop("codemie.service.workflow_evaluation_service", None)
    langfuse_mod = sys.modules.pop("langfuse", None)
    try:
        importlib.import_module("codemie.service.workflow_evaluation_service")
    except ImportError as exc:
        raise AssertionError("workflow_evaluation_service must be importable without langfuse installed") from exc
    finally:
        sys.modules.pop("codemie.service.workflow_evaluation_service", None)
        if langfuse_mod is not None:
            sys.modules["langfuse"] = langfuse_mod
