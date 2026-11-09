"""Небольшая конфигурация локального pipeline без внешнего фреймворка."""

from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    """Настройки обработки одного файла и генерации ответа."""

    model_id: str = "Qwen/Qwen3-VL-8B-Instruct"
    max_gpu_memory: str = "13GiB"
    max_pages: int = 20
    max_image_side: int = 1536
    max_new_tokens: int = 2048
    temperature: float = 0.0
    max_text_chars: int = 120_000
