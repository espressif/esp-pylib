# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Tests for esp_pylib.serial_ports — port discovery, filtering, sorting."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from esp_pylib import serial_ports as ports_mod
from esp_pylib.constants import ESPRESSIF_VID
from esp_pylib.errors import NoSerialPortFoundError
from esp_pylib.serial_ports import detect_port
from esp_pylib.serial_ports import get_port_list
from esp_pylib.serial_ports import get_port_names
from esp_pylib.serial_ports import parse_port_filters


class FakePort:
    """Minimal stand-in for ``serial.tools.list_ports_common.ListPortInfo``.

    We don't subclass ``ListPortInfo`` because its constructor requires a device
    string and sets defaults we'd just have to overwrite. The attributes accessed
    by ``ports.py`` are: ``device``, ``vid``, ``pid``, ``description``, ``serial_number``.
    """

    def __init__(
        self,
        device: str,
        vid: int | None = None,
        pid: int | None = None,
        description: str = '',
        serial_number: str | None = None,
    ):
        self.device = device
        self.vid = vid
        self.pid = pid
        self.description = description
        self.serial_number = serial_number


def _patch_comports(ports: list[FakePort]):
    """Patch the comports() function imported into the module under test."""
    return patch.object(ports_mod, '_comports', return_value=list(ports))


def _patch_platform(platform: str):
    """Patch ``sys.platform`` as seen by ``ports.py``."""
    return patch.object(ports_mod.sys, 'platform', platform)


class TestGetPortList:
    def test_returns_all_ports_when_no_filters(self):
        fake = [FakePort('/dev/ttyUSB0'), FakePort('/dev/ttyUSB1')]
        with _patch_comports(fake):
            assert {p.device for p in get_port_list()} == {'/dev/ttyUSB0', '/dev/ttyUSB1'}

    def test_filter_by_vid(self):
        fake = [
            FakePort('/dev/ttyUSB0', vid=0x1234),
            FakePort('/dev/ttyUSB1', vid=ESPRESSIF_VID),
        ]
        with _patch_comports(fake):
            result = get_port_list(vids=[ESPRESSIF_VID])
        assert [p.device for p in result] == ['/dev/ttyUSB1']

    def test_filter_by_pid(self):
        fake = [
            FakePort('/dev/ttyUSB0', pid=0x1001),
            FakePort('/dev/ttyUSB1', pid=0x2000),
        ]
        with _patch_comports(fake):
            result = get_port_list(pids=[0x2000])
        assert [p.device for p in result] == ['/dev/ttyUSB1']

    def test_filter_by_name_substring_case_insensitive(self):
        fake = [FakePort('/dev/ttyUSB0'), FakePort('/dev/ttyACM1')]
        with _patch_comports(fake):
            assert [p.device for p in get_port_list(names=['ACM'])] == ['/dev/ttyACM1']
            assert [p.device for p in get_port_list(names=['acm'])] == ['/dev/ttyACM1']

    def test_filter_by_serial_substring_case_insensitive(self):
        fake = [
            FakePort('/dev/ttyUSB0', serial_number='ABC123'),
            FakePort('/dev/ttyUSB1', serial_number='XYZ999'),
        ]
        with _patch_comports(fake):
            result = get_port_list(serials=['xyz'])
        assert [p.device for p in result] == ['/dev/ttyUSB1']

    def test_filter_skips_ports_without_metadata(self):
        # Ports missing vid/pid/serial must not match an active filter
        fake = [
            FakePort('/dev/ttyUSB0', vid=None, pid=None, serial_number=None),
            FakePort('/dev/ttyUSB1', vid=ESPRESSIF_VID, pid=0x1001, serial_number='S'),
        ]
        with _patch_comports(fake):
            assert [p.device for p in get_port_list(vids=[ESPRESSIF_VID])] == ['/dev/ttyUSB1']
            assert [p.device for p in get_port_list(pids=[0x1001])] == ['/dev/ttyUSB1']
            assert [p.device for p in get_port_list(serials=['s'])] == ['/dev/ttyUSB1']

    def test_filters_are_anded(self):
        fake = [
            FakePort('/dev/ttyUSB0', vid=ESPRESSIF_VID, pid=0x1001),
            FakePort('/dev/ttyUSB1', vid=ESPRESSIF_VID, pid=0x2000),
        ]
        with _patch_comports(fake):
            result = get_port_list(vids=[ESPRESSIF_VID], pids=[0x1001])
        assert [p.device for p in result] == ['/dev/ttyUSB0']


class TestSorting:
    def test_espressif_vid_sorts_first(self):
        fake = [
            FakePort('/dev/ttyUSB0', vid=0x1234),
            FakePort('/dev/ttyACM0', vid=ESPRESSIF_VID),
        ]
        with _patch_comports(fake), _patch_platform('linux'):
            assert [p.device for p in get_port_list()][0] == '/dev/ttyACM0'

    def test_linux_pattern_priority(self):
        # ttyUSB before ttyACM (per LINUX_DEVICE_PATTERNS order), unknown last
        fake = [
            FakePort('/dev/random'),
            FakePort('/dev/ttyACM0'),
            FakePort('/dev/ttyUSB0'),
        ]
        with _patch_comports(fake), _patch_platform('linux'):
            assert [p.device for p in get_port_list()] == [
                '/dev/ttyUSB0',
                '/dev/ttyACM0',
                '/dev/random',
            ]

    def test_macos_pattern_priority(self):
        # usbserial before usbmodem (per MACOS_DEVICE_PATTERNS order)
        fake = [
            FakePort('/dev/cu.unknown'),
            FakePort('/dev/cu.usbmodem001'),
            FakePort('/dev/cu.usbserial001'),
        ]
        with _patch_comports(fake), _patch_platform('darwin'):
            assert [p.device for p in get_port_list()] == [
                '/dev/cu.usbserial001',
                '/dev/cu.usbmodem001',
                '/dev/cu.unknown',
            ]

    def test_windows_only_espressif_priority(self):
        fake = [
            FakePort('COM3', vid=0x1234),
            FakePort('COM5', vid=ESPRESSIF_VID),
            FakePort('COM4', vid=0xABCD),
        ]
        with _patch_comports(fake), _patch_platform('win32'):
            result = [p.device for p in get_port_list()]
        # Espressif first; the rest preserved in deterministic device-name order
        assert result[0] == 'COM5'
        assert set(result[1:]) == {'COM3', 'COM4'}


class TestExcludeList:
    def test_macos_virtual_ports_excluded(self):
        fake = [
            FakePort('/dev/cu.Bluetooth-Incoming-Port'),
            FakePort('/dev/cu.wlan-debug'),
            FakePort('/dev/cu.debug-console'),
            FakePort('/dev/cu.usbserial-1001'),
        ]
        with _patch_comports(fake), _patch_platform('darwin'):
            devices = [p.device for p in get_port_list()]
        assert devices == ['/dev/cu.usbserial-1001']

    def test_linux_no_exclude_list(self):
        # Same names on Linux (unlikely in practice) must NOT be filtered.
        fake = [FakePort('/dev/cu.Bluetooth-Incoming-Port'), FakePort('/dev/ttyUSB0')]
        with _patch_comports(fake), _patch_platform('linux'):
            devices = {p.device for p in get_port_list()}
        assert devices == {'/dev/cu.Bluetooth-Incoming-Port', '/dev/ttyUSB0'}


class TestGetPortNames:
    def test_returns_device_strings_only(self):
        fake = [FakePort('/dev/ttyUSB0'), FakePort('/dev/ttyUSB1')]
        with _patch_comports(fake), _patch_platform('linux'):
            assert get_port_names() == ['/dev/ttyUSB0', '/dev/ttyUSB1']

    def test_passes_filters_through(self):
        fake = [
            FakePort('/dev/ttyUSB0', vid=ESPRESSIF_VID),
            FakePort('/dev/ttyUSB1', vid=0x1234),
        ]
        with _patch_comports(fake), _patch_platform('linux'):
            assert get_port_names(vids=[ESPRESSIF_VID]) == ['/dev/ttyUSB0']


class TestDetectPort:
    def test_returns_first_after_sort(self):
        fake = [
            FakePort('/dev/ttyUSB0'),
            FakePort('/dev/ttyACM0', vid=ESPRESSIF_VID),
        ]
        with _patch_comports(fake), _patch_platform('linux'):
            assert detect_port() == '/dev/ttyACM0'

    def test_raises_when_no_ports(self):
        with _patch_comports([]), pytest.raises(NoSerialPortFoundError):
            detect_port()

    def test_raises_when_filters_eliminate_all(self):
        fake = [FakePort('/dev/ttyUSB0', vid=0x1234)]
        with _patch_comports(fake), pytest.raises(NoSerialPortFoundError):
            detect_port(vids=[ESPRESSIF_VID])


class TestParsePortFilters:
    def test_empty_input_returns_empty_lists(self):
        result = parse_port_filters(())
        assert result == {'vids': [], 'pids': [], 'names': [], 'serials': []}

    def test_parses_vid_hex_and_dec(self):
        result = parse_port_filters(('vid=0x303A', 'vid=4660'))
        assert result['vids'] == [0x303A, 4660]

    def test_parses_pid(self):
        assert parse_port_filters(('pid=0x1001',))['pids'] == [0x1001]

    def test_parses_name_and_serial(self):
        result = parse_port_filters(('name=ttyUSB', 'serial=ABC123'))
        assert result['names'] == ['ttyUSB']
        assert result['serials'] == ['ABC123']

    def test_keys_are_lowercased(self):
        result = parse_port_filters(('VID=0x1', 'Name=foo'))
        assert result['vids'] == [1]
        assert result['names'] == ['foo']

    def test_returns_shape_compatible_with_get_port_list(self):
        # Round-trip: parse_port_filters output can be splatted into get_port_list.
        fake = [
            FakePort('/dev/ttyUSB0', vid=ESPRESSIF_VID, pid=0x1001),
            FakePort('/dev/ttyUSB1', vid=0x1234, pid=0x2000),
        ]
        filters = parse_port_filters(('vid=0x303A',))
        with _patch_comports(fake):
            result = get_port_list(**filters)
        assert [p.device for p in result] == ['/dev/ttyUSB0']

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match='key=value'):
            parse_port_filters(('vid0x303A',))

    def test_unknown_key_raises(self):
        with pytest.raises(ValueError, match='Unknown port filter key'):
            parse_port_filters(('color=red',))

    def test_invalid_int_for_vid_raises(self):
        with pytest.raises(ValueError, match='Invalid integer'):
            parse_port_filters(('vid=not-a-number',))

    def test_value_with_equals_sign_preserved(self):
        # Only the first '=' splits the key from the value.
        result = parse_port_filters(('serial=A=B=C',))
        assert result['serials'] == ['A=B=C']
