"""Частичные иерархические справочники, передаваемые модели до генерации."""

from __future__ import annotations

from collections.abc import Mapping

DATA_TYPE_SUBTYPES: Mapping[str, tuple[str, ...]] = {
    "Карты": (
        "План",
        "Приложение",
        "Разрез",
        "Схема",
    ),
    "Протокол": (
        "Протокол ГКЗ",
        "Протокол НТС",
        "Протокол ТКЗ",
        "Протокол ТКР",
        "Протокол ТС",
        "Протокол ЦКЗ",
        "Протокол ЦКР",
        "Протокол ЭТС",
    ),
    "Отчет": (
        "Баланс",
        "Бюллетень геологических материалов",
        "Геологическая информация отчетов НИР",
        "Геологический отчет, ТЭД, ТЭО, ТЭС",
        "Годовой отчет организации",
        "Дело скважины",
        "Другой документ негеологического содержания",
        "Изданные балансы, справочники",
        "Информационный отчет по лицензии",
        "Материалы по подсчету запасов",
        "Мониторинг по лицензии",
        "Свидетельство об открытии месторождения",
    ),
}


class DataTypeHierarchyError(ValueError):
    """Тип данных и его подраздел не образуют разрешённую пару."""


def _normalize_name(value: str) -> str:
    """Нормализует регистр и пробелы для точного сравнения названий."""
    return " ".join(value.strip().casefold().split())


def canonicalize_data_type_pair(data_type: str, data_subtype: str) -> tuple[str, str]:
    """Проверяет настроенную ветку и возвращает её канонические названия."""
    canonical_types = {_normalize_name(name): name for name in DATA_TYPE_SUBTYPES}
    canonical_type = canonical_types.get(_normalize_name(data_type))
    if canonical_type is None:
        # Для ещё не описанных типов сохраняется прежняя свободная логика.
        return data_type.strip(), data_subtype.strip()

    allowed_subtypes = DATA_TYPE_SUBTYPES[canonical_type]
    canonical_subtypes = {_normalize_name(name): name for name in allowed_subtypes}
    canonical_subtype = canonical_subtypes.get(_normalize_name(data_subtype))
    if canonical_subtype is None:
        owners = [
            parent
            for parent, children in DATA_TYPE_SUBTYPES.items()
            if any(_normalize_name(child) == _normalize_name(data_subtype) for child in children)
        ]
        owner_hint = f" Подраздел относится к типу «{owners[0]}»." if owners else ""
        allowed = ", ".join(f"«{name}»" for name in allowed_subtypes)
        raise DataTypeHierarchyError(
            f"Подраздел «{data_subtype}» не относится к типу «{canonical_type}»."
            f"{owner_hint} Допустимые подразделы: {allowed}."
        )
    return canonical_type, canonical_subtype


def render_data_type_hierarchy() -> str:
    """Формирует компактный человекочитаемый справочник для prompt модели."""
    lines = [
        "ОБЯЗАТЕЛЬНАЯ СВЯЗЬ ТИПА И ПОДРАЗДЕЛА:",
        "Выбери ровно один тип и один подраздел из его ветки.",
        "Используй названия дословно и не создавай новые варианты.",
    ]
    for data_type, subtypes in DATA_TYPE_SUBTYPES.items():
        lines.append(f"{data_type}:")
        lines.extend(f"- {subtype}" for subtype in subtypes)
    lines.append(
        "Для типов, которых нет в этом частичном справочнике, следуй описанию JSON Schema."
    )
    return "\n".join(lines)
