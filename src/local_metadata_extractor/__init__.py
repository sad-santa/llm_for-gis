"""Локальное извлечение метаданных из документов и карт."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("local-metadata-extractor")
except PackageNotFoundError:
    __version__ = "0.1.0"
