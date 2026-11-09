"""Небольшая конфигурация локального pipeline без внешнего фреймворка."""

from dataclasses import dataclass
from enum import StrEnum


class ExcelExtractor(StrEnum):
    """Способ извлечения текста из Excel-файлов."""

    DOCLING = "docling"
    OPENPYXL = "openpyxl"


@dataclass(slots=True)
class Settings:
    """Настройки обработки одного файла и генерации ответа."""

    model_id: str = "Qwen/Qwen3-VL-8B-Instruct"
    max_gpu_memory: str = "13GiB"
    max_pages: int = 7
    excel_extractor: ExcelExtractor = ExcelExtractor.DOCLING
    max_excel_rows: int = 100
    max_excel_columns: int = 256
    max_image_side: int = 1536
    max_new_tokens: int = 2048
    temperature: float = 0.0
    max_text_chars: int = 2_000
