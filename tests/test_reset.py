# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Tests for esp_pylib.serial_reset — DTR/RTS primitives and custom sequences."""

import os
from unittest.mock import MagicMock
from unittest.mock import call
from unittest.mock import patch

import pytest

from esp_pylib import serial_reset as reset_mod
from esp_pylib.serial_reset import PIN_HIGH
from esp_pylib.serial_reset import PIN_LOW
from esp_pylib.serial_reset import classic_bootloader_reset
from esp_pylib.serial_reset import execute_custom_reset
from esp_pylib.serial_reset import hard_reset
from esp_pylib.serial_reset import parse_custom_reset_sequence
from esp_pylib.serial_reset import set_dtr
from esp_pylib.serial_reset import set_dtr_rts
from esp_pylib.serial_reset import set_rts
from esp_pylib.serial_reset import unix_tight_bootloader_reset
from esp_pylib.serial_reset import usb_jtag_bootloader_reset


def _make_port():
    """Build a Mock standing in for ``serial.Serial``.

    Uses :class:`MagicMock` so attribute access (``port.dtr``) and method
    calls (``port.setDTR(...)``) are recorded uniformly. We pre-seed
    ``port.dtr`` to ``False`` so the Windows usbser.sys workaround in
    :func:`set_rts` has a deterministic value to re-apply.
    """
    port = MagicMock()
    port.dtr = False
    return port


class TestSetDTR:
    def test_calls_set_dtr_with_state(self):
        port = _make_port()
        set_dtr(port, True)
        port.setDTR.assert_called_once_with(True)

    def test_pin_low_high_constants(self):
        port = _make_port()
        set_dtr(port, PIN_LOW)
        set_dtr(port, PIN_HIGH)
        assert port.setDTR.call_args_list == [call(True), call(False)]


class TestSetRTS:
    def test_sets_rts_then_reapplies_current_dtr(self):
        port = _make_port()
        port.dtr = True
        set_rts(port, True)
        # First the requested RTS write, then a dummy DTR write to flush
        # SET_CONTROL_LINE_STATE on the Windows usbser.sys driver.
        assert port.setRTS.call_args_list == [call(True)]
        assert port.setDTR.call_args_list == [call(True)]

    def test_dtr_workaround_uses_current_dtr_value(self):
        port = _make_port()
        port.dtr = False
        set_rts(port, False)
        port.setRTS.assert_called_once_with(False)
        port.setDTR.assert_called_once_with(False)


class TestSetDTRandRTS:
    @pytest.mark.skipif(os.name == 'nt', reason='POSIX-only ioctl path')
    def test_writes_combined_status(self):
        port = _make_port()
        port.fileno.return_value = 99
        # Initial status read returns 0; expect TIOCM_DTR | TIOCM_RTS to be set.
        with patch.object(reset_mod.fcntl, 'ioctl') as ioctl:
            # First call: TIOCMGET (returns 4 zero bytes)
            ioctl.side_effect = [b'\x00\x00\x00\x00', None]
            set_dtr_rts(port, dtr=True, rts=True)

        from esp_pylib.serial_reset import TIOCM_DTR
        from esp_pylib.serial_reset import TIOCM_RTS
        from esp_pylib.serial_reset import TIOCMGET
        from esp_pylib.serial_reset import TIOCMSET

        assert ioctl.call_count == 2
        # TIOCMGET first
        get_args = ioctl.call_args_list[0][0]
        assert get_args[0] == 99
        assert get_args[1] == TIOCMGET
        # TIOCMSET second, with DTR and RTS bits set
        set_args = ioctl.call_args_list[1][0]
        assert set_args[0] == 99
        assert set_args[1] == TIOCMSET
        import struct

        written = struct.unpack('I', set_args[2])[0]
        assert written & TIOCM_DTR
        assert written & TIOCM_RTS

    @pytest.mark.skipif(os.name == 'nt', reason='POSIX-only ioctl path')
    def test_clears_bits_when_state_is_false(self):
        port = _make_port()
        port.fileno.return_value = 7
        import struct

        from esp_pylib.serial_reset import TIOCM_DTR
        from esp_pylib.serial_reset import TIOCM_RTS

        # Initial status: both DTR and RTS already set; we want them cleared.
        initial = struct.pack('I', TIOCM_DTR | TIOCM_RTS)
        with patch.object(reset_mod.fcntl, 'ioctl') as ioctl:
            ioctl.side_effect = [initial, None]
            set_dtr_rts(port, dtr=False, rts=False)

        written = struct.unpack('I', ioctl.call_args_list[1][0][2])[0]
        assert not (written & TIOCM_DTR)
        assert not (written & TIOCM_RTS)

    def test_raises_on_windows(self):
        port = _make_port()
        with patch.object(reset_mod.os, 'name', 'nt'), pytest.raises(NotImplementedError):
            set_dtr_rts(port, True, True)


class TestParseCustomResetSequence:
    def test_dtr_step(self):
        assert parse_custom_reset_sequence('D0') == [{'type': 'dtr', 'state': False}]
        assert parse_custom_reset_sequence('D1') == [{'type': 'dtr', 'state': True}]

    def test_rts_step(self):
        assert parse_custom_reset_sequence('R1') == [{'type': 'rts', 'state': True}]

    def test_wait_step(self):
        assert parse_custom_reset_sequence('W0.1') == [{'type': 'wait', 'duration': 0.1}]
        assert parse_custom_reset_sequence('W2') == [{'type': 'wait', 'duration': 2.0}]

    def test_unix_combined_step(self):
        steps = parse_custom_reset_sequence('U1,0')
        assert steps == [{'type': 'dtr_rts', 'dtr': True, 'rts': False}]

    @pytest.mark.parametrize('seq', ['U1, 0', 'U 1,0', 'U 1 , 0', 'U1 ,0'])
    def test_unix_combined_step_tolerates_whitespace(self, seq):
        # The outer token already gets ``.strip()``-ed, but the comma split
        # used to leave inner whitespace untouched, breaking the strict
        # ``'0'``/``'1'`` match in ``_parse_bool_digit``.
        assert parse_custom_reset_sequence(seq) == [
            {'type': 'dtr_rts', 'dtr': True, 'rts': False},
        ]

    def test_classic_reset_round_trip(self):
        # The plan example in the docstring should parse to the equivalent of esptool's ClassicReset.
        steps = parse_custom_reset_sequence('D0|R1|W0.1|D1|R0|W0.05|D0')
        assert steps == [
            {'type': 'dtr', 'state': False},
            {'type': 'rts', 'state': True},
            {'type': 'wait', 'duration': 0.1},
            {'type': 'dtr', 'state': True},
            {'type': 'rts', 'state': False},
            {'type': 'wait', 'duration': 0.05},
            {'type': 'dtr', 'state': False},
        ]

    def test_empty_steps_are_skipped(self):
        # Trailing/leading separators or whitespace shouldn't break parsing.
        assert parse_custom_reset_sequence('|D0||W0.1|') == [
            {'type': 'dtr', 'state': False},
            {'type': 'wait', 'duration': 0.1},
        ]
        assert parse_custom_reset_sequence('  D0  |  W0.1  ') == [
            {'type': 'dtr', 'state': False},
            {'type': 'wait', 'duration': 0.1},
        ]

    def test_unknown_command_raises(self):
        with pytest.raises(ValueError, match='Invalid custom reset sequence step'):
            parse_custom_reset_sequence('X0')

    def test_invalid_dtr_argument_raises(self):
        with pytest.raises(ValueError, match='Invalid custom reset sequence step'):
            parse_custom_reset_sequence('Dabc')

    def test_invalid_wait_argument_raises(self):
        with pytest.raises(ValueError, match='Invalid custom reset sequence step'):
            parse_custom_reset_sequence('Wnope')

    def test_invalid_u_argument_count_raises(self):
        with pytest.raises(ValueError, match='Invalid custom reset sequence step'):
            parse_custom_reset_sequence('U1')

    @pytest.mark.parametrize('token', ['D2', 'D-1', 'D10', 'R2', 'U2,0', 'U0,2', 'U-1,0'])
    def test_strict_bool_digits_only(self, token):
        # Only the literal digits ``0`` and ``1`` are accepted for D/R/U
        # arguments; anything else (incl. multi-digit ``D10`` typos and
        # negative numbers) must raise rather than silently coerce to True.
        with pytest.raises(ValueError, match="Expected '0' or '1'"):
            parse_custom_reset_sequence(token)


class TestExecuteCustomReset:
    def test_dispatches_to_primitives(self):
        port = _make_port()
        with patch.object(reset_mod.time, 'sleep') as sleep:
            execute_custom_reset(port, 'D0|R1|W0.05|D1|R0')

        # DTR calls (D0, D1)
        assert port.setDTR.call_args_list[:1] == [call(False)]  # from D0
        # set_rts also writes DTR after the R1 write, so subsequent DTR writes interleave;
        # we mostly want to confirm setRTS got R1 and R0:
        assert call(True) in port.setRTS.call_args_list
        assert call(False) in port.setRTS.call_args_list
        sleep.assert_called_once_with(0.05)

    @pytest.mark.skipif(os.name == 'nt', reason='POSIX-only ioctl path')
    def test_executes_unix_combined_step(self):
        port = _make_port()
        port.fileno.return_value = 1
        with patch.object(reset_mod.fcntl, 'ioctl') as ioctl, patch.object(reset_mod.time, 'sleep'):
            ioctl.side_effect = [b'\x00\x00\x00\x00', None]
            execute_custom_reset(port, 'U1,0')

        from esp_pylib.serial_reset import TIOCMGET
        from esp_pylib.serial_reset import TIOCMSET

        kinds = [c[0][1] for c in ioctl.call_args_list]
        assert kinds == [TIOCMGET, TIOCMSET]

    def test_invalid_sequence_propagates_value_error(self):
        port = _make_port()
        with pytest.raises(ValueError):
            execute_custom_reset(port, 'Z0')


class TestModuleLevelImports:
    def test_fcntl_present_on_unix(self):
        if os.name != 'nt':
            assert hasattr(reset_mod, 'fcntl')

    def test_module_imports_on_any_platform(self):
        # Sanity check: importing must not raise on any supported platform.
        # (The test runner has already imported it; this confirms the symbols exist.)
        assert callable(reset_mod.set_dtr)
        assert callable(reset_mod.set_rts)
        assert callable(reset_mod.set_dtr_rts)


def _record_sequence(port, sleep_mock):
    """Build an interleaved trace of (kind, value) tuples for assertions.

    The named reset sequences are correctness-critical because they drive the
    chip's reset pins in a specific order; tests therefore need to lock down
    the exact ordering of DTR / RTS / sleep calls. We attach side effects
    that append to a shared list so the order is preserved across the three
    independent mock targets.

    Mocking subtlety: :func:`set_rts` always emits a trailing
    ``port.setDTR(port.dtr)`` to flush ``SET_CONTROL_LINE_STATE`` on Windows
    usbser.sys. That re-write is plumbing, not intentional sequence content,
    and it would clutter the trace. The disambiguation is structural: the
    workaround is the *only* place where a ``setDTR`` immediately follows a
    ``setRTS``, so we drop exactly the first ``setDTR`` after each ``setRTS``.
    The bare ``TestSetRTS`` cases already lock down the workaround itself.
    We also mirror pyserial by updating ``port.dtr`` from inside the
    ``setDTR`` side effect, since the workaround re-reads it.
    """
    trace: list[tuple[str, object]] = []
    pending_workaround = [False]

    def on_set_dtr(value):
        port.dtr = value
        if pending_workaround[0]:
            pending_workaround[0] = False
            return
        trace.append(('dtr', value))

    def on_set_rts(value):
        trace.append(('rts', value))
        pending_workaround[0] = True

    def on_sleep(duration):
        trace.append(('sleep', duration))

    port.setDTR.side_effect = on_set_dtr
    port.setRTS.side_effect = on_set_rts
    sleep_mock.side_effect = on_sleep
    return trace


class TestClassicBootloaderReset:
    def test_default_sequence_matches_legacy_classic_reset(self):
        # Mirrors esptool's ``ClassicReset.reset()`` exactly: DTR HIGH, RTS LOW,
        # 0.1s wait, DTR LOW, RTS HIGH, DEFAULT_RESET_DELAY wait, DTR HIGH.
        port = _make_port()
        with patch.object(reset_mod.time, 'sleep') as sleep:
            trace = _record_sequence(port, sleep)
            classic_bootloader_reset(port)
        assert trace == [
            ('dtr', PIN_HIGH),
            ('rts', PIN_LOW),
            ('sleep', 0.1),
            ('dtr', PIN_LOW),
            ('rts', PIN_HIGH),
            ('sleep', 0.05),  # DEFAULT_RESET_DELAY
            ('dtr', PIN_HIGH),
        ]

    def test_timing_parameters_are_respected(self):
        # esp-idf-monitor passes per-chip ``enter_boot_set`` / ``enter_boot_unset``
        # values; verify both delays are forwarded to ``time.sleep``.
        port = _make_port()
        with patch.object(reset_mod.time, 'sleep') as sleep:
            trace = _record_sequence(port, sleep)
            classic_bootloader_reset(port, enter_boot_delay=0.42, reset_delay=0.07)
        sleeps = [v for kind, v in trace if kind == 'sleep']
        assert sleeps == [0.42, 0.07]


class TestUnixTightBootloaderReset:
    @pytest.mark.skipif(os.name == 'nt', reason='POSIX-only ioctl path')
    def test_uses_set_dtr_rts_for_each_transition(self):
        # The whole point of the tight reset is that every transition writes
        # both pins atomically via ``set_dtr_rts``; the trailing ``set_dtr``
        # is the documented "ensure IO0=HIGH" safety write.
        port = _make_port()
        port.fileno.return_value = 11
        with patch.object(reset_mod, 'set_dtr_rts') as set_both, patch.object(
            reset_mod, 'set_dtr'
        ) as set_d, patch.object(reset_mod.time, 'sleep') as sleep:
            unix_tight_bootloader_reset(port, enter_boot_delay=0.1, reset_delay=0.05)
        assert set_both.call_args_list == [
            call(port, PIN_HIGH, PIN_HIGH),
            call(port, PIN_LOW, PIN_LOW),
            call(port, PIN_HIGH, PIN_LOW),
            call(port, PIN_LOW, PIN_HIGH),
            call(port, PIN_HIGH, PIN_HIGH),
        ]
        set_d.assert_called_once_with(port, PIN_HIGH)
        assert sleep.call_args_list == [call(0.1), call(0.05)]

    def test_raises_on_windows(self):
        # ``set_dtr_rts`` itself raises NotImplementedError on Windows; we
        # verify the wrapper propagates rather than silently degrading, so
        # tools must explicitly fall back to ``classic_bootloader_reset``.
        port = _make_port()
        with patch.object(reset_mod.os, 'name', 'nt'), pytest.raises(NotImplementedError):
            unix_tight_bootloader_reset(port)


class TestUsbJtagBootloaderReset:
    def test_sequence_matches_legacy_usb_jtag_reset(self):
        # Mirrors esptool's ``USBJTAGSerialReset.reset()``. Note the trailing
        # RTS toggles intentionally walk through (1, 1) instead of (0, 0)
        # because Windows usbser.sys only flushes on RTS changes.
        port = _make_port()
        with patch.object(reset_mod.time, 'sleep') as sleep:
            trace = _record_sequence(port, sleep)
            usb_jtag_bootloader_reset(port)
        assert trace == [
            ('rts', PIN_HIGH),
            ('dtr', PIN_HIGH),
            ('sleep', 0.1),
            ('dtr', PIN_LOW),
            ('rts', PIN_HIGH),
            ('sleep', 0.1),
            ('rts', PIN_LOW),
            ('dtr', PIN_HIGH),
            ('rts', PIN_LOW),
            ('sleep', 0.1),
            ('dtr', PIN_HIGH),
            ('rts', PIN_HIGH),
        ]


class TestHardReset:
    def test_default_sequence_pulses_rts_once(self):
        # The default (UART bridge) path: RTS LOW, hold 0.1s, RTS HIGH.
        # No post-release sleep — that's reserved for the USB variant.
        port = _make_port()
        with patch.object(reset_mod.time, 'sleep') as sleep:
            trace = _record_sequence(port, sleep)
            hard_reset(port)
        assert trace == [
            ('rts', PIN_LOW),
            ('sleep', 0.1),
            ('rts', PIN_HIGH),
        ]

    def test_usb_variant_waits_for_re_enumeration(self):
        # Chips on the internal USB peripheral disappear from the bus during
        # reset; esptool's ``HardReset(uses_usb=True)`` path waits 0.2s after
        # raising EN so subsequent DTR/RTS writes have a port to land on.
        port = _make_port()
        with patch.object(reset_mod.time, 'sleep') as sleep:
            trace = _record_sequence(port, sleep)
            hard_reset(port, hold_delay=0.2, post_release_delay=0.2)
        assert trace == [
            ('rts', PIN_LOW),
            ('sleep', 0.2),
            ('rts', PIN_HIGH),
            ('sleep', 0.2),
        ]

    def test_zero_post_release_skips_trailing_sleep(self):
        # We treat ``post_release_delay=0`` as "no extra wait" and skip the
        # call entirely so callers don't need to special-case the default.
        port = _make_port()
        with patch.object(reset_mod.time, 'sleep') as sleep:
            hard_reset(port, hold_delay=0.05, post_release_delay=0)
        assert sleep.call_args_list == [call(0.05)]
