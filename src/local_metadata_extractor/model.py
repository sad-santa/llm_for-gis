"""Ленивая загрузка Qwen3-VL и один локальный inference."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import Settings
from .schemas import ExtractedContent, MetadataResult

SYSTEM_PROMPT = """Ты извлекаешь метаданные из геологических документов и карт.

Верни только JSON-объект строго по переданной JSON Schema, без Markdown и пояснений.

Используй только факты, прямо указанные или однозначно следующие из конкретных данных документа.
Допускай определение категории по однозначным фактам документа, даже если её название не указано дословно.
Значения категориальных полей записывай только в установленных формулировках, без произвольных синонимов.
Не делай выводов только по тематике, типичным практикам или внешним знаниям.
При недостаточном подтверждении оставляй поле пустым: null или [].

Не путай упоминание человека, метода или организации с их ролью в документе.
Авторами считай только авторов самого документа, исключая цитируемых исследователей и список литературы.

EVIDENCE:
Для каждого заполненного поля приводи короткую дословную цитату из исходного текста или изображения.
Цитата должна точно воспроизводить реально присутствующий фрагмент, без пересказа, перефразирования и добавления слов.
Не пиши пояснения вроде «в документе упоминается» или «из текста следует».
Цитата должна подтверждать значение напрямую либо служить конкретным основанием для его однозначной интерпретации.
Если точную подтверждающую цитату найти невозможно, не заполняй поле.
Для технических данных допускаются факты из переданных технических метаданных.

Имя файла не является доказательством.
Не угадывай CRS по изображению.
Сохраняй исходное написание имён, лицензий и географических названий.
Не добавляй поля вне схемы. Множественные значения возвращай массивами.
"""


class ModelLoadError(RuntimeError):
    """Локальная модель или CUDA не готовы к inference."""


class LocalQwenModel:
    """Хранит единственный лениво загружаемый экземпляр Qwen3-VL."""

    def __init__(self, settings: Settings) -> None:
        """Запоминает настройки, не выделяя VRAM при создании объекта."""
        self.settings = settings
        self._model: Any | None = None
        self._processor: Any | None = None

    def _load(self) -> None:
        """Проверяет CUDA и загружает 4-bit модель непосредственно перед первым запросом."""
        if self._model is not None:
            return
        try:
            import torch
            from transformers import (
                AutoProcessor,
                BitsAndBytesConfig,
                Qwen3VLForConditionalGeneration,
            )
        except ImportError as exc:
            raise ModelLoadError("Зависимости модели не установлены. Выполните uv sync.") from exc
        if not torch.cuda.is_available():
            raise ModelLoadError(
                "CUDA недоступна. CPU inference для Qwen3-VL в этом MVP не поддерживается."
            )
        compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        quantization = BitsAndBytesConfig(
            # load_in_8bit=True,
            load_in_4bit=True,
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_quant_type="nf4",
        )
        try:
            self._processor = AutoProcessor.from_pretrained(self.settings.model_id)
            self._model = Qwen3VLForConditionalGeneration.from_pretrained(
                self.settings.model_id,
                quantization_config=quantization,
                torch_dtype=compute_dtype,
                device_map="auto",
                max_memory={0: self.settings.max_gpu_memory, "cpu": "32GiB"},
                attn_implementation="sdpa",
            )
        except (OSError, RuntimeError, ValueError) as exc:
            raise ModelLoadError(
                f"Не удалось загрузить {self.settings.model_id} в доступную память: {exc}"
            ) from exc

    def generate(
        self,
        content: ExtractedContent,
        repair_raw: str | None = None,
        repair_error: str | None = None,
    ) -> str:
        """Генерирует JSON либо один раз исправляет отклонённый предыдущий ответ."""
        self._load()
        prompt = build_prompt(content, repair_raw=repair_raw, repair_error=repair_error)
        message_content: list[dict[str, Any]] = []
        for image_path in content.image_paths:
            message_content.append(build_image_content(image_path))
        message_content.append({"type": "text", "text": prompt})
        messages = [
            {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": message_content},
        ]
        inputs = self._processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
        inputs.pop("token_type_ids", None)
        inputs = inputs.to(self._model.device)
        generated = self._model.generate(
            **inputs,
            max_new_tokens=self.settings.max_new_tokens,
            do_sample=self.settings.temperature > 0,
            temperature=self.settings.temperature if self.settings.temperature > 0 else None,
        )
        new_tokens = generated[:, inputs["input_ids"].shape[1] :]
        return self._processor.batch_decode(
            new_tokens, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]


def build_image_content(image_path: str) -> dict[str, str]:
    """Возвращает локальный путь изображения в формате, понятном Transformers."""
    return {"type": "image", "url": str(Path(image_path).resolve())}


def build_prompt(
    content: ExtractedContent,
    repair_raw: str | None = None,
    repair_error: str | None = None,
) -> str:
    """Создаёт прозрачный prompt из схемы, Markdown и технических метаданных."""
    schema = json.dumps(MetadataResult.model_json_schema(), ensure_ascii=False, indent=2)
    if repair_raw is not None:
        if repair_error is None:
            raise ValueError("Для исправления ответа необходимо передать причину ошибки.")
        return (
            "Предыдущий ответ не прошёл проверку.\n\n"
            f"Причина ошибки:\n{repair_error}\n\n"
            "Исправь ответ с учётом указанной ошибки. Не добавляй факты, которых нет "
            "в исходных данных. Если значение нельзя подтвердить, замени его на null "
            "или пустой массив. Верни только один JSON-объект без Markdown и пояснений.\n\n"
            f"JSON Schema:\n{schema}\n\n"
            f"Предыдущий ошибочный ответ:\n{repair_raw}"
        )
    payload = {
        "source_file": Path(content.source_path).name,
        "source_format": content.source_format,
        "technical_metadata": content.technical_metadata,
        "extractor_warnings": content.warnings,
        "tables": content.tables,
    }
    return (
        f"JSON Schema результата:\n{schema}\n\n"
        f"Данные экстрактора:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        f"Содержимое документа в Markdown:\n{content.text}"
    )
