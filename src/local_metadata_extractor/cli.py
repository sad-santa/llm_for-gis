"""Командная строка для обработки одного локального файла."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.status import Status

from .config import Settings
from .extractors import ExtractionError, UnsupportedFormatError
from .model import ModelLoadError
from .pipeline import process_file
from .reference_resolution import ReferenceResolutionError
from .validation import ModelResponseError

app = typer.Typer(help="Локальное извлечение метаданных из документов и карт.")
console = Console()
error_console = Console(stderr=True)


@app.callback()
def main() -> None:
    """Предоставляет группу команд локального экстрактора."""


@app.command()
def extract(
    file: Annotated[Path, typer.Argument(help="PDF, DOC(X), XLS(X), изображение или GeoTIFF")],
    output_dir: Annotated[
        Path | None, typer.Option("--output-dir", help="Каталог результата")
    ] = None,
    model: Annotated[
        str, typer.Option("--model", help="Идентификатор локальной модели")
    ] = "Qwen/Qwen3-VL-8B-Instruct",
    max_pages: Annotated[int, typer.Option("--max-pages", min=1, help="Максимум страниц PDF")] = 20,
    keep_intermediate: Annotated[
        bool, typer.Option("--keep-intermediate", help="Сохранить Markdown, превью и сырой ответ")
    ] = False,
) -> None:
    """Обрабатывает один файл и записывает проверенный UTF-8 JSON."""
    settings = Settings(model_id=model, max_pages=max_pages)
    try:
        with Status("Извлечение и анализ файла...", console=console):
            result_path = process_file(
                file,
                output_dir=output_dir,
                settings=settings,
                keep_intermediate=keep_intermediate,
            )
    except (
        FileNotFoundError,
        UnsupportedFormatError,
        ExtractionError,
        ModelLoadError,
        ModelResponseError,
        ReferenceResolutionError,
    ) as exc:
        error_console.print(f"[red]Ошибка:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Готово:[/green] {result_path}")


if __name__ == "__main__":
    app()
