"""Последовательный путь от одного файла до проверенного JSON."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import TypeAlias

from .config import Settings
from .extractors import extract_file, temporary_work_dir
from .model import LocalQwenModel
from .reference_resolution import ReferenceLookups, to_api_result
from .schemas import ExtractedContent, MetadataResult
from .validation import ModelResponseError, parse_model_response

ModelCall: TypeAlias = Callable[[ExtractedContent, str | None, str | None], str]


def process_file(
    source_path: Path,
    output_dir: Path | None = None,
    settings: Settings | None = None,
    keep_intermediate: bool = False,
    model_call: ModelCall | None = None,
    reference_lookups: ReferenceLookups | None = None,
) -> Path:
    """Извлекает метаданные и при наличии справочников преобразует названия в ID."""
    settings = settings or Settings()
    source_path = source_path.resolve()
    target_dir = (output_dir or source_path.parent / "output").resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir = target_dir / f"{source_path.stem}.artifacts"

    with temporary_work_dir() as temp_name:
        temp_dir = Path(temp_name)
        content = extract_file(source_path, temp_dir, settings)
        if model_call is None:
            local_model = LocalQwenModel(settings)

            def call_local_model(
                item: ExtractedContent,
                repair: str | None,
                repair_error: str | None,
            ) -> str:
                """Передаёт данные единственному экземпляру локальной модели."""
                return local_model.generate(
                    item,
                    repair_raw=repair,
                    repair_error=repair_error,
                )

            model_call = call_local_model
        raw = model_call(content, None, None)
        try:
            result = parse_model_response(raw)
        except ModelResponseError as first_error:
            repaired = model_call(content, raw, str(first_error))
            try:
                result = parse_model_response(repaired)
                raw = repaired
            except ModelResponseError as second_error:
                artifact_dir.mkdir(parents=True, exist_ok=True)
                (artifact_dir / "raw-response.txt").write_text(repaired, encoding="utf-8")
                raise ModelResponseError(
                    f"Модель дважды вернула неверный JSON: {first_error}; {second_error}"
                ) from second_error

        _merge_extractor_facts(result, content)
        if keep_intermediate:
            _save_intermediate(artifact_dir, content, raw)
            for image_path in content.image_paths:
                shutil.copy2(image_path, artifact_dir / Path(image_path).name)
        output_result = (
            to_api_result(result, reference_lookups) if reference_lookups is not None else result
        )
        result_path = target_dir / f"{source_path.stem}.metadata.json"
        result_path.write_text(
            output_result.model_dump_json(indent=2, exclude_none=False), encoding="utf-8"
        )
        return result_path


def _merge_extractor_facts(result: MetadataResult, content: ExtractedContent) -> None:
    """Переносит достоверный CRS GeoTIFF и предупреждения экстрактора в ответ."""
    result.source_file = Path(content.source_path).name
    crs = content.technical_metadata.get("crs_authid")
    if crs:
        result.metadata.crs_authid = str(crs)
        result.evidence["crs_authid"] = [f"GeoTIFF metadata: {crs}"]
    result.warnings = list(dict.fromkeys([*content.warnings, *result.warnings]))


def _save_intermediate(artifact_dir: Path, content: ExtractedContent, raw: str) -> None:
    """Сохраняет видимые человеку Markdown, техметаданные и сырой ответ."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "content.md").write_text(content.text, encoding="utf-8")
    (artifact_dir / "technical-metadata.json").write_text(
        json.dumps(content.technical_metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (artifact_dir / "raw-response.txt").write_text(raw, encoding="utf-8")
