import json
from pathlib import Path


def write_json(path: Path, data: dict | list) -> None:
    """Записывает JSON во временный файл и заменяет исходный."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(path.name + ".tmp")

    try:
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
