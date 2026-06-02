# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""ROM ELF file resolution.

Single implementation replacing duplicated code in esp-idf-monitor and
esp-coredump. Uses ``IDF_PATH`` and ``ESP_ROM_ELF_DIR`` from the
environment — the cross-tool variables used for ROM ELF lookup.
"""

from __future__ import annotations

import json
import os

__all__ = [
    'get_idf_path',
    'get_rom_elf_dir',
    'get_roms_json_paths',
    'get_rom_elf_path',
]


def get_idf_path() -> str:
    """Return ``IDF_PATH`` from the environment (empty string when unset)."""
    return os.getenv('IDF_PATH', '')


def get_rom_elf_dir() -> str:
    """Return ``ESP_ROM_ELF_DIR`` from the environment (empty string when unset)."""
    return os.getenv('ESP_ROM_ELF_DIR', '')


def get_roms_json_paths() -> list[str]:
    """Return both possible ``roms.json`` locations under ``IDF_PATH``.

    ``tools/idf_py_actions/roms.json`` is listed for compatibility with
    ESP-IDF before v5.5, when the file was moved under ``components/esp_rom``.
    """
    idf = get_idf_path()
    return [
        os.path.join(idf, 'components', 'esp_rom', 'roms.json'),
        os.path.join(idf, 'tools', 'idf_py_actions', 'roms.json'),
    ]


def get_rom_elf_path(target: str, chip_rev: int) -> str | None:
    """Resolve the ROM ELF path for *target* and *chip_rev*.

    Reads ``roms.json`` from ``IDF_PATH`` (see `get_roms_json_paths`)
    and, when a matching revision entry exists, returns
    ``{ESP_ROM_ELF_DIR}/{target}_rev{chip_rev}_rom.elf``.

    Returns ``None`` when ``IDF_PATH`` or ``ESP_ROM_ELF_DIR`` are unset,
    when no ``roms.json`` lists *target* with at least one revision entry,
    or when no entry matches *chip_rev*. Unreadable files, invalid JSON, or
    JSON that omits *target* (or lists it with an empty revision list) in one
    path are skipped so the other ``roms.json`` location can be tried. Once a
    file lists *target* with a non-empty revision list, that file is used
    exclusively (no fallback if *chip_rev* is missing there).
    """
    idf_path = get_idf_path()
    rom_elf_dir = get_rom_elf_dir()

    if not idf_path or not rom_elf_dir:
        return None

    target_roms: list[dict[str, object]] | None = None
    for roms_json_path in get_roms_json_paths():
        try:
            with open(roms_json_path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        candidate = data.get(target)
        if not isinstance(candidate, list) or not candidate:
            continue
        target_roms = candidate
        break

    if not target_roms:
        return None

    for rom in target_roms:
        if rom.get('rev') == chip_rev:
            return os.path.join(rom_elf_dir, f'{target}_rev{chip_rev}_rom.elf')

    return None
