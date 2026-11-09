"""Проверки частичной иерархии типов и подразделов данных."""

import pytest

from local_metadata_extractor.reference_catalog import (
    DataTypeHierarchyError,
    canonicalize_data_type_pair,
)


@pytest.mark.parametrize(
    ("data_type", "data_subtype"),
    [
        ("Карты", "Схема"),
        ("Протокол", "Протокол ГКЗ"),
        ("Отчет", "Геологический отчет, ТЭД, ТЭО, ТЭС"),
    ],
)
def test_configured_parent_child_pair_is_accepted(data_type: str, data_subtype: str) -> None:
    """Каждая настроенная ветка принимает свой подраздел."""
    assert canonicalize_data_type_pair(data_type, data_subtype) == (data_type, data_subtype)


def test_names_are_canonicalized_case_and_whitespace_insensitively() -> None:
    """Модельное написание приводится к каноническому варианту справочника."""
    assert canonicalize_data_type_pair("  карты ", " СХЕМА ") == ("Карты", "Схема")


def test_child_of_another_parent_is_rejected() -> None:
    """Ранее выбранный подраздел нельзя сохранить после смены родителя."""
    with pytest.raises(DataTypeHierarchyError, match="относится к типу «Протокол»"):
        canonicalize_data_type_pair("Карты", "Протокол ГКЗ")


def test_unknown_child_is_rejected_with_allowed_values() -> None:
    """Ошибка перечисляет варианты текущего родителя для repair-вызова."""
    with pytest.raises(DataTypeHierarchyError, match="Допустимые подразделы:.*«Схема»"):
        canonicalize_data_type_pair("Карты", "Геологическая карта")


def test_unconfigured_parent_keeps_existing_behavior() -> None:
    """Неописанная четвёртая ветка пока остаётся без нового ограничения."""
    assert canonicalize_data_type_pair(
        "Первичная геологическая информация",
        "Журналы бурения",
    ) == ("Первичная геологическая информация", "Журналы бурения")
