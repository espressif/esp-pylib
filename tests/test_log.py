# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Tests for esp_pylib.logger (EspLog, EspLogBase, set_logger, output)."""

import sys
from io import StringIO
from typing import Union
from unittest.mock import patch

import pytest

from esp_pylib.logger import EspLog
from esp_pylib.logger import EspLogBase
from esp_pylib.logger import Verbosity
from esp_pylib.logger import log


class CaptureLogger(EspLogBase):
    """Logger that records calls for testing."""

    def __init__(self):
        self.print_calls = []
        self.error_calls = []
        self.warning_calls = []
        self.note_calls = []
        self.debug_calls = []
        self.die_calls = []

    def print(self, *args, **kwargs):
        self.print_calls.append((args, kwargs))

    def err(self, message: str, suggestion=None):
        self.error_calls.append((message, suggestion))

    def warn(self, message: str, suggestion=None):
        self.warning_calls.append((message, suggestion))

    def note(self, message: str):
        self.note_calls.append((message,))

    def debug(self, message: str):
        self.debug_calls.append((message,))

    def die(self, message: str, exit_code: int = 1, suggestion=None):
        self.die_calls.append((message, exit_code, suggestion))

    def set_verbosity(self, mode: Union[int, str]):
        self.verbosity = mode


@pytest.fixture(autouse=True)
def reset_logger():
    """Reset the global logger after each test so tests don't affect each other."""
    yield
    EspLog._reset()


class TestSingleton:
    def test_singleton_identity(self):
        a = EspLog()
        b = EspLog()
        assert a is b
        # log is a proxy that delegates to the current EspLog singleton
        assert log.instance is a

    def test_singleton_after_reset_is_new_instance(self):
        original = EspLog()
        EspLog._reset()
        new_logger = EspLog()
        assert new_logger is not original
        assert type(new_logger) is EspLog


class TestSetLogger:
    def test_set_logger_accepts_esp_log_base(self):
        original = EspLog()
        custom = CaptureLogger()
        EspLog.set_logger(custom)
        current = EspLog()
        assert current is custom
        assert current is not original

    def test_set_logger_rejects_non_base(self):
        with pytest.raises(TypeError, match='Logger must implement the EspLogBase interface'):
            EspLog.set_logger(object())

    def test_set_logger_rejects_incomplete_class(self):
        class Incomplete:
            def print(self, *args, **kwargs):
                pass

        with pytest.raises(TypeError, match='Logger must implement the EspLogBase interface'):
            EspLog.set_logger(Incomplete())

    def test_reset_restores_default_esp_log(self):
        EspLog.set_logger(CaptureLogger())
        assert type(EspLog()) is CaptureLogger
        EspLog._reset()
        assert type(EspLog()) is EspLog


class TestPrint:
    def test_print_output_with_fresh_logger(self):
        EspLog._reset()
        out = StringIO()
        with patch('sys.stdout', out):
            logger = EspLog()
            logger.print('hello')
        assert out.getvalue() == 'hello\n'

    def test_print_silent(self):
        EspLog._reset()
        out = StringIO()
        err = StringIO()
        with patch('sys.stdout', out), patch('sys.stderr', err):
            logger = EspLog()
            logger.set_verbosity(Verbosity.SILENT)
            logger.print('hidden')
            logger.debug('debug hidden')
            logger.note('note hidden')
            logger.warn('warning hidden')
            logger.err('error visible')
        assert out.getvalue() == ''
        err_value = err.getvalue()
        assert 'ERROR: error visible' in err_value
        assert 'WARNING: warning hidden' not in err_value
        assert 'debug hidden' not in err_value
        assert 'note hidden' not in err_value

    def test_print_verbose(self):
        EspLog._reset()
        out = StringIO()
        with patch('sys.stdout', out):
            logger = EspLog()
            logger.set_verbosity(Verbosity.VERBOSE)
            logger.debug('visible')
        assert out.getvalue() == 'visible\n'


class TestErrorWarningNote:
    def test_error_contains_message(self):
        EspLog._reset()
        err = StringIO()
        with patch('sys.stderr', err):
            logger = EspLog()
            logger.err('something broke')
        text = err.getvalue()
        assert 'ERROR:' in text
        assert 'something broke' in text

    def test_warning_contains_message(self):
        EspLog._reset()
        err = StringIO()
        with patch('sys.stderr', err):
            logger = EspLog()
            logger.warn('be careful')
        text = err.getvalue()
        assert 'WARNING:' in text
        assert 'be careful' in text

    def test_note_contains_message(self):
        EspLog._reset()
        out = StringIO()
        with patch('sys.stdout', out):
            logger = EspLog()
            logger.note('info here')
        text = out.getvalue()
        assert 'Note:' in text
        assert 'info here' in text


class TestDebug:
    def test_debug_shown_when_verbose(self):
        EspLog._reset()
        stdout = StringIO()
        with patch('sys.stdout', stdout):
            logger = EspLog()
            logger.set_verbosity(Verbosity.VERBOSE)
            logger.debug('debug line')
        assert 'debug line' in stdout.getvalue()

    def test_debug_hidden_when_not_verbose(self):
        EspLog._reset()
        err = StringIO()
        with patch('sys.stderr', err):
            logger = EspLog()
            logger.set_verbosity(Verbosity.NORMAL)
            logger.debug('debug line')
        assert err.getvalue() == ''


class TestDie:
    def test_die_calls_error_and_exits(self):
        EspLog._reset()
        err = StringIO()
        with patch('sys.stderr', err), patch.object(sys, 'exit') as mock_exit:
            logger = EspLog()
            logger.die('fatal', exit_code=2, suggestion='fix it')
        assert 'ERROR:' in err.getvalue()
        assert 'fatal' in err.getvalue()
        mock_exit.assert_called_once_with(2)

    def test_die_default_exit_code(self):
        EspLog._reset()
        with patch('sys.stderr', StringIO()), patch.object(sys, 'exit') as mock_exit:
            logger = EspLog()
            logger.die('oops')
        mock_exit.assert_called_once_with(1)


class TestCallSiteReporting:
    """Verify the file/line reported to the IDE WebSocket points at the user's caller,
    even when err/warn are reached via internal helpers like die().

    These tests force ``is_enabled()`` to True so the call-site lookup happens; in real CLI
    usage the lookup is skipped (see :class:`TestSkipCallSiteWhenIdeDisabled`).
    """

    def test_err_reports_direct_caller(self):
        EspLog._reset()
        with patch('sys.stderr', StringIO()), patch('esp_pylib.logger._ws_is_enabled', return_value=True), patch(
            'esp_pylib.logger.send_log_message'
        ) as mock_send:
            logger = EspLog()
            logger.err('boom')
            expected_line = sys._getframe().f_lineno - 1
        mock_send.assert_called_once()
        _typ, _msg, _suggestion, file, line = mock_send.call_args[0]
        assert file == __file__
        assert line == expected_line

    def test_warn_reports_direct_caller(self):
        EspLog._reset()
        with patch('sys.stderr', StringIO()), patch('esp_pylib.logger._ws_is_enabled', return_value=True), patch(
            'esp_pylib.logger.send_log_message'
        ) as mock_send:
            logger = EspLog()
            logger.warn('careful')
            expected_line = sys._getframe().f_lineno - 1
        mock_send.assert_called_once()
        _typ, _msg, _suggestion, file, line = mock_send.call_args[0]
        assert file == __file__
        assert line == expected_line

    def test_die_reports_user_caller_not_die_method(self):
        """Regression: die() calls err(); call site must be the user's die() call,
        not the err() call inside die() in logger.py."""
        EspLog._reset()
        with patch('sys.stderr', StringIO()), patch.object(sys, 'exit'), patch(
            'esp_pylib.logger._ws_is_enabled', return_value=True
        ), patch('esp_pylib.logger.send_log_message') as mock_send:
            logger = EspLog()
            logger.die('fatal')
            expected_line = sys._getframe().f_lineno - 1
        mock_send.assert_called_once()
        _typ, _msg, _suggestion, file, line = mock_send.call_args[0]
        assert file == __file__, f'Expected test file, got {file} (likely points into logger.py)'
        assert line == expected_line


class TestSkipCallSiteWhenIdeDisabled:
    """Plain CLI usage (no IDE WebSocket configured) must not pay the cost of stack walking
    or build a payload that ``send_log_message`` would immediately discard."""

    def test_warn_skips_call_site_and_send_when_disabled(self):
        EspLog._reset()
        with patch('sys.stderr', StringIO()), patch(
            'esp_pylib.logger._ws_is_enabled', return_value=False
        ) as mock_enabled, patch('esp_pylib.logger.send_log_message') as mock_send, patch.object(
            EspLog, '_get_call_site'
        ) as mock_callsite:
            logger = EspLog()
            logger.warn('careful')

        mock_enabled.assert_called_once()
        mock_callsite.assert_not_called()
        mock_send.assert_not_called()

    def test_err_skips_call_site_and_send_when_disabled(self):
        EspLog._reset()
        with patch('sys.stderr', StringIO()), patch(
            'esp_pylib.logger._ws_is_enabled', return_value=False
        ) as mock_enabled, patch('esp_pylib.logger.send_log_message') as mock_send, patch.object(
            EspLog, '_get_call_site'
        ) as mock_callsite:
            logger = EspLog()
            logger.err('boom')

        mock_enabled.assert_called_once()
        mock_callsite.assert_not_called()
        mock_send.assert_not_called()


class TestCaptureLoggerIntegration:
    def test_custom_logger_receives_all_calls(self):
        custom = CaptureLogger()
        EspLog.set_logger(custom)
        current = EspLog()  # current singleton is custom
        current.print('a', 'b')
        current.err('e')
        current.warn('w')
        current.note('n')
        current.debug('d')
        assert custom.print_calls == [(('a', 'b'), {})]
        assert custom.error_calls == [('e', None)]
        assert custom.warning_calls == [('w', None)]
        assert custom.note_calls == [('n',)]
        assert custom.debug_calls == [('d',)]
