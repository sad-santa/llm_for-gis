"""Детерминированная проверка ответа модели после Pydantic."""

from __future__ import annotations

import json
import re
from datetime import datetime

from pydantic import ValidationError

from .reference_catalog import DataTypeHierarchyError, canonicalize_data_type_pair
from .schemas import MetadataFields, MetadataResult


class ModelResponseError(ValueError):
    """Ответ модели нельзя преобразовать в итоговую схему."""


def strip_markdown_fence(raw: str) -> str:
    """Удаляет единственное Markdown-ограждение вокруг JSON, если оно есть."""
    text = raw.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text


def parse_model_response(raw: str, current_year: int | None = None) -> MetadataResult:
    """Разбирает JSON модели, валидирует схему и простые бизнес-правила."""
    try:
        payload = json.loads(strip_markdown_fence(raw))
        missing_fields = _missing_optional_metadata_fields(payload)
        result = MetadataResult.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ModelResponseError(f"Некорректный структурированный ответ: {exc}") from exc
    if missing_fields:
        result.warnings.append(
            "Модель не вернула необязательные поля metadata; "
            "применены значения по умолчанию: "
            + ", ".join(missing_fields)
        )
    return validate_result(result, current_year=current_year)


def _missing_optional_metadata_fields(payload: object) -> list[str]:
    """Возвращает необязательные поля metadata, которые LLM не включила в JSON."""
    if not isinstance(payload, dict):
        return []
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return []
    optional_fields = {
        name for name, field in MetadataFields.model_fields.items() if not field.is_required()
    }
    return sorted(optional_fields - set(metadata))


def validate_result(result: MetadataResult, current_year: int | None = None) -> MetadataResult:
    """Проверяет диапазон года, CRS и наличие доказательства номенклатуры."""
    try:
        data_type, data_subtype = canonicalize_data_type_pair(
            result.metadata.data_type_id,
            result.metadata.data_subtype_id,
        )
    except DataTypeHierarchyError as exc:
        raise ModelResponseError(str(exc)) from exc
    result.metadata.data_type_id = data_type
    result.metadata.data_subtype_id = data_subtype

    upper_year = current_year or datetime.now().year
    invalid_years = [year for year in result.metadata.years if not 1950 <= year <= upper_year]
    if invalid_years:
        raise ModelResponseError(
            f"Год должен находиться между 1950 и {upper_year}: {invalid_years}"
        )

    crs = result.metadata.crs_authid
    if crs and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*:[A-Za-z0-9._-]+", crs):
        result.metadata.crs_authid = None
        result.evidence.pop("crs_authid", None)
        result.warnings.append(
            f"CRS '{crs}' отклонён: ожидается подтверждённый идентификатор AUTHORITY:CODE."
        )

    if result.metadata.nomenclatures and not result.evidence.get("nomenclatures"):
        result.metadata.nomenclatures = []
        result.warnings.append("Номенклатура удалена: модель не привела доказательство.")

    missing_evidence: list[str] = []
    for field_name, value in result.metadata.model_dump().items():
        is_filled = value is not None and value != []
        if is_filled and not result.evidence.get(field_name):
            missing_evidence.append(field_name)
    if missing_evidence:
        raise ModelResponseError(
            "Для заполненных полей отсутствует evidence: " + ", ".join(missing_evidence)
        )
    return result
