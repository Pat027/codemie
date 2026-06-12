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

"""Unit tests for VsdxLoader (modern Visio .vsdx diagrams)."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from codemie.datasource.loader.file_extraction_utils import LOADERS, is_binary_extractable
from codemie.datasource.loader.vsdx_loader import VsdxLoader

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample.vsdx")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _shape(text):
    return SimpleNamespace(text=text)


def _page(name, shape_texts):
    return SimpleNamespace(name=name, all_shapes=[_shape(t) for t in shape_texts])


def _patch_visio(pages):
    """Patch vsdx.VisioFile so the context manager yields a fake document with given pages."""
    visio = SimpleNamespace(pages=pages)
    mock_cls = MagicMock()
    mock_cls.return_value.__enter__.return_value = visio
    mock_cls.return_value.__exit__.return_value = False
    return patch("vsdx.VisioFile", mock_cls)


# ---------------------------------------------------------------------------
# Real fixture (end-to-end against a genuine .vsdx file)
# ---------------------------------------------------------------------------


def test_extracts_shape_text_from_real_vsdx():
    docs = list(VsdxLoader(FIXTURE).lazy_load())
    assert len(docs) == 1
    assert isinstance(docs[0], Document)
    assert "RECTANGLE" in docs[0].page_content
    assert "CIRCLE" in docs[0].page_content


def test_real_vsdx_metadata():
    doc = list(VsdxLoader(FIXTURE).lazy_load())[0]
    assert doc.metadata["source"] == "sample.vsdx"
    assert doc.metadata["file_name"] == "sample.vsdx"
    assert doc.metadata["page_number"] == 1
    assert doc.metadata["page_name"] == "Page-1"


# ---------------------------------------------------------------------------
# Page handling (mocked parser boundary)
# ---------------------------------------------------------------------------


def test_yields_one_document_per_page_with_text():
    pages = [_page("Flow", ["Start", "End"]), _page("Detail", ["Step A"])]
    with _patch_visio(pages):
        docs = list(VsdxLoader("diagram.vsdx").lazy_load())
    assert len(docs) == 2
    assert docs[0].metadata["page_name"] == "Flow"
    assert docs[1].metadata["page_name"] == "Detail"
    assert docs[1].metadata["page_number"] == 2


def test_page_text_and_name_in_content():
    with _patch_visio([_page("Architecture", ["Service", "Database"])]):
        docs = list(VsdxLoader("diagram.vsdx").lazy_load())
    content = docs[0].page_content
    assert content.startswith("# Architecture")
    assert "Service" in content
    assert "Database" in content


def test_skips_pages_without_text():
    pages = [_page("Empty", ["", "   "]), _page("HasText", ["Real"])]
    with _patch_visio(pages):
        docs = list(VsdxLoader("diagram.vsdx").lazy_load())
    assert len(docs) == 1
    assert docs[0].metadata["page_name"] == "HasText"


def test_no_documents_when_diagram_has_no_text():
    with _patch_visio([_page("Blank", []), _page("AlsoBlank", [None])]):
        docs = list(VsdxLoader("diagram.vsdx").lazy_load())
    assert docs == []


# ---------------------------------------------------------------------------
# Graceful failure
# ---------------------------------------------------------------------------


def test_yields_nothing_when_visiofile_raises():
    mock_cls = MagicMock()
    mock_cls.return_value.__enter__.side_effect = Exception("corrupt file")
    with patch("vsdx.VisioFile", mock_cls):
        docs = list(VsdxLoader("broken.vsdx").lazy_load())
    assert docs == []


def test_yields_nothing_when_vsdx_not_installed():
    # Simulate the import failing inside lazy_load
    with patch.dict("sys.modules", {"vsdx": None}):
        docs = list(VsdxLoader("diagram.vsdx").lazy_load())
    assert docs == []


# ---------------------------------------------------------------------------
# Registration / dispatch
# ---------------------------------------------------------------------------


def test_vsdx_registered_in_loaders():
    assert LOADERS["vsdx"] is VsdxLoader


def test_vsdx_is_binary_extractable():
    assert is_binary_extractable("diagram.vsdx") is True
