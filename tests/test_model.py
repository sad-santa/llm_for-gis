"""Проверки подготовки входа модели без загрузки настоящей Qwen."""

from pathlib import Path

import pytest

from local_metadata_extractor.model import build_image_content, build_prompt
from local_metadata_extractor.schemas import ExtractedContent


def test_image_content_uses_local_path_for_cyrillic_filename(tmp_path: Path) -> None:
    """Transformers получает Windows-путь, а не неподдерживаемый file URI."""
    image_path = tmp_path / "новая карта.png"
    image_path.touch()

    content = build_image_content(str(image_path))

    assert content == {"type": "image", "url": str(image_path.resolve())}
    assert not content["url"].startswith("file:")


def test_repair_prompt_contains_response_and_validation_error() -> None:
    """Повторный prompt объясняет модели, почему предыдущий JSON был отклонён."""
    content = ExtractedContent(source_path="map.png", source_format="png")

    prompt = build_prompt(
        content,
        repair_raw='{"metadata": {"years": [1949]}}',
        repair_error="Год должен находиться между 1950 и 2026: [1949]",
    )

    assert "Причина ошибки:\nГод должен находиться между 1950 и 2026: [1949]" in prompt
    assert 'Предыдущий ошибочный ответ:\n{"metadata": {"years": [1949]}}' in prompt
    assert "Исправь ответ с учётом указанной ошибки" in prompt
    assert "ОБЯЗАТЕЛЬНАЯ СВЯЗЬ ТИПА И ПОДРАЗДЕЛА" in prompt
    assert "Карты:\n- План\n- Приложение\n- Разрез\n- Схема" in prompt


def test_repair_prompt_requires_validation_error() -> None:
    """Ошибочный ответ нельзя отправить на repair без причины его отклонения."""
    content = ExtractedContent(source_path="map.png", source_format="png")

    with pytest.raises(ValueError, match="причину ошибки"):
        build_prompt(content, repair_raw="broken")


def test_initial_prompt_contains_data_type_hierarchy() -> None:
    """Первичный prompt показывает модели допустимые родительско-дочерние пары."""
    content = ExtractedContent(source_path="map.png", source_format="png")

    prompt = build_prompt(content)

    assert "Протокол:\n- Протокол ГКЗ\n- Протокол НТС" in prompt
    assert "Отчет:\n- Баланс\n- Бюллетень геологических материалов" in prompt
