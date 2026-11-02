"""Проверки подготовки входа модели без загрузки настоящей Qwen."""

from pathlib import Path

from local_metadata_extractor.model import build_image_content


def test_image_content_uses_local_path_for_cyrillic_filename(tmp_path: Path) -> None:
    """Transformers получает Windows-путь, а не неподдерживаемый file URI."""
    image_path = tmp_path / "новая карта.png"
    image_path.touch()

    content = build_image_content(str(image_path))

    assert content == {"type": "image", "url": str(image_path.resolve())}
    assert not content["url"].startswith("file:")
