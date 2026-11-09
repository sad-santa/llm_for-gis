"""Проверки определения формата и лёгких экстракторов."""

from pathlib import Path

import pytest

from local_metadata_extractor.config import ExcelExtractor, Settings
from local_metadata_extractor.extractors import (
    ExtractionError,
    UnsupportedFormatError,
    convert_legacy_office,
    detect_format,
    extract_file,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("a.pdf", "pdf"),
        ("a.DOCX", "docx"),
        ("a.xlsx", "xlsx"),
        ("a.PNG", "image"),
        ("a.tiff", "geotiff"),
    ],
)
def test_detect_format(tmp_path: Path, name: str, expected: str) -> None:
    """Поддерживаемые расширения распознаются без учёта регистра."""
    path = tmp_path / name
    path.touch()
    assert detect_format(path) == expected


def test_unsupported_format(tmp_path: Path) -> None:
    """Неизвестное расширение даёт предметную ошибку."""
    path = tmp_path / "data.csv"
    path.touch()
    with pytest.raises(UnsupportedFormatError):
        detect_format(path)


def test_legacy_office_needs_libreoffice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Для старого Office отсутствие soffice объясняется пользователю."""
    path = tmp_path / "old.doc"
    path.touch()
    monkeypatch.setattr("local_metadata_extractor.extractors.shutil.which", lambda _: None)
    with pytest.raises(ExtractionError, match="LibreOffice"):
        convert_legacy_office(path, tmp_path)


def test_extract_excel_compacts_first_sheet_and_limits_rows(tmp_path: Path) -> None:
    """Excel читается без пустых ячеек, повторов и строк за пределом лимита."""
    from openpyxl import Workbook

    path = tmp_path / "report.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Протокол"
    sheet.append(["Заголовок", None, "Заголовок"])
    sheet.append([None, None, None])
    sheet.append(["Au", None, "Ag"])
    sheet.append(["Избаш Ольга, директор"])
    sheet.append(["Не должно попасть"])
    workbook.create_sheet("Второй лист")["A1"] = "Не обрабатывается"
    workbook.save(path)
    workbook.close()

    content = extract_file(
        path,
        tmp_path / "work",
        Settings(max_excel_rows=4, excel_extractor=ExcelExtractor.OPENPYXL),
    )

    assert content.text == (
        "Лист: Протокол\n"
        "Строка 1: Заголовок\n"
        "Строка 3: Au | Ag\n"
        "Строка 4: Избаш Ольга, директор"
    )
    assert content.technical_metadata["selected_sheet"] == "Протокол"
    assert "Остальные листы Excel не обрабатывались." in content.warnings


def test_extract_image_creates_small_preview(tmp_path: Path) -> None:
    """Большая картинка уменьшается до заданной стороны."""
    from PIL import Image

    path = tmp_path / "map.png"
    Image.new("RGB", (200, 100), "white").save(path)
    content = extract_file(path, tmp_path / "work", Settings(max_image_side=64))
    assert content.technical_metadata["width"] == 200
    assert content.technical_metadata["preview_width"] == 64
    assert Path(content.image_paths[0]).is_file()


def test_extract_geotiff_reads_crs(tmp_path: Path) -> None:
    """CRS тестового GeoTIFF извлекается как AUTHORITY:CODE."""
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    path = tmp_path / "map.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=4,
        height=3,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(0, 3, 1, 1),
    ) as dataset:
        dataset.write(np.arange(12, dtype="uint8").reshape(1, 3, 4))
    content = extract_file(path, tmp_path / "work", Settings())
    assert content.technical_metadata["crs_authid"] == "EPSG:4326"
