"""Pydantic-схемы входных данных и итогового JSON."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _clean_text(value: str | None) -> str | None:
    """Убирает пробелы и превращает пустую строку в ``None``."""
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _unique_nonempty(values: list[Any]) -> list[Any]:
    """Удаляет пустые и повторяющиеся элементы, сохраняя исходный порядок."""
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        marker = repr(value)
        if marker not in seen:
            seen.add(marker)
            result.append(value)
    return result


class StrictModel(BaseModel):
    """Базовая модель, запрещающая неописанные поля."""

    model_config = ConfigDict(extra="forbid")


class ExtractedContent(StrictModel):
    """Содержимое файла, подготовленное для передачи локальной модели."""

    source_path: str
    source_format: str
    text: str = ""
    tables: list[str] = Field(default_factory=list)
    image_paths: list[str] = Field(default_factory=list)
    technical_metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class MetadataFields(StrictModel):
    """Фиксированные графы метаданных из исходного технического задания."""

    presentation_type_label: str | None = None
    data_type_label: str | None = None
    subsection_type_label: str | None = None
    vid_pi: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    type_geo_inf: str | None = None
    area_label: list[str] = Field(default_factory=list)
    subsection_area_label: list[str] = Field(default_factory=list)
    stage_label: str | None = None
    stadium_label: str | None = None
    nomenclature: list[str] = Field(default_factory=list)
    scale_ratio: list[str] = Field(default_factory=list)
    list_crs_authid: str | None = None
    region_label: list[str] = Field(default_factory=list)
    organization_name: list[str] = Field(default_factory=list)
    ore_zone_label: list[str] = Field(default_factory=list)
    license_number: list[str] = Field(default_factory=list)
    year: list[int] = Field(default_factory=list)
    author_name: list[str] = Field(default_factory=list)

    @field_validator(
        "vid_pi",
        "methods",
        "area_label",
        "subsection_area_label",
        "nomenclature",
        "scale_ratio",
        "region_label",
        "organization_name",
        "ore_zone_label",
        "license_number",
        "year",
        "author_name",
        mode="before",
    )
    @classmethod
    def normalize_null_lists(cls, value: Any) -> Any:
        """Преобразует модельный ``null`` пустого множественного поля в массив."""
        return [] if value is None else value

    @field_validator(
        "presentation_type_label",
        "data_type_label",
        "subsection_type_label",
        "type_geo_inf",
        "stage_label",
        "stadium_label",
        "list_crs_authid",
        mode="before",
    )
    @classmethod
    def clean_optional_text(cls, value: Any) -> Any:
        """Нормализует пустые значения необязательных строк."""
        return _clean_text(value) if isinstance(value, str) or value is None else value

    @field_validator(
        "vid_pi",
        "methods",
        "area_label",
        "subsection_area_label",
        "nomenclature",
        "scale_ratio",
        "region_label",
        "organization_name",
        "ore_zone_label",
        "license_number",
        "year",
        "author_name",
        mode="after",
    )
    @classmethod
    def clean_lists(cls, value: list[Any]) -> list[Any]:
        """Очищает массивы от пустых значений и повторов."""
        return _unique_nonempty(value)


class MetadataResult(StrictModel):
    """Проверенный итоговый объект, который сохраняется как JSON."""

    schema_version: str = "1.0"
    source_file: str
    metadata: MetadataFields
    evidence: dict[str, list[str]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def require_all_metadata_keys(cls, value: Any) -> Any:
        """Требует присутствия каждой фиксированной графы именно в ответе LLM."""
        if isinstance(value, dict) and isinstance(value.get("metadata"), dict):
            missing = set(MetadataFields.model_fields) - set(value["metadata"])
            if missing:
                raise ValueError(f"Отсутствуют поля metadata: {', '.join(sorted(missing))}")
        return value

    @field_validator("evidence", mode="before")
    @classmethod
    def normalize_evidence_lists(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        result = {}

        for key, items in value.items():
            if isinstance(items, str):
                result[key] = [items]

            elif items is None:
                result[key] = []

            elif isinstance(items, (int, float)) and not isinstance(items, bool):
                result[key] = [str(items)]

            else:
                result[key] = items

        return result

    @field_validator("evidence", mode="after")
    @classmethod
    def clean_evidence(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        """Очищает доказательства и запрещает ключи вне схемы метаданных."""
        allowed = set(MetadataFields.model_fields)
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Неизвестные поля evidence: {', '.join(sorted(unknown))}")
        return {key: _unique_nonempty(items) for key, items in value.items() if items}
