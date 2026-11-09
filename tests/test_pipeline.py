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
            "metadata": MetadataFields(
                data_type_id="Карты",
                data_subtype_id="Схема",
                years=[2024],
            ).model_dump(),
            "evidence": {
                "data_type_id": ["Документ является картографическим материалом"],
                "data_subtype_id": ["В заголовке указано: схема"],
                "years": ["На карте указан 2024 год"],
            },
            "warnings": [],
        },
        ensure_ascii=False,
    )


def test_pipeline_with_fake_model_and_intermediate_markdown(tmp_path: Path) -> None:
    """Файл проходит путь до JSON, а исходное содержание сохраняется отдельно."""
    source = tmp_path / "map.png"
    Image.new("RGB", (20, 10), "white").save(source)
    calls: list[tuple[str | None, str | None]] = []

    def fake_model(
        content: object,
        repair: str | None,
        repair_error: str | None,
    ) -> str:
        calls.append((repair, repair_error))
        return valid_response("map.png")

    result_path = process_file(source, keep_intermediate=True, model_call=fake_model)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["metadata"]["years"] == [2024]
    assert calls == [(None, None)]
    assert (result_path.parent / "map.artifacts" / "content.md").is_file()


def test_pipeline_repairs_invalid_json_once(tmp_path: Path) -> None:
    """После первого плохого JSON выполняется ровно один repair-вызов."""
    source = tmp_path / "map.png"
    Image.new("RGB", (10, 10), "white").save(source)
    calls: list[tuple[str | None, str | None]] = []

    def fake_model(
        content: object,
        repair: str | None,
        repair_error: str | None,
    ) -> str:
        calls.append((repair, repair_error))
        return "broken" if repair is None else valid_response("map.png")

    process_file(source, model_call=fake_model)
    assert calls[0] == (None, None)
    assert calls[1][0] == "broken"
    assert calls[1][1] is not None
    assert "Некорректный структурированный ответ" in calls[1][1]


def test_pipeline_passes_business_validation_error_to_repair(tmp_path: Path) -> None:
    """Repair-вызов получает причину ошибки бизнес-валидации."""
    source = tmp_path / "map.png"
    Image.new("RGB", (10, 10), "white").save(source)
    invalid_response = json.loads(valid_response("map.png"))
    invalid_response["metadata"]["years"] = [1949]
    calls: list[tuple[str | None, str | None]] = []

    def fake_model(
        content: object,
        repair: str | None,
        repair_error: str | None,
    ) -> str:
        calls.append((repair, repair_error))
        if repair is None:
            return json.dumps(invalid_response, ensure_ascii=False)
        return valid_response("map.png")

    process_file(source, model_call=fake_model)

    assert calls[1][1] is not None
    assert "Год должен находиться между 1950" in calls[1][1]


def test_pipeline_repairs_subtype_from_another_parent(tmp_path: Path) -> None:
    """Несогласованная пара тип–подтип отклоняется внутри repair-цикла."""
    source = tmp_path / "map.png"
    Image.new("RGB", (10, 10), "white").save(source)
    invalid_response = json.loads(valid_response("map.png"))
    invalid_response["metadata"]["data_subtype_id"] = "Протокол ГКЗ"
    calls: list[tuple[str | None, str | None]] = []

    def fake_model(
        content: object,
        repair: str | None,
        repair_error: str | None,
    ) -> str:
        calls.append((repair, repair_error))
        if repair is None:
            return json.dumps(invalid_response, ensure_ascii=False)
        return valid_response("map.png")

    process_file(source, model_call=fake_model)

    assert calls[1][1] is not None
    assert "не относится к типу «Карты»" in calls[1][1]
    assert "Подраздел относится к типу «Протокол»" in calls[1][1]


def test_pipeline_switches_to_api_schema_when_lookups_are_provided(tmp_path: Path) -> None:
    """Переданные справочники включают преобразование названий в backend-ID."""
    source = tmp_path / "map.png"
    Image.new("RGB", (10, 10), "white").save(source)
    metadata = MetadataFields(
        data_type_id="Карты",
        data_subtype_id="Схема",
        region_ids=["Камчатский край"],
        years=[2024],
    ).model_dump()
    response = json.dumps(
        {
            "schema_version": "1.0",
            "source_file": "map.png",
            "metadata": metadata,
            "evidence": {
                "data_type_id": ["Документ является картографическим материалом"],
                "data_subtype_id": ["В заголовке указано: схема"],
                "region_ids": ["Камчатский край указан в заголовке"],
                "years": ["На карте указан 2024 год"],
            },
            "warnings": [],
        },
        ensure_ascii=False,
    )

    result_path = process_file(
        source,
        model_call=lambda content, repair, repair_error: response,
        reference_lookups={
            "data_type_id": {"Карты": 1},
            "data_subtype_id": {"Схема": 2},
            "region_ids": {"Камчатский край": 4},
        },
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert result["metadata"]["region_ids"] == [4]
