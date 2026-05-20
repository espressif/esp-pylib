# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Tests for esp_pylib.cli_types."""

from unittest.mock import patch

import pytest
import rich_click as click
from click.shell_completion import CompletionItem
from click.testing import CliRunner

from esp_pylib.cli_types import COMMON_BAUD_RATES
from esp_pylib.cli_types import AnyIntType
from esp_pylib.cli_types import AutoSizeType
from esp_pylib.cli_types import BaudRateType
from esp_pylib.cli_types import SerialPortType


class _FakePort:
    def __init__(self, device, description='', vid=None, pid=None):
        self.device = device
        self.description = description
        self.vid = vid
        self.pid = pid


class TestAnyIntType:
    @pytest.mark.parametrize(
        'value, expected',
        [
            ('0xff', 255),
            ('0b1010', 10),
            ('0o10', 8),
            (7, 7),
        ],
        ids=['hex', 'binary', 'octal', 'int'],
    )
    def test_convert(self, value: str, expected: int):
        assert AnyIntType().convert(value, None, None) == expected

    def test_invalid_raises_bad_parameter(self):
        with pytest.raises(click.BadParameter):
            AnyIntType().convert('not-a-number', None, None)


class TestAutoSizeType:
    @pytest.mark.parametrize(
        'value, expected',
        [
            ('4k', 4 * 1024),
            ('2M', 2 * 1024 * 1024),
        ],
        ids=['k', 'M'],
    )
    def test_convert(self, value: str, expected: int):
        assert AutoSizeType().convert(value, None, None) == expected

    def test_all_when_allowed(self):
        assert AutoSizeType(allow_all=True).convert('all', None, None) == 'all'

    def test_all_disallowed_parses_as_integer(self):
        with pytest.raises(click.BadParameter):
            AutoSizeType(allow_all=False).convert('all', None, None)


class TestBaudRateType:
    def test_convert_decimal(self):
        assert BaudRateType().convert('115200', None, None) == 115200

    def test_shell_complete_filters_by_incomplete_prefix(self):
        items = BaudRateType().shell_complete(None, None, '115')
        assert all(isinstance(i, CompletionItem) for i in items)
        assert {i.value for i in items} == {'115200'}

    def test_shell_complete_empty_prefix_lists_all_rates(self):
        items = BaudRateType().shell_complete(None, None, '')
        assert {i.value for i in items} == {str(b) for b in COMMON_BAUD_RATES}


class TestSerialPortType:
    def test_convert_returns_value_unchanged(self):
        # The type accepts arbitrary strings — validation is the tool's job
        # when it actually opens the port.
        t = SerialPortType()
        assert t.convert('/dev/ttyUSB0', None, None) == '/dev/ttyUSB0'
        assert t.convert('COM3', None, None) == 'COM3'

    def test_shell_complete_returns_completion_items(self):
        fake_ports = [
            _FakePort('/dev/ttyUSB0', 'CP210x'),
            _FakePort('/dev/ttyUSB1', 'FT232R'),
            _FakePort('/dev/ttyACM0', 'JTAG'),
        ]
        t = SerialPortType()
        with patch('esp_pylib.serial_ports.get_port_list', return_value=fake_ports):
            items = t.shell_complete(None, None, '/dev/ttyUSB')
        assert all(isinstance(i, CompletionItem) for i in items)
        assert {i.value for i in items} == {'/dev/ttyUSB0', '/dev/ttyUSB1'}

    def test_shell_complete_filters_by_prefix_case_insensitive(self):
        fake_ports = [_FakePort('/dev/ttyUSB0'), _FakePort('/dev/ACM0')]
        t = SerialPortType()
        with patch('esp_pylib.serial_ports.get_port_list', return_value=fake_ports):
            items = t.shell_complete(None, None, '/dev/tty')
        assert {i.value for i in items} == {'/dev/ttyUSB0'}

    def test_shell_complete_includes_description_as_help(self):
        # Description-only path: VID/PID missing, help carries just the description.
        fake_ports = [_FakePort('/dev/ttyUSB0', 'My Adapter')]
        t = SerialPortType()
        with patch('esp_pylib.serial_ports.get_port_list', return_value=fake_ports):
            items = t.shell_complete(None, None, '')
        assert items[0].help == 'Description: My Adapter'

    def test_shell_complete_help_includes_vid_pid_in_hex(self):
        # USB device with full metadata: description + VID/PID rendered as
        # 4-digit zero-padded hex (the convention in Espressif docs / lsusb).
        fake_ports = [_FakePort('/dev/ttyUSB0', 'CP210x', vid=0x10C4, pid=0xEA60)]
        t = SerialPortType()
        with patch('esp_pylib.serial_ports.get_port_list', return_value=fake_ports):
            items = t.shell_complete(None, None, '')
        assert items[0].help == 'Description: CP210x, VID: 0x10C4, PID: 0xEA60'

    def test_shell_complete_help_skips_missing_fields(self):
        # Non-USB serial port (no VID/PID) and a USB device with no description:
        # each field is independently included only when set, so the help
        # string never contains the literal text ``None``.
        no_usb = _FakePort('/dev/ttyS0', 'Built-in UART')
        no_desc = _FakePort('/dev/ttyUSB1', '', vid=0x303A, pid=0x1001)
        t = SerialPortType()
        with patch('esp_pylib.serial_ports.get_port_list', return_value=[no_usb, no_desc]):
            items = t.shell_complete(None, None, '')
        helps = {i.value: i.help for i in items}
        assert helps['/dev/ttyS0'] == 'Description: Built-in UART'
        assert helps['/dev/ttyUSB1'] == 'VID: 0x303A, PID: 0x1001'

    def test_format_port_completion_help_with_no_metadata(self):
        # A port with no description, no VID, no PID — e.g. a bare ``socket://``
        # handler — yields an empty string rather than raising or producing
        # noise like ``"Description: , VID: None, PID: None"``.
        assert SerialPortType._format_port_completion_help(_FakePort('/dev/null')) == ''

    def test_shell_complete_empty_when_pyserial_missing(self):
        t = SerialPortType()
        # Simulate pyserial missing by forcing an ImportError from the lazy import
        # inside ``shell_complete``. Patching ``builtins.__import__`` is the cleanest
        # way to make a single statement raise ImportError without uninstalling pyserial.
        real_import = __import__

        def _fake_import(name, *args, **kwargs):
            if name == 'esp_pylib.serial_ports':
                raise ImportError('pyserial missing (simulated)')
            return real_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=_fake_import):
            items = t.shell_complete(None, None, '')
        assert items == []

    def test_shell_complete_swallows_runtime_errors(self):
        t = SerialPortType()
        with patch('esp_pylib.serial_ports.get_port_list', side_effect=OSError('permission denied')):
            items = t.shell_complete(None, None, '')
        assert items == []


class TestSerialPortTypeWithClick:
    """Use SerialPortType inside a real Click command to confirm wiring works."""

    def test_used_as_option_type(self):
        @click.command()
        @click.option('--port', type=SerialPortType())
        def cmd(port):
            click.echo(f'port={port}')

        runner = CliRunner()
        result = runner.invoke(cmd, ['--port', '/dev/ttyUSB0'])
        assert result.exit_code == 0
        assert 'port=/dev/ttyUSB0' in result.output
