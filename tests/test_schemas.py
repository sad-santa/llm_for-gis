"""Проверки фиксированной Pydantic-схемы."""

import pytest
from pydantic import ValidationError

from local_metadata_extractor.schemas import ApiMetadataFields, MetadataFields, MetadataResult


def full_metadata() -> dict[str, object]:
    """Возвращает минимальные значения всех обязательных ключей схемы."""
    return MetadataFields().model_dump()


def test_metadata_fields_follow_upload_contract_order() -> None:
    """Поля следуют порядку контракта загрузки из раздела 6.2."""
    expected = [
        "data_subtype_id",
        "presentation_type",
        "geo_info_type_id",
        "mineral_ids",
        "method_ids",
        "study_kind_ids",
        "study_subkind_ids",
        "exploration_stage_ids",
        "nomenclatures",
        "crs_authid",
        "region_ids",
        "org_ids",
        "ore_zone_ids",
        "license_numbers",
        "assign_license_bbox",
        "years",
        "authors",
    ]
    assert list(MetadataFields.model_fields) == expected
    assert list(ApiMetadataFields.model_fields) == expected


def test_extraction_and_api_schemas_use_different_reference_types() -> None:
    """LLM извлекает названия, а API-модель принимает идентификаторы."""
    extraction = MetadataFields.model_json_schema()["properties"]
    api = ApiMetadataFields.model_json_schema()["properties"]

    assert extraction["region_ids"]["items"]["type"] == "string"
    assert api["region_ids"]["items"]["type"] == "integer"
    assert extraction["mineral_ids"]["items"]["type"] == "string"
    assert api["mineral_ids"]["items"]["type"] == "integer"


def test_metadata_cleans_empty_and_duplicate_values() -> None:
    """Пустые строки удаляются, повторения сохраняются только один раз."""
    metadata = MetadataFields(
        presentation_type="  ", authors=["Иванов И.И.", "", " Иванов И.И. "]
    )
    assert metadata.presentation_type is None
    assert metadata.authors == ["Иванов И.И."]


def test_result_requires_every_metadata_key() -> None:
    """Частичный объект модели не маскируется значениями по умолчанию."""
    with pytest.raises(ValidationError, match="Отсутствуют поля metadata"):
        MetadataResult.model_validate(
            {"schema_version": "1.0", "source_file": "x.pdf", "metadata": {"years": []}}
        )


def test_result_rejects_extra_fields() -> None:
    """LLM не может расширять зафиксированную схему."""
    payload = full_metadata()
    payload["invented"] = "value"
    with pytest.raises(ValidationError):
        MetadataResult.model_validate({"source_file": "x.pdf", "metadata": payload})


def test_result_normalizes_common_llm_nulls_and_evidence_strings() -> None:
    """Допустимые вариации LLM приводятся к каноническому JSON."""
    payload = full_metadata()
    payload["method_ids"] = None
    payload["years"] = [2024]

    result = MetadataResult.model_validate(
        {
            "source_file": "x.pdf",
            "metadata": payload,
            "evidence": {"years": "Титульная страница: 2024"},
        }
    )

    assert result.metadata.method_ids == []
    assert result.evidence["years"] == ["Титульная страница: 2024"]
