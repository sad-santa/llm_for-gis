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
    """Строковые значения, которые извлекает LLM до разрешения справочников."""

    data_type_id: str = Field(
        min_length=1,
        description=(
            "Родительский тип данных — широкая категория документа. Базовые значения: "
            "'Отчет', 'Протокол', 'Первичная геологическая информация' и 'Карты'. "
            "Определи тип по титулу и содержанию и верни точное название из справочника, "
            "а не числовой ID. Поле обязательно и не может быть пустым."
        ),
        examples=["Отчет", "Протокол", "Первичная геологическая информация", "Карты"],
    )
    data_subtype_id: str = Field(
        min_length=1,
        description=(
            "Конкретный подтип документа внутри родительского data_type_id, определённый "
            "по титулу и содержанию. Например, для типа 'Отчет' — "
            "'Геологический отчет, ТЭД, ТЭО, ТЭС', "
            "для 'Протокол' — 'Протокол ГКЗ', для 'Первичная геологическая информация' — "
            "'Журнал бурения', для 'Карты' — 'Разрез', 'План' или 'Схема'. Верни точное "
            "название подтипа из справочника, а не родительский тип и не числовой ID. "
            "Поле обязательно и не может быть пустым."
        ),
        examples=["Геологический отчет, ТЭД, ТЭО, ТЭС", "Протокол ГКЗ", "Разрез"],
    )
    presentation_type: str | None = Field(
        default=None,
        description=(
            "Форма, в которой представлена информация в файле. Верни краткое название "
            "представления, предпочтительно точное действующее значение справочника. "
            "Не подменяй его видом документа. Если форма представления не определена, верни null."
        ),
        examples=["Текст"],
    )
    geo_info_type_id: str | None = Field(
        default=None,
        description=(
            "Тип геологической информации: 'Первичная' для полевых наблюдений и измерений, "
            "'Интерпретированная' для результатов обработки и выводов, "
            "'Первичная и Интерпретированная' при наличии обоих видов либо 'Нет сведений'. "
            "Верни точное название значения справочника, а не числовой ID."
        ),
        examples=["Первичная", "Интерпретированная", "Первичная и Интерпретированная"],
    )
    mineral_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Виды полезных ископаемых или целевые полезные компоненты, "
            "упомянутых в документе. Распознавай нормализованные химические обозначения "
            "элементов независимо от языка исходного названия, например: "
            "медь/copper/Cu -> Cu; золото/gold/Au -> Au; "
            "серебро/silver/Ag -> Ag; кобальт/cobalt/Co -> Co. "
            "Не добавляй концентрации, единицы измерения, поясняющий текст "
            "и повторяющиеся значения. Если информация отсутствует, "
            "возвращай пустой список."
        ),
        examples=[["Cu", "Au", "Ag", "Co"]],
    )
    method_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Методы работ или исследований, результаты которых представлены в документе, "
            "например каротаж скважин, гидрогеология, промыслово-геофизические исследования "
            "или электроразведка. Верни точные названия значений справочника, а не числовые ID. "
            "Не включай метод, если документ лишь упоминает его без соответствующих результатов."
        ),
        examples=[["Электроразведка"], ["Геофизические исследования скважин (каротаж)"]],
    )
    study_kind_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Виды изученности — области работ, к которым относится документ. "
            "Действующие базовые значения: 'Геологическая' и 'Геофизическая'. "
            "Верни точные названия значений справочника, а не числовые ID."
        ),
        examples=[["Геологическая"], ["Геофизическая"]],
    )
    study_subkind_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Подразделы выбранных видов изученности, уточняющие область работ: например, "
            "'Тектоника', 'Минералогия' или 'Петрография' для геологической изученности; "
            "'Магниторазведка' или 'Электроразведка' для геофизической. Каждый подраздел должен "
            "относиться к одному из значений study_kind_ids. Верни названия, а не числовые ID."
        ),
        examples=[["Минералогия"], ["Магниторазведка", "Электроразведка"]],
    )
    exploration_stage_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Стадии разведочных работ, на которых получен документ. Для вида пользования "
            "недрами 'Разведка и добыча' базовые значения: 'ГРР', 'ЭРР' и 'ОРР'. "
            "Верни точные названия стадий из справочника, а не числовые ID."
        ),
        examples=[["ГРР"], ["ЭРР", "ОРР"]],
    )
    nomenclatures: list[str] = Field(
        default_factory=list,
        description=(
            "Номера листов топографической разграфки, к территории которых относится документ. "
            "Сохраняй каноническую запись, например 'N-57', 'N-57-XII', 'N-57-144', "
            "'N-57-144-А' или сдвоенный лист 'P-57,58'. Не добавляй масштаб: он выводится "
            "из номенклатуры. Если номер листа не подтверждён, верни пустой список."
        ),
        examples=[["N-57-XII"], ["P-57,58"]],
    )
    crs_authid: str | None = Field(
        default=None,
        description=(
            "Подтверждённый идентификатор системы координат пространственных данных файла "
            "в формате AUTHORITY:CODE, например 'EPSG:4326'. Используй только технические "
            "метаданные растра или вектора; не определяй CRS по изображению или текстовому "
            "названию проекции. Для документа без подтверждённой системы координат верни null."
        ),
        examples=["EPSG:4326"],
    )
    region_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Субъекты Российской Федерации, к территории которых относится документ, "
            "например 'Камчатский край' или 'Чукотский автономный округ'. Верни точные "
            "названия значений справочника, а не числовые ID."
        ),
        examples=[["Камчатский край"], ["Чукотский автономный округ"]],
    )
    org_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Месторождения, к которым относится документ. Верни точные названия объектов "
            "из справочника месторождений, а не организации, числовые ID или географические "
            "названия, не являющиеся месторождениями."
        ),
    )
    ore_zone_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Рудные зоны, к которым относится документ. Верни точные названия объектов "
            "из справочника, а не числовые ID. Если заполнены org_ids, каждая рудная зона "
            "должна относиться к одному из указанных месторождений."
        ),
    )
    license_numbers: list[str] = Field(
        default_factory=list,
        description=(
            "Номера лицензий на пользование недрами, относящихся к документу, в написании "
            "реестра лицензий. Не добавляй пояснение '(аннулирована)' и другой сопроводительный "
            "текст. Если номер лицензии не указан явно, верни пустой список."
        ),
        examples=[["ПТР 01234 ТЭ"]],
    )
    assign_license_bbox: bool | None = Field(
        default=None,
        description=(
            "Пользовательская настройка присвоения файлу контуров лицензий, а не свойство "
            "документа. Модель не должна определять это значение по содержимому файла; "
            "всегда возвращай null."
        ),
    )
    years: list[int] = Field(
        default_factory=list,
        description=(
            "Год или годы, к которым относится документ. "
            "Документ или отчет может охватывать несколько лет. "
            "Возвращай годы целыми числами в диапазоне от 1800 "
            "до текущего календарного года + 1. "
            "Не добавляй пояснения и повторяющиеся значения. "
            "Если год определить невозможно, возвращай пустой список."
        ),
        examples=[[2020], [2019, 2020]],
    )
    authors: list[str] = Field(
        default_factory=list,
        description=(
            "Авторы или составители документа, карты, схемы либо другого "
            "геологического материала. Ищи сведения об авторстве в начале "
            "или в конце документа, в угловом штампе, "
            "зарамочном оформлении, легенде, под названием и рядом с пометками "
            "'автор', 'составил', 'автор-составитель', 'author', "
            "'compiled by' или 'prepared by'. "
            "Каждого явно указанного автора возвращай отдельной строкой "
            "в формате 'Фамилия И.О.', например 'Иванов И.И.'. "
            "Не придумывай автора по названию организации. "
            "Не добавляй повторяющиеся значения. "
            "Если авторство явно не указано, возвращай пустой список."
        ),
        examples=[
            ["Иванов И.И."],
            ["Иванов И.И.", "Петров П.П."],
        ],
    )

    @field_validator(
        "mineral_ids",
        "method_ids",
        "study_kind_ids",
        "study_subkind_ids",
        "exploration_stage_ids",
        "nomenclatures",
        "region_ids",
        "org_ids",
        "ore_zone_ids",
        "license_numbers",
        "years",
        "authors",
        mode="before",
    )
    @classmethod
    def normalize_null_lists(cls, value: Any) -> Any:
        """Преобразует модельный ``null`` пустого множественного поля в массив."""
        return [] if value is None else value

    @field_validator(
        "data_type_id",
        "data_subtype_id",
        "presentation_type",
        "geo_info_type_id",
        "crs_authid",
        mode="before",
    )
    @classmethod
    def clean_optional_text(cls, value: Any) -> Any:
        """Нормализует пустые значения необязательных строк."""
        return _clean_text(value) if isinstance(value, str) or value is None else value

    @field_validator(
        "mineral_ids",
        "method_ids",
        "study_kind_ids",
        "study_subkind_ids",
        "exploration_stage_ids",
        "nomenclatures",
        "region_ids",
        "org_ids",
        "ore_zone_ids",
        "license_numbers",
        "years",
        "authors",
        mode="after",
    )
    @classmethod
    def clean_lists(cls, value: list[Any]) -> list[Any]:
        """Очищает массивы от пустых значений и повторов."""
        return _unique_nonempty(value)


class ApiMetadataFields(StrictModel):
    """Атрибуты в типах, которые принимает ``POST /api/uploads``."""

    data_type_id: int
    data_subtype_id: int
    presentation_type: str | None = None
    geo_info_type_id: int | None = None
    mineral_ids: list[int] = Field(default_factory=list)
    method_ids: list[int] = Field(default_factory=list)
    study_kind_ids: list[int] = Field(default_factory=list)
    study_subkind_ids: list[int] = Field(default_factory=list)
    exploration_stage_ids: list[int] = Field(default_factory=list)
    nomenclatures: list[str] = Field(default_factory=list)
    crs_authid: str | None = None
    region_ids: list[int] = Field(default_factory=list)
    org_ids: list[int] = Field(default_factory=list)
    ore_zone_ids: list[int] = Field(default_factory=list)
    license_numbers: list[str] = Field(default_factory=list)
    assign_license_bbox: bool | None = None
    years: list[int] = Field(default_factory=list)
    authors: list[str] = Field(default_factory=list)


class MetadataResult(StrictModel):
    """Проверенный строковый ответ LLM до разрешения справочников."""

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


class ApiMetadataResult(StrictModel):
    """Итоговый объект с идентификаторами справочников для backend API."""

    schema_version: str = "1.0"
    source_file: str
    metadata: ApiMetadataFields
    evidence: dict[str, list[str]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
