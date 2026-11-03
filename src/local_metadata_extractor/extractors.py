"""Определение формата и подготовка файлов для мультимодальной модели."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .config import Settings
from .schemas import ExtractedContent

SUPPORTED_FORMATS = {
    ".pdf": "pdf",
    ".doc": "doc",
    ".docx": "docx",
    ".xls": "xls",
    ".xlsx": "xlsx",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tif": "geotiff",
    ".tiff": "geotiff",
}


class ExtractionError(RuntimeError):
    """Файл поддерживается, но его содержимое извлечь не удалось."""


class UnsupportedFormatError(ValueError):
    """Расширение входного файла не входит в список MVP."""


def detect_format(path: Path) -> str:
    """Определяет поддерживаемый формат по расширению файла."""
    if not path.is_file():
        raise FileNotFoundError(f"Файл не найден: {path}")
    try:
        return SUPPORTED_FORMATS[path.suffix.lower()]
    except KeyError as exc:
        raise UnsupportedFormatError(
            f"Формат {path.suffix or '<без расширения>'} не поддерживается"
        ) from exc


def convert_legacy_office(path: Path, work_dir: Path) -> Path:
    """Конвертирует DOC/XLS через локальный LibreOffice в современный формат."""
    soffice = shutil.which("soffice")
    if not soffice:
        raise ExtractionError(
            "Для обработки .doc и .xls установите LibreOffice и добавьте soffice в PATH."
        )
    target_extension = ".docx" if path.suffix.lower() == ".doc" else ".xlsx"
    command = [
        soffice,
        "--headless",
        "--convert-to",
        target_extension[1:],
        "--outdir",
        str(work_dir),
        str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    converted = work_dir / f"{path.stem}{target_extension}"
    if completed.returncode or not converted.exists():
        details = (completed.stderr or completed.stdout).strip()
        raise ExtractionError(f"LibreOffice не смог конвертировать файл: {details}")
    return converted


def extract_file(path: Path, work_dir: Path, settings: Settings) -> ExtractedContent:
    """Выбирает простой экстрактор и возвращает нормализованное содержимое."""
    source_format = detect_format(path)
    work_dir.mkdir(parents=True, exist_ok=True)
    if source_format in {"doc", "xls"}:
        converted = convert_legacy_office(path, work_dir)
        content = _extract_document(converted, source_format, settings)
        content.source_path = str(path)
        content.technical_metadata["converted_to"] = str(converted)
        return content
    if source_format in {"pdf", "docx", "xlsx"}:
        return _extract_document(path, source_format, settings)
    if source_format == "image":
        return _extract_image(path, work_dir, settings)
    return _extract_geotiff(path, work_dir, settings)


def _extract_document(path: Path, source_format: str, settings: Settings) -> ExtractedContent:
    """Преобразует PDF/Word/Excel в Markdown через Docling, включая OCR PDF."""
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise ExtractionError("Docling не установлен. Выполните uv sync.") from exc

    try:
        if source_format == "pdf":
            options = PdfPipelineOptions(do_ocr=True, do_table_structure=True)
            converter = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
            )
            result = converter.convert(path, page_range=(1, settings.max_pages))
        else:
            converter = DocumentConverter()
            result = converter.convert(path)
        markdown = result.document.export_to_markdown()
    except (RuntimeError, ValueError, OSError) as exc:
        raise ExtractionError(f"Docling не смог обработать {path.name}: {exc}") from exc

    warnings: list[str] = []
    if len(markdown) > settings.max_text_chars:
        markdown = markdown[: settings.max_text_chars]
        warnings.append(f"Markdown обрезан до {settings.max_text_chars} символов.")
    if source_format == "pdf":
        warnings.append(f"Для PDF обработаны страницы не далее {settings.max_pages}.")
    tables = _document_tables(result.document)
    metadata: dict[str, Any] = {"size_bytes": path.stat().st_size}
    if source_format == "xlsx":
        metadata["note"] = "Названия листов и таблицы представлены в Markdown Docling."
    return ExtractedContent(
        source_path=str(path),
        source_format=source_format,
        text=markdown,
        tables=tables,
        technical_metadata=metadata,
        warnings=warnings,
    )


def _document_tables(document: Any) -> list[str]:
    """Экспортирует найденные Docling таблицы без привязки к версии внутреннего API."""
    tables: list[str] = []
    for table in getattr(document, "tables", []):
        try:
            tables.append(table.export_to_markdown(doc=document))
        except (AttributeError, TypeError, ValueError):
            continue
    return tables


def _extract_image(path: Path, work_dir: Path, settings: Settings) -> ExtractedContent:
    """Проверяет изображение, применяет EXIF orientation и создаёт компактное превью."""
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as exc:
        raise ExtractionError("Pillow не установлен. Выполните uv sync.") from exc
    preview_path = work_dir / f"{path.stem}.preview.png"
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source)
            original_size = image.size
            image.thumbnail((settings.max_image_side, settings.max_image_side))
            image.convert("RGB").save(preview_path, format="PNG", optimize=True)
    except (UnidentifiedImageError, OSError) as exc:
        raise ExtractionError(f"Некорректное изображение {path.name}: {exc}") from exc
    return ExtractedContent(
        source_path=str(path),
        source_format="image",
        image_paths=[str(preview_path)],
        technical_metadata={
            "width": original_size[0],
            "height": original_size[1],
            "preview_width": image.width,
            "preview_height": image.height,
        },
    )


def _extract_geotiff(path: Path, work_dir: Path, settings: Settings) -> ExtractedContent:
    """Читает геопривязку GeoTIFF и строит превью без загрузки полного растра."""
    try:
        import numpy as np
        import rasterio
        from PIL import Image
        from rasterio.enums import Resampling
    except ImportError as exc:
        raise ExtractionError("Для GeoTIFF нужны Rasterio, NumPy и Pillow.") from exc

    preview_path = work_dir / f"{path.stem}.preview.png"
    try:
        with rasterio.open(path) as dataset:
            scale = min(1.0, settings.max_image_side / max(dataset.width, dataset.height))
            out_width = max(1, round(dataset.width * scale))
            out_height = max(1, round(dataset.height * scale))
            band_count = min(dataset.count, 3)
            bands = list(range(1, band_count + 1))
            data = dataset.read(
                bands,
                out_shape=(band_count, out_height, out_width),
                resampling=Resampling.bilinear,
                masked=True,
            )
            rgb = _raster_to_uint8(data, np)
            if band_count == 1:
                image = Image.fromarray(rgb[0], mode="L").convert("RGB")
            else:
                image = Image.fromarray(np.moveaxis(rgb, 0, -1), mode="RGB")
            image.save(preview_path, format="PNG", optimize=True)
            crs = dataset.crs.to_authority() if dataset.crs else None
            crs_authid = f"{crs[0]}:{crs[1]}" if crs else None
            metadata = {
                "width": dataset.width,
                "height": dataset.height,
                "band_count": dataset.count,
                "dtype": list(dataset.dtypes),
                "bounds": list(dataset.bounds),
                "transform": list(dataset.transform)[:6],
                "crs_wkt": dataset.crs.to_wkt() if dataset.crs else None,
                "crs_authid": crs_authid,
                "nodata": dataset.nodata,
            }
    except (OSError, ValueError, rasterio.errors.RasterioError) as exc:
        raise ExtractionError(f"Некорректный GeoTIFF {path.name}: {exc}") from exc
    return ExtractedContent(
        source_path=str(path),
        source_format="geotiff",
        image_paths=[str(preview_path)],
        technical_metadata=metadata,
    )


def _raster_to_uint8(data: Any, np: Any) -> Any:
    """Растягивает каждый канал превью по диапазону 2–98 процентов."""
    output = np.zeros(data.shape, dtype=np.uint8)
    for index, band in enumerate(data):
        valid = band.compressed()
        if valid.size == 0:
            continue
        low, high = np.percentile(valid, (2, 98))
        if high <= low:
            high = low + 1
        output[index] = np.clip((band.filled(low) - low) * 255 / (high - low), 0, 255)
    return output


def temporary_work_dir() -> tempfile.TemporaryDirectory[str]:
    """Создаёт автоматически очищаемый каталог промежуточных файлов."""
    return tempfile.TemporaryDirectory(prefix="metadata-extractor-")
