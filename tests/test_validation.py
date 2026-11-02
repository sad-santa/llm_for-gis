"""Проверки разбора и детерминированной валидации JSON."""

import json

import pytest

from local_metadata_extractor.schemas import MetadataFields
from local_metadata_extractor.validation import ModelResponseError, parse_model_response


def response(**metadata_updates: object) -> str:
    """Создаёт полный модельный ответ с указанными значениями."""
    metadata = MetadataFields().model_dump()
    metadata.update(metadata_updates)
    return json.dumps(
        {
            "schema_version": "1.0",
            "source_file": "report.pdf",
            "metadata": metadata,
            "evidence": {},
            "warnings": [],
        },
        ensure_ascii=False,
    )


def test_markdown_fence_is_removed() -> None:
    """Случайное JSON-ограждение модели не мешает разбору."""
    result = parse_model_response(f"```json\n{response()}\n```")
    assert result.source_file == "report.pdf"


def test_invalid_json_is_rejected() -> None:
    """Синтаксически неверный ответ получает предметную ошибку."""
    with pytest.raises(ModelResponseError):
        parse_model_response("not json")


def test_year_range_is_checked() -> None:
    """Годы до 1950 и после текущего года не принимаются."""
    with pytest.raises(ModelResponseError, match="Год должен"):
        parse_model_response(response(year=[1949]), current_year=2026)


def test_nomenclature_without_evidence_is_removed() -> None:
    """Номенклатура без подтверждения не попадает в результат."""
    result = parse_model_response(response(nomenclature=["N-53"]), current_year=2026)
    assert result.metadata.nomenclature == []
    assert "доказательство" in result.warnings[0]


def test_filled_field_requires_evidence() -> None:
    """Любой заполненный факт, кроме удаляемой номенклатуры, требует подтверждения."""
    with pytest.raises(ModelResponseError, match="evidence"):
        parse_model_response(response(methods=["геохимия"]), current_year=2026)


def test_unverified_crs_name_is_removed_instead_of_rejecting_result() -> None:
    """Текстовое название проекции не выдаётся за технический CRS authid."""
    payload = json.loads(response(list_crs_authid="Gauss-Kruger 1942"))
    payload["evidence"] = {"list_crs_authid": ["Подпись на карте"]}

    result = parse_model_response(json.dumps(payload), current_year=2026)

    assert result.metadata.list_crs_authid is None
    assert "list_crs_authid" not in result.evidence
    assert "AUTHORITY:CODE" in result.warnings[0]
