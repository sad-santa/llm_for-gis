"""Pipeline проверяется без загрузки настоящей 8B-модели."""

import json
from pathlib import Path

from PIL import Image

from local_metadata_extractor.pipeline import process_file
from local_metadata_extractor.schemas import MetadataFields


def valid_response(source_file: str) -> str:
    """Возвращает валидный полный JSON для поддельного inference."""
    return json.dumps(
        {
            "schema_version": "1.0",
            "source_file": source_file,
            "metadata": MetadataFields(year=[2024]).model_dump(),
            "evidence": {"year": ["На карте указан 2024 год"]},
            "warnings": [],
        },
        ensure_ascii=False,
    )


def test_pipeline_with_fake_model_and_intermediate_markdown(tmp_path: Path) -> None:
    """Файл проходит путь до JSON, а исходное содержание сохраняется отдельно."""
    source = tmp_path / "map.png"
    Image.new("RGB", (20, 10), "white").save(source)
    calls: list[str | None] = []

    def fake_model(content: object, repair: str | None) -> str:
        calls.append(repair)
        return valid_response("map.png")

    result_path = process_file(source, keep_intermediate=True, model_call=fake_model)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["metadata"]["year"] == [2024]
    assert calls == [None]
    assert (result_path.parent / "map.artifacts" / "content.md").is_file()


def test_pipeline_repairs_invalid_json_once(tmp_path: Path) -> None:
    """После первого плохого JSON выполняется ровно один repair-вызов."""
    source = tmp_path / "map.png"
    Image.new("RGB", (10, 10), "white").save(source)
    calls: list[str | None] = []

    def fake_model(content: object, repair: str | None) -> str:
        calls.append(repair)
        return "broken" if repair is None else valid_response("map.png")

    process_file(source, model_call=fake_model)
    assert calls == [None, "broken"]
