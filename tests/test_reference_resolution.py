"""Проверки преобразования строкового ответа LLM в контракт backend API."""

import pytest

from local_metadata_extractor.reference_resolution import (
    ReferenceResolutionError,
    to_api_result,
)
from local_metadata_extractor.schemas import MetadataFields, MetadataResult


def test_reference_names_are_resolved_to_api_ids() -> None:
    """Названия справочных значений заменяются целочисленными ID."""
    result = MetadataResult(
        source_file="map.pdf",
        metadata=MetadataFields(
            data_type_id="Отчет",
            data_subtype_id="Геологический отчет, ТЭД, ТЭО, ТЭС",
            geo_info_type_id="Первичная",
            mineral_ids=["Au", "Cu"],
            method_ids=["Электроразведка"],
            region_ids=["Камчатский край"],
            years=[2020],
            authors=["Иванов И.И."],
        ),
    )
    lookups = {
        "data_type_id": {"Отчет": 5},
        "data_subtype_id": {"Геологический отчет, ТЭД, ТЭО, ТЭС": 10},
        "geo_info_type_id": {"Первичная": 20},
        "mineral_ids": {"Au": 1, "Cu": 2},
        "method_ids": {"Электроразведка": 3},
        "region_ids": {"Камчатский край": 4},
    }

    api_result = to_api_result(result, lookups)

    assert api_result.metadata.data_type_id == 5
    assert api_result.metadata.data_subtype_id == 10
    assert api_result.metadata.geo_info_type_id == 20
    assert api_result.metadata.mineral_ids == [1, 2]
    assert api_result.metadata.method_ids == [3]
    assert api_result.metadata.region_ids == [4]
    assert api_result.metadata.years == [2020]
    assert api_result.metadata.authors == ["Иванов И.И."]


def test_reference_resolution_is_case_and_whitespace_insensitive() -> None:
    """Точное сопоставление допускает различия регистра и лишние пробелы."""
    result = MetadataResult(
        source_file="map.pdf",
        metadata=MetadataFields(
            data_type_id="Отчет",
            data_subtype_id="Геологический отчет, ТЭД, ТЭО, ТЭС",
            region_ids=["  КАМЧАТСКИЙ   КРАЙ "],
        ),
    )

    api_result = to_api_result(
        result,
        {
            "data_type_id": {"Отчет": 5},
            "data_subtype_id": {"Геологический отчет, ТЭД, ТЭО, ТЭС": 10},
            "region_ids": {"Камчатский край": 4},
        },
    )

    assert api_result.metadata.region_ids == [4]


def test_unknown_reference_name_is_not_silently_dropped() -> None:
    """Неизвестное название вызывает ошибку вместо придуманного ID."""
    result = MetadataResult(
        source_file="map.pdf",
        metadata=MetadataFields(
            data_type_id="Отчет",
            data_subtype_id="Геологический отчет, ТЭД, ТЭО, ТЭС",
            region_ids=["Неизвестный регион"],
        ),
    )

    with pytest.raises(ReferenceResolutionError, match="отсутствует в справочнике"):
        to_api_result(
            result,
            {
                "data_type_id": {"Отчет": 5},
                "data_subtype_id": {"Геологический отчет, ТЭД, ТЭО, ТЭС": 10},
                "region_ids": {"Камчатский край": 4},
            },
        )
