"""Преобразование извлечённых названий в идентификаторы backend-справочников."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeAlias

from .schemas import ApiMetadataFields, ApiMetadataResult, MetadataResult

ReferenceValues: TypeAlias = Mapping[str, int]
ReferenceLookups: TypeAlias = Mapping[str, ReferenceValues]

SCALAR_REFERENCE_FIELDS = (
    "data_type_id",
    "data_subtype_id",
    "geo_info_type_id",
)

LIST_REFERENCE_FIELDS = (
    "mineral_ids",
    "method_ids",
    "study_kind_ids",
    "study_subkind_ids",
    "exploration_stage_ids",
    "region_ids",
    "org_ids",
    "ore_zone_ids",
)


class ReferenceResolutionError(ValueError):
    """Извлечённое название нельзя сопоставить со справочником backend."""


def _normalize_name(value: str) -> str:
    """Нормализует написание для регистронезависимого точного сопоставления."""
    return " ".join(value.strip().casefold().split())


def _normalized_lookup(field_name: str, lookups: ReferenceLookups) -> dict[str, int]:
    """Возвращает нормализованный справочник и выявляет неоднозначные названия."""
    source = lookups.get(field_name)
    if source is None:
        raise ReferenceResolutionError(f"Не передан справочник для поля {field_name}")

    result: dict[str, int] = {}
    for name, item_id in source.items():
        normalized = _normalize_name(name)
        previous = result.get(normalized)
        if previous is not None and previous != item_id:
            raise ReferenceResolutionError(
                f"Неоднозначное название в справочнике {field_name}: {name}"
            )
        result[normalized] = item_id
    return result


def _resolve_name(field_name: str, value: str, lookup: Mapping[str, int]) -> int:
    """Находит один ID по извлечённому названию без попытки угадать значение."""
    item_id = lookup.get(_normalize_name(value))
    if item_id is None:
        raise ReferenceResolutionError(
            f"Значение поля {field_name} отсутствует в справочнике: {value}"
        )
    return item_id


def to_api_result(result: MetadataResult, lookups: ReferenceLookups) -> ApiMetadataResult:
    """Создаёт API-результат, заменяя справочные названия на целочисленные ID."""
    metadata = result.metadata.model_dump()

    for field_name in SCALAR_REFERENCE_FIELDS:
        value = metadata[field_name]
        if value is not None:
            lookup = _normalized_lookup(field_name, lookups)
            metadata[field_name] = _resolve_name(field_name, value, lookup)

    for field_name in LIST_REFERENCE_FIELDS:
        values = metadata[field_name]
        if values:
            lookup = _normalized_lookup(field_name, lookups)
            metadata[field_name] = list(
                dict.fromkeys(_resolve_name(field_name, value, lookup) for value in values)
            )

    return ApiMetadataResult(
        schema_version=result.schema_version,
        source_file=result.source_file,
        metadata=ApiMetadataFields.model_validate(metadata),
        evidence=result.evidence,
        warnings=result.warnings,
    )
