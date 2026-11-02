"""Проверки фиксированной Pydantic-схемы."""

import pytest
from pydantic import ValidationError

from local_metadata_extractor.schemas import MetadataFields, MetadataResult


def full_metadata() -> dict[str, object]:
    """Возвращает минимальные значения всех обязательных ключей схемы."""
    return MetadataFields().model_dump()


def test_metadata_cleans_empty_and_duplicate_values() -> None:
    """Пустые строки удаляются, повторения сохраняются только один раз."""
    metadata = MetadataFields(presentation_type_label="  ", methods=["геохимия", "", " геохимия "])
    assert metadata.presentation_type_label is None
    assert metadata.methods == ["геохимия"]


def test_result_requires_every_metadata_key() -> None:
    """Частичный объект модели не маскируется значениями по умолчанию."""
    with pytest.raises(ValidationError, match="Отсутствуют поля metadata"):
        MetadataResult.model_validate(
            {"schema_version": "1.0", "source_file": "x.pdf", "metadata": {"year": []}}
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
    payload["methods"] = None
    payload["year"] = [2024]

    result = MetadataResult.model_validate(
        {
            "source_file": "x.pdf",
            "metadata": payload,
            "evidence": {"year": "Титульная страница: 2024"},
        }
    )

    assert result.metadata.methods == []
    assert result.evidence["year"] == ["Титульная страница: 2024"]
