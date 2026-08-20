# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Tests for esp_pylib.rom — ROM ELF path resolution."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from esp_pylib.rom import get_idf_path
from esp_pylib.rom import get_rom_elf_dir
from esp_pylib.rom import get_rom_elf_path
from esp_pylib.rom import get_roms_json_paths

if TYPE_CHECKING:
    from pathlib import Path


class TestEnvAccessors:
    def test_get_idf_path_from_env(self, monkeypatch):
        monkeypatch.setenv('IDF_PATH', '/opt/esp-idf')
        assert get_idf_path() == '/opt/esp-idf'

    def test_get_idf_path_default_empty(self, monkeypatch):
        monkeypatch.delenv('IDF_PATH', raising=False)
        assert get_idf_path() == ''

    def test_get_rom_elf_dir_from_env(self, monkeypatch):
        monkeypatch.setenv('ESP_ROM_ELF_DIR', '/rom/elves')
        assert get_rom_elf_dir() == '/rom/elves'

    def test_get_rom_elf_dir_default_empty(self, monkeypatch):
        monkeypatch.delenv('ESP_ROM_ELF_DIR', raising=False)
        assert get_rom_elf_dir() == ''


class TestRomsJsonPaths:
    def test_both_locations_under_idf_path(self, monkeypatch):
        monkeypatch.setenv('IDF_PATH', '/idf')
        idf = '/idf'
        assert get_roms_json_paths() == [
            os.path.join(idf, 'components', 'esp_rom', 'roms.json'),
            os.path.join(idf, 'tools', 'idf_py_actions', 'roms.json'),
        ]


class TestGetRomElfPath:
    def test_returns_none_without_idf_path(self, monkeypatch, tmp_path):
        monkeypatch.delenv('IDF_PATH', raising=False)
        monkeypatch.setenv('ESP_ROM_ELF_DIR', str(tmp_path))
        assert get_rom_elf_path('esp32', 0) is None

    def test_returns_none_without_rom_elf_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv('IDF_PATH', str(tmp_path))
        monkeypatch.delenv('ESP_ROM_ELF_DIR', raising=False)
        assert get_rom_elf_path('esp32', 0) is None

    def test_returns_none_when_roms_json_missing(self, monkeypatch, tmp_path):
        monkeypatch.setenv('IDF_PATH', str(tmp_path))
        monkeypatch.setenv('ESP_ROM_ELF_DIR', str(tmp_path / 'elfs'))
        assert get_rom_elf_path('esp32', 0) is None

    def test_falls_back_to_next_lower_revision(self, monkeypatch, tmp_path: Path):
        idf = tmp_path / 'idf'
        elf_dir = tmp_path / 'elfs'
        _write_roms_json(idf, {'esp32p4': [{'rev': 0}, {'rev': 300}]})
        monkeypatch.setenv('IDF_PATH', str(idf))
        monkeypatch.setenv('ESP_ROM_ELF_DIR', str(elf_dir))
        assert get_rom_elf_path('esp32p4', 301) == str(elf_dir / 'esp32p4_rev300_rom.elf')

    def test_returns_none_when_no_revision_le_chip_rev(self, monkeypatch, tmp_path: Path):
        idf = tmp_path / 'idf'
        elf_dir = tmp_path / 'elfs'
        _write_roms_json(idf, {'esp32': [{'rev': 300}]})
        monkeypatch.setenv('IDF_PATH', str(idf))
        monkeypatch.setenv('ESP_ROM_ELF_DIR', str(elf_dir))
        assert get_rom_elf_path('esp32', 1) is None

    def test_resolves_path_from_components_roms_json(self, monkeypatch, tmp_path: Path):
        idf = tmp_path / 'idf'
        elf_dir = tmp_path / 'elfs'
        _write_roms_json(idf, {'esp32': [{'rev': 0}, {'rev': 1}]})
        monkeypatch.setenv('IDF_PATH', str(idf))
        monkeypatch.setenv('ESP_ROM_ELF_DIR', str(elf_dir))
        assert get_rom_elf_path('esp32', 1) == str(elf_dir / 'esp32_rev1_rom.elf')

    def test_falls_back_to_legacy_roms_json_location(self, monkeypatch, tmp_path: Path):
        idf = tmp_path / 'idf'
        elf_dir = tmp_path / 'elfs'
        legacy = idf / 'tools' / 'idf_py_actions'
        legacy.mkdir(parents=True)
        (legacy / 'roms.json').write_text(
            json.dumps({'esp32c3': [{'rev': 3}]}),
            encoding='utf-8',
        )
        monkeypatch.setenv('IDF_PATH', str(idf))
        monkeypatch.setenv('ESP_ROM_ELF_DIR', str(elf_dir))
        assert get_rom_elf_path('esp32c3', 3) == str(elf_dir / 'esp32c3_rev3_rom.elf')

    def test_skips_invalid_components_roms_json_and_uses_legacy(self, monkeypatch, tmp_path: Path):
        idf = tmp_path / 'idf'
        elf_dir = tmp_path / 'elfs'
        components = idf / 'components' / 'esp_rom'
        components.mkdir(parents=True)
        (components / 'roms.json').write_text('not json', encoding='utf-8')
        legacy = idf / 'tools' / 'idf_py_actions'
        legacy.mkdir(parents=True)
        (legacy / 'roms.json').write_text(
            json.dumps({'esp32c3': [{'rev': 3}]}),
            encoding='utf-8',
        )
        monkeypatch.setenv('IDF_PATH', str(idf))
        monkeypatch.setenv('ESP_ROM_ELF_DIR', str(elf_dir))
        assert get_rom_elf_path('esp32c3', 3) == str(elf_dir / 'esp32c3_rev3_rom.elf')

    def test_falls_back_when_components_roms_json_omits_target(self, monkeypatch, tmp_path: Path):
        idf = tmp_path / 'idf'
        elf_dir = tmp_path / 'elfs'
        components = idf / 'components' / 'esp_rom'
        components.mkdir(parents=True)
        (components / 'roms.json').write_text(
            json.dumps({'esp32s3': [{'rev': 0}]}),
            encoding='utf-8',
        )
        legacy = idf / 'tools' / 'idf_py_actions'
        legacy.mkdir(parents=True)
        (legacy / 'roms.json').write_text(
            json.dumps({'esp32': [{'rev': 1}]}),
            encoding='utf-8',
        )
        monkeypatch.setenv('IDF_PATH', str(idf))
        monkeypatch.setenv('ESP_ROM_ELF_DIR', str(elf_dir))
        assert get_rom_elf_path('esp32', 1) == str(elf_dir / 'esp32_rev1_rom.elf')

    def test_falls_back_when_components_lists_empty_target(self, monkeypatch, tmp_path: Path):
        idf = tmp_path / 'idf'
        elf_dir = tmp_path / 'elfs'
        components = idf / 'components' / 'esp_rom'
        components.mkdir(parents=True)
        (components / 'roms.json').write_text(
            json.dumps({'esp32': []}),
            encoding='utf-8',
        )
        legacy = idf / 'tools' / 'idf_py_actions'
        legacy.mkdir(parents=True)
        (legacy / 'roms.json').write_text(
            json.dumps({'esp32': [{'rev': 2}]}),
            encoding='utf-8',
        )
        monkeypatch.setenv('IDF_PATH', str(idf))
        monkeypatch.setenv('ESP_ROM_ELF_DIR', str(elf_dir))
        assert get_rom_elf_path('esp32', 2) == str(elf_dir / 'esp32_rev2_rom.elf')

    def test_skips_non_object_roms_json_root(self, monkeypatch, tmp_path: Path):
        idf = tmp_path / 'idf'
        elf_dir = tmp_path / 'elfs'
        components = idf / 'components' / 'esp_rom'
        components.mkdir(parents=True)
        (components / 'roms.json').write_text('[]', encoding='utf-8')
        legacy = idf / 'tools' / 'idf_py_actions'
        legacy.mkdir(parents=True)
        (legacy / 'roms.json').write_text(
            json.dumps({'esp32c3': [{'rev': 1}]}),
            encoding='utf-8',
        )
        monkeypatch.setenv('IDF_PATH', str(idf))
        monkeypatch.setenv('ESP_ROM_ELF_DIR', str(elf_dir))
        assert get_rom_elf_path('esp32c3', 1) == str(elf_dir / 'esp32c3_rev1_rom.elf')

    def test_prefers_components_roms_json_over_legacy(self, monkeypatch, tmp_path: Path):
        idf = tmp_path / 'idf'
        elf_dir = tmp_path / 'elfs'
        _write_roms_json(idf, {'esp32': [{'rev': 0}]})
        legacy = idf / 'tools' / 'idf_py_actions'
        legacy.mkdir(parents=True)
        (legacy / 'roms.json').write_text(
            json.dumps({'esp32': [{'rev': 99}]}),
            encoding='utf-8',
        )
        monkeypatch.setenv('IDF_PATH', str(idf))
        monkeypatch.setenv('ESP_ROM_ELF_DIR', str(elf_dir))
        assert get_rom_elf_path('esp32', 0) == str(elf_dir / 'esp32_rev0_rom.elf')
        assert get_rom_elf_path('esp32', 99) == str(elf_dir / 'esp32_rev0_rom.elf')


def _write_roms_json(idf_root: Path, data: dict[str, list[dict[str, int]]]) -> None:
    roms = idf_root / 'components' / 'esp_rom'
    roms.mkdir(parents=True)
    (roms / 'roms.json').write_text(json.dumps(data), encoding='utf-8')
