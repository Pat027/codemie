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
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from codemie.datasource.loader.binary.image_loader import ImageLoader, ImageMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pil_mock(
    format: str = "JPEG",
    width: int = 800,
    height: int = 600,
    mode: str = "RGB",
    mime_type: str = "image/jpeg",
    exif: dict | None = None,
) -> MagicMock:
    """Return a context-manager mock that looks like a PIL Image."""
    mock_img = MagicMock()
    mock_img.__enter__ = MagicMock(return_value=mock_img)
    mock_img.__exit__ = MagicMock(return_value=False)
    mock_img.format = format
    mock_img.width = width
    mock_img.height = height
    mock_img.mode = mode
    mock_img.get_format_mimetype.return_value = mime_type
    mock_img.getexif.return_value = exif or {}
    return mock_img


def _make_blob(data: bytes, mimetype: str | None = "image/jpeg") -> MagicMock:
    blob = MagicMock()
    blob.as_bytes.return_value = data
    blob.mimetype = mimetype
    return blob


def _make_storage() -> MagicMock:
    """Return a mock DatasourceFileStorage whose write_file returns a FileObject mock."""
    storage = MagicMock()
    file_obj = MagicMock()
    file_obj.to_encoded_url.return_value = "encoded_url_token"
    storage.write_file.return_value = file_obj
    return storage


# ---------------------------------------------------------------------------
# ImageMetadata.to_text()
# ---------------------------------------------------------------------------


class TestImageMetadataToText:
    def test_file_name_always_first_line(self):
        meta = ImageMetadata(file_name="photo.jpg", file_size=1024)
        assert meta.to_text().startswith("Image: photo.jpg")

    def test_file_size_included(self):
        meta = ImageMetadata(file_name="photo.jpg", file_size=2048)
        assert "File Size: 2048 bytes" in meta.to_text()

    def test_format_included_when_set(self):
        meta = ImageMetadata(file_name="img.png", file_size=0, format="PNG")
        assert "Format: PNG" in meta.to_text()

    def test_dimensions_included_when_both_set(self):
        meta = ImageMetadata(file_name="img.jpg", file_size=0, width=1920, height=1080)
        assert "Dimensions: 1920x1080" in meta.to_text()

    def test_dimensions_skipped_when_missing(self):
        meta = ImageMetadata(file_name="img.jpg", file_size=0, width=None, height=None)
        assert "Dimensions" not in meta.to_text()

    def test_mode_included_when_set(self):
        meta = ImageMetadata(file_name="img.jpg", file_size=0, mode="RGBA")
        assert "Mode: RGBA" in meta.to_text()

    def test_exif_tags_appended(self):
        meta = ImageMetadata(file_name="cam.jpg", file_size=0, exif={"Make": "Canon", "Model": "EOS"})
        text = meta.to_text()
        assert "Make: Canon" in text
        assert "Model: EOS" in text

    def test_optional_fields_absent_when_not_set(self):
        meta = ImageMetadata(file_name="img.jpg", file_size=0)
        text = meta.to_text()
        assert "Format" not in text
        assert "Dimensions" not in text
        assert "Mode" not in text


# ---------------------------------------------------------------------------
# ImageLoader._extract_image_metadata()
# ---------------------------------------------------------------------------


class TestExtractImageMetadata:
    def test_pil_success_populates_format_mime_dimensions_mode(self, tmp_path):
        img_file = tmp_path / "photo.jpg"
        img_file.write_bytes(b"fake")
        mock_img = _make_pil_mock(format="JPEG", width=800, height=600, mode="RGB", mime_type="image/jpeg")

        loader = ImageLoader(str(img_file), MagicMock(), _make_storage())
        with patch("codemie.datasource.loader.binary.image_loader.Image.open", return_value=mock_img):
            meta = loader._extract_image_metadata()

        assert meta.format == "JPEG"
        assert meta.mime_type == "image/jpeg"
        assert meta.width == 800
        assert meta.height == 600
        assert meta.mode == "RGB"

    def test_pil_success_includes_file_size(self, tmp_path):
        img_file = tmp_path / "photo.jpg"
        img_file.write_bytes(b"x" * 500)
        mock_img = _make_pil_mock()

        loader = ImageLoader(str(img_file), MagicMock(), _make_storage())
        with patch("codemie.datasource.loader.binary.image_loader.Image.open", return_value=mock_img):
            meta = loader._extract_image_metadata()

        assert meta.file_size == 500

    def test_pil_failure_falls_back_to_extension_format(self, tmp_path):
        img_file = tmp_path / "broken.gif"
        img_file.write_bytes(b"not-a-gif")

        loader = ImageLoader(str(img_file), MagicMock(), _make_storage())
        with patch(
            "codemie.datasource.loader.binary.image_loader.Image.open",
            side_effect=Exception("corrupted"),
        ):
            meta = loader._extract_image_metadata()

        assert meta.format == "GIF"
        assert meta.width is None
        assert meta.mime_type is None

    def test_pil_failure_logs_warning(self, tmp_path):
        img_file = tmp_path / "broken.jpg"
        img_file.write_bytes(b"bad")

        loader = ImageLoader(str(img_file), MagicMock(), _make_storage())
        with (
            patch(
                "codemie.datasource.loader.binary.image_loader.Image.open",
                side_effect=Exception("oops"),
            ),
            patch("codemie.datasource.loader.binary.image_loader.logger") as mock_logger,
        ):
            loader._extract_image_metadata()

        mock_logger.warning.assert_called_once()
        assert "broken.jpg" in mock_logger.warning.call_args[0][0]

    def test_pil_failure_does_not_raise(self, tmp_path):
        img_file = tmp_path / "bad.png"
        img_file.write_bytes(b"x")

        loader = ImageLoader(str(img_file), MagicMock(), _make_storage())
        with patch(
            "codemie.datasource.loader.binary.image_loader.Image.open",
            side_effect=RuntimeError("fatal"),
        ):
            meta = loader._extract_image_metadata()

        assert meta.file_name == "bad.png"

    def test_get_format_mimetype_used_over_mimetypes_guess(self, tmp_path):
        img_file = tmp_path / "photo.jpg"
        img_file.write_bytes(b"fake")
        mock_img = _make_pil_mock(mime_type="image/jpeg")
        mock_img.get_format_mimetype.return_value = "image/jpeg"

        loader = ImageLoader(str(img_file), MagicMock(), _make_storage())
        with patch("codemie.datasource.loader.binary.image_loader.Image.open", return_value=mock_img):
            meta = loader._extract_image_metadata()

        mock_img.get_format_mimetype.assert_called_once()
        assert meta.mime_type == "image/jpeg"

    def test_mimetypes_guess_used_when_get_format_mimetype_returns_none(self, tmp_path):
        img_file = tmp_path / "photo.jpg"
        img_file.write_bytes(b"fake")
        mock_img = _make_pil_mock()
        mock_img.get_format_mimetype.return_value = None

        loader = ImageLoader(str(img_file), MagicMock(), _make_storage())
        with (
            patch("codemie.datasource.loader.binary.image_loader.Image.open", return_value=mock_img),
            patch(
                "codemie.datasource.loader.binary.image_loader.mimetypes.guess_type",
                return_value=("image/jpeg", None),
            ),
        ):
            meta = loader._extract_image_metadata()

        assert meta.mime_type == "image/jpeg"


# ---------------------------------------------------------------------------
# ImageLoader._extract_exif()
# ---------------------------------------------------------------------------


class TestExtractExif:
    def test_wanted_tags_included(self):
        mock_img = MagicMock()
        mock_img.getexif.return_value = {36867: "2024:01:15 12:00:00", 271: "Canon"}

        fake_tags = {36867: "DateTimeOriginal", 271: "Make"}
        with patch("codemie.datasource.loader.binary.image_loader.TAGS", fake_tags):
            result = ImageLoader._extract_exif(mock_img)

        assert result == {"DateTimeOriginal": "2024:01:15 12:00:00", "Make": "Canon"}

    def test_unwanted_tags_excluded(self):
        mock_img = MagicMock()
        mock_img.getexif.return_value = {305: "Adobe Photoshop"}

        fake_tags = {305: "Software"}
        with patch("codemie.datasource.loader.binary.image_loader.TAGS", fake_tags):
            result = ImageLoader._extract_exif(mock_img)

        assert "Software" not in result

    def test_non_string_values_excluded(self):
        mock_img = MagicMock()
        mock_img.getexif.return_value = {306: 20240101}

        fake_tags = {306: "DateTime"}
        with patch("codemie.datasource.loader.binary.image_loader.TAGS", fake_tags):
            result = ImageLoader._extract_exif(mock_img)

        assert result == {}

    def test_empty_exif_returns_empty_dict(self):
        mock_img = MagicMock()
        mock_img.getexif.return_value = {}
        assert ImageLoader._extract_exif(mock_img) == {}


# ---------------------------------------------------------------------------
# ImageLoader._extension_fallback()
# ---------------------------------------------------------------------------


class TestExtensionFallback:
    def test_returns_uppercase_extension(self):
        assert ImageLoader._extension_fallback("photo.gif") == "GIF"

    def test_returns_uppercase_for_jpeg(self):
        assert ImageLoader._extension_fallback("scan.jpeg") == "JPEG"

    def test_no_extension_returns_unknown(self):
        assert ImageLoader._extension_fallback("noextension") == "UNKNOWN"

    def test_dot_only_name_returns_unknown(self):
        assert ImageLoader._extension_fallback(".hidden") == "UNKNOWN"


# ---------------------------------------------------------------------------
# ImageLoader.lazy_load()
# ---------------------------------------------------------------------------


class TestLazyLoad:
    def _make_loader(self, tmp_path, parser=None):
        img_file = tmp_path / "photo.jpg"
        img_file.write_bytes(b"fake-image-bytes")
        return ImageLoader(str(img_file), parser or MagicMock(), _make_storage()), img_file

    def test_parser_doc_gets_metadata_text_appended(self, tmp_path):
        mock_parser = MagicMock()
        loader, _ = self._make_loader(tmp_path, parser=mock_parser)

        meta = ImageMetadata(file_name="photo.jpg", file_size=16, format="JPEG", width=100, height=100, mode="RGB")
        mock_doc = Document(page_content="OCR text", metadata={})

        mock_parser.lazy_parse.return_value = iter([mock_doc])

        with (
            patch.object(loader, "_extract_image_metadata", return_value=meta),
            patch("codemie.datasource.loader.binary.image_loader.Blob.from_path", return_value=MagicMock()),
            patch.object(loader, "_store_image", return_value=None),
        ):
            docs = list(loader.lazy_load())

        assert len(docs) == 1
        assert "OCR text" in docs[0].page_content
        assert "Format: JPEG" in docs[0].page_content

    def test_file_path_metadata_set_to_loader_path(self, tmp_path):
        mock_parser = MagicMock()
        loader, img_file = self._make_loader(tmp_path, parser=mock_parser)

        meta = ImageMetadata(file_name="photo.jpg", file_size=16)
        mock_doc = Document(page_content="text", metadata={})
        mock_parser.lazy_parse.return_value = iter([mock_doc])

        with (
            patch.object(loader, "_extract_image_metadata", return_value=meta),
            patch("codemie.datasource.loader.binary.image_loader.Blob.from_path", return_value=MagicMock()),
            patch.object(loader, "_store_image", return_value=None),
        ):
            docs = list(loader.lazy_load())

        assert docs[0].metadata["file_path"] == str(img_file)

    def test_source_not_set_by_loader(self, tmp_path):
        """source is the caller's responsibility (set in extract_documents_from_bytes)."""
        mock_parser = MagicMock()
        loader, _ = self._make_loader(tmp_path, parser=mock_parser)

        meta = ImageMetadata(file_name="photo.jpg", file_size=16)
        mock_doc = Document(page_content="text", metadata={})
        mock_parser.lazy_parse.return_value = iter([mock_doc])

        with (
            patch.object(loader, "_extract_image_metadata", return_value=meta),
            patch("codemie.datasource.loader.binary.image_loader.Blob.from_path", return_value=MagicMock()),
            patch.object(loader, "_store_image", return_value=None),
        ):
            docs = list(loader.lazy_load())

        assert "source" not in docs[0].metadata

    def test_store_image_called_once_for_multiple_docs(self, tmp_path):
        mock_parser = MagicMock()
        loader, _ = self._make_loader(tmp_path, parser=mock_parser)

        meta = ImageMetadata(file_name="photo.jpg", file_size=16)
        docs_in = [Document(page_content="a", metadata={}), Document(page_content="b", metadata={})]
        mock_parser.lazy_parse.return_value = iter(docs_in)

        with (
            patch.object(loader, "_extract_image_metadata", return_value=meta),
            patch("codemie.datasource.loader.binary.image_loader.Blob.from_path", return_value=MagicMock()),
            patch.object(loader, "_store_image", return_value=None) as mock_store,
        ):
            list(loader.lazy_load())

        assert mock_store.call_count == 1

    def test_empty_page_content_doc_gets_only_metadata_text(self, tmp_path):
        mock_parser = MagicMock()
        loader, _ = self._make_loader(tmp_path, parser=mock_parser)

        meta = ImageMetadata(file_name="photo.jpg", file_size=16, format="JPEG")
        mock_doc = Document(page_content="", metadata={})
        mock_parser.lazy_parse.return_value = iter([mock_doc])

        with (
            patch.object(loader, "_extract_image_metadata", return_value=meta),
            patch("codemie.datasource.loader.binary.image_loader.Blob.from_path", return_value=MagicMock()),
            patch.object(loader, "_store_image", return_value=None),
        ):
            docs = list(loader.lazy_load())

        assert docs[0].page_content == meta.to_text()


# ---------------------------------------------------------------------------
# ImageLoader._store_image()
# ---------------------------------------------------------------------------


class TestStoreImage:
    def _make_loader(self, tmp_path, storage=None) -> ImageLoader:
        img_file = tmp_path / "photo.jpg"
        img_file.write_bytes(b"fake")
        return ImageLoader(str(img_file), MagicMock(), storage or _make_storage())

    def test_returns_dict_with_encoded_url_and_mime(self, tmp_path):
        file_bytes = b"small-image"
        blob = _make_blob(file_bytes)
        meta = ImageMetadata(file_name="photo.jpg", file_size=len(file_bytes), mime_type="image/jpeg")

        storage = MagicMock()
        file_obj = MagicMock()
        file_obj.to_encoded_url.return_value = "encoded_url_token"
        storage.write_file.return_value = file_obj

        loader = self._make_loader(tmp_path, storage=storage)
        result = loader._store_image(blob, meta)

        assert result is not None
        assert result["image_encoded_url"] == "encoded_url_token"
        assert result["image_mime_type"] == "image/jpeg"

    def test_write_file_called_with_correct_args(self, tmp_path):
        file_bytes = b"data"
        blob = _make_blob(file_bytes)
        meta = ImageMetadata(file_name="photo.jpg", file_size=len(file_bytes), mime_type="image/jpeg")

        storage = MagicMock()
        storage.write_file.return_value = MagicMock()

        loader = self._make_loader(tmp_path, storage=storage)
        loader._store_image(blob, meta)

        storage.write_file.assert_called_once_with(
            name="photo.jpg",
            mime_type="image/jpeg",
            content=file_bytes,
        )

    def test_mime_type_fallback_to_blob_mimetype(self, tmp_path):
        file_bytes = b"data"
        blob = _make_blob(file_bytes, mimetype="image/png")
        meta = ImageMetadata(file_name="img.png", file_size=len(file_bytes), mime_type=None)

        storage = MagicMock()
        file_obj = MagicMock()
        file_obj.to_encoded_url.return_value = "token"
        storage.write_file.return_value = file_obj

        loader = self._make_loader(tmp_path, storage=storage)
        result = loader._store_image(blob, meta)

        assert result is not None
        assert result["image_mime_type"] == "image/png"
        storage.write_file.assert_called_once_with(name="img.png", mime_type="image/png", content=file_bytes)

    def test_mime_type_ultimate_fallback_to_jpeg(self, tmp_path):
        file_bytes = b"data"
        blob = _make_blob(file_bytes, mimetype=None)
        blob.mimetype = None
        meta = ImageMetadata(file_name="img.bin", file_size=len(file_bytes), mime_type=None)

        storage = MagicMock()
        file_obj = MagicMock()
        file_obj.to_encoded_url.return_value = "token"
        storage.write_file.return_value = file_obj

        loader = self._make_loader(tmp_path, storage=storage)
        result = loader._store_image(blob, meta)

        assert result is not None
        assert result["image_mime_type"] == "image/jpeg"

    def test_returns_none_when_storage_raises(self, tmp_path):
        blob = _make_blob(b"data")
        meta = ImageMetadata(file_name="photo.jpg", file_size=4, mime_type="image/jpeg")

        storage = MagicMock()
        storage.write_file.side_effect = OSError("storage unavailable")

        loader = self._make_loader(tmp_path, storage=storage)
        result = loader._store_image(blob, meta)

        assert result is None

    def test_storage_error_logs_warning(self, tmp_path):
        blob = _make_blob(b"data")
        meta = ImageMetadata(file_name="photo.jpg", file_size=4, mime_type="image/jpeg")

        storage = MagicMock()
        storage.write_file.side_effect = OSError("storage unavailable")

        loader = self._make_loader(tmp_path, storage=storage)
        with patch("codemie.datasource.loader.binary.image_loader.logger") as mock_logger:
            loader._store_image(blob, meta)

        mock_logger.warning.assert_called_once()
        assert "photo.jpg" in mock_logger.warning.call_args[0][0]

    def test_no_file_size_limit_for_large_files(self, tmp_path):
        """Unlike the old _build_inline_image_meta, _store_image has no size cap."""
        file_bytes = b"x" * (15 * 1024 * 1024)  # 15 MB
        blob = _make_blob(file_bytes)
        meta = ImageMetadata(file_name="large.jpg", file_size=len(file_bytes), mime_type="image/jpeg")

        storage = MagicMock()
        file_obj = MagicMock()
        file_obj.to_encoded_url.return_value = "big_token"
        storage.write_file.return_value = file_obj

        loader = self._make_loader(tmp_path, storage=storage)
        result = loader._store_image(blob, meta)

        assert result is not None
        assert result["image_encoded_url"] == "big_token"
        storage.write_file.assert_called_once()


# ---------------------------------------------------------------------------
# ImageLoader.lazy_load() — size limit
# ---------------------------------------------------------------------------


class TestLazyLoadSizeLimit:
    def _make_loader(self, tmp_path, file_size_bytes: int, parser=None) -> ImageLoader:
        img_file = tmp_path / "photo.jpg"
        img_file.write_bytes(b"x" * file_size_bytes)
        return ImageLoader(str(img_file), parser or MagicMock(), _make_storage())

    def test_raises_skipped_file_exception_when_over_limit(self, tmp_path):
        from codemie.datasource.exceptions import SkippedFileException

        loader = self._make_loader(tmp_path, file_size_bytes=100)
        with patch.object(ImageLoader, "_MAX_SIZE_BYTES", 50):
            with pytest.raises(SkippedFileException):
                list(loader.lazy_load())

    def test_logs_info_when_skipping(self, tmp_path):
        from codemie.datasource.exceptions import SkippedFileException

        loader = self._make_loader(tmp_path, file_size_bytes=100)
        with (
            patch.object(ImageLoader, "_MAX_SIZE_BYTES", 50),
            patch("codemie.datasource.loader.binary.image_loader.logger") as mock_logger,
        ):
            with pytest.raises(SkippedFileException):
                list(loader.lazy_load())

        mock_logger.info.assert_called_once()
        assert "photo.jpg" in mock_logger.info.call_args[0][0]

    def test_processes_normally_when_within_limit(self, tmp_path):
        mock_parser = MagicMock()
        mock_doc = Document(page_content="OCR text", metadata={})
        mock_parser.lazy_parse.return_value = iter([mock_doc])

        loader = self._make_loader(tmp_path, file_size_bytes=100, parser=mock_parser)
        meta = ImageMetadata(file_name="photo.jpg", file_size=100)

        with (
            patch.object(ImageLoader, "_MAX_SIZE_BYTES", 1000),
            patch.object(loader, "_extract_image_metadata", return_value=meta),
            patch("codemie.datasource.loader.binary.image_loader.Blob.from_path", return_value=MagicMock()),
            patch.object(loader, "_store_image", return_value=None),
        ):
            docs = list(loader.lazy_load())

        assert len(docs) == 1
