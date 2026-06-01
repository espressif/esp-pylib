# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Tests for esp_pylib.logger (EspLog, EspLogBase, set_logger, output)."""

from __future__ import annotations

import io
import re
import sys
from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console

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
        self.hint_calls = []
        self.debug_calls = []
        self.die_calls = []
        self.progress_bar_calls = []
        self.counter_line_calls = []

    def print(self, *args, **kwargs):
        self.print_calls.append((args, kwargs))

    def err(self, message: str, suggestion=None):
        self.error_calls.append((message, suggestion))

    def warn(self, message: str, suggestion=None):
        self.warning_calls.append((message, suggestion))

    def note(self, message: str):
        self.note_calls.append((message,))

    def hint(self, message: str):
        self.hint_calls.append((message,))

    def debug(self, message: str):
        self.debug_calls.append((message,))

    def die(self, message: str, exit_code: int = 1, suggestion=None):
        self.die_calls.append((message, exit_code, suggestion))

    def set_verbosity(self, mode: int | str):
        self.verbosity = mode

    def progress_bar(
        self,
        cur_iter: int,
        total_iters: int,
        prefix: str = '',
        suffix: str = '',
        bar_length: int = 30,
    ) -> None:
        self.progress_bar_calls.append((cur_iter, total_iters, prefix, suffix, bar_length))

    def counter_line(self, prefix: str, suffix: str, *, final: bool = False) -> None:
        self.counter_line_calls.append((prefix, suffix, final))


@pytest.fixture(autouse=True)
def reset_logger():
    """Reset the global logger after each test so tests don't affect each other."""
    yield
    EspLog._reset()


def assert_progress_bar_not_empty(output: str, prefix: str = 'Progress: ', percent: str = '50.0%') -> None:
    assert prefix in output
    assert percent in output
    bar_segment = output.split(prefix, 1)[1].split(percent, 1)[0]
    assert any(not ch.isspace() for ch in bar_segment)


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

    def test_proxy_creates_default_logger_on_first_use(self):
        # ``from esp_pylib.logger import log; log.note(...)`` must work even
        # when nothing has constructed ``EspLog()`` or called ``set_logger()``
        # yet — the proxy lazily builds the default singleton on first access.
        EspLog._reset()
        assert EspLog.instance is None
        out = StringIO()
        with patch('sys.stdout', out):
            log.note('hello')
        assert 'NOTE: hello' in out.getvalue()
        assert type(EspLog.instance) is EspLog


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

    def test_print_follows_reassigned_stdout(self):
        # ``Console`` binds ``sys.stdout`` at construction. Build the logger
        # first, *then* reassign ``sys.stdout`` (as ``contextlib.redirect_stdout``
        # does). ``print`` must follow the new stream like the builtin ``print``
        # did, instead of writing to the stream captured at construction.
        EspLog._reset()
        logger = EspLog()
        out = StringIO()
        with patch('sys.stdout', out):
            logger.print('redirected')
        assert out.getvalue() == 'redirected\n'

    def test_print_silent_with_reassigned_stdout(self):
        # Following a reassigned ``sys.stdout`` must not defeat ``--silent``:
        # the rerouting swaps the Console while keeping ``file is None``
        # semantics, so the silent gate still suppresses stdout output.
        EspLog._reset()
        logger = EspLog()
        logger.set_verbosity(Verbosity.SILENT)
        out = StringIO()
        with patch('sys.stdout', out):
            logger.print('should be suppressed')
        assert out.getvalue() == ''

    def test_warn_err_follow_reassigned_stderr(self):
        # Mirror of ``test_print_follows_reassigned_stdout`` for stderr: build the
        # logger first, *then* reassign ``sys.stderr`` (as
        # ``contextlib.redirect_stderr`` does). ``warn``/``err`` must follow the
        # new stream instead of writing to the one captured at construction.
        EspLog._reset()
        logger = EspLog()
        err = StringIO()
        with patch('sys.stderr', err):
            logger.warn('reassigned warning')
            logger.err('reassigned error')
        text = err.getvalue()
        assert 'WARNING:' in text
        assert 'reassigned warning' in text
        assert 'ERROR:' in text
        assert 'reassigned error' in text


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
        assert 'NOTE:' in text
        assert 'info here' in text

    def test_hint_contains_message_on_stdout(self):
        EspLog._reset()
        out = StringIO()
        with patch('sys.stdout', out):
            logger = EspLog()
            logger.hint('try adding esp_wifi to REQUIRES')
        text = out.getvalue()
        assert 'HINT:' in text
        assert 'try adding esp_wifi to REQUIRES' in text

    def test_hint_hidden_when_silent(self):
        EspLog._reset()
        out = StringIO()
        with patch('sys.stdout', out):
            logger = EspLog()
            logger.set_verbosity(Verbosity.SILENT)
            logger.hint('suppressed')
        assert out.getvalue() == ''


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
    usage the lookup is skipped (see `TestSkipCallSiteWhenIdeDisabled`).
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

    def test_warn_silent_still_forwards_to_ide(self):
        """Silent mode suppresses stderr but must not drop IDE diagnostics."""
        EspLog._reset()
        with patch('sys.stderr', StringIO()) as err, patch('esp_pylib.logger._ws_is_enabled', return_value=True), patch(
            'esp_pylib.logger.send_log_message'
        ) as mock_send:
            logger = EspLog()
            logger.set_verbosity(Verbosity.SILENT)
            logger.warn('quiet warning')
        assert 'WARNING:' not in err.getvalue()
        mock_send.assert_called_once()
        assert mock_send.call_args[0][1] == 'quiet warning'


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


class TestProgressBar:
    def test_interactive_uses_rich_bar_character(self):
        EspLog._reset()
        out = StringIO()
        fake_console = Console(file=out, force_terminal=True, highlight=False, emoji=False)
        with patch('sys.stdout', out):
            logger = EspLog()
            with patch.object(logger, '_get_interactive_console', return_value=fake_console):
                logger.progress_bar(
                    cur_iter=2,
                    total_iters=4,
                    prefix='Progress: ',
                    suffix=' (2/4)',
                    bar_length=10,
                )
        output = out.getvalue()
        assert_progress_bar_not_empty(output)

    def test_interactive_no_color_still_renders_progress_bar(self):
        EspLog._reset()
        out = StringIO()
        # Mirror what EspLog(no_color=True) would build for ``self._stdout``;
        # ``_get_interactive_console`` returns that Console in production.
        fake_console = Console(file=out, force_terminal=True, no_color=True, highlight=False, emoji=False)
        with patch('sys.stdout', out):
            logger = EspLog(no_color=True)
            with patch.object(logger, '_get_interactive_console', return_value=fake_console):
                logger.progress_bar(
                    cur_iter=2,
                    total_iters=4,
                    prefix='Progress: ',
                    suffix=' (2/4)',
                    bar_length=10,
                )
        output = out.getvalue()
        assert '50.0%' in output
        assert 'Progress:' in output
        # Cursor controls (e.g. erase line) may still appear; typical SGR color is absent.
        assert '\x1b[38' not in output and '\x1b[48' not in output
        # Fixed-width plain rendering: the bar between prefix and suffix
        # must always be exactly ``bar_length`` cells wide so ``50.0%``
        # renders in the same column on every redraw, regardless of how far
        # the bar has filled in. With ``cur_iter=2 total_iters=4
        # bar_length=10``, Rich's half-bar logic gives exactly 5 ``━`` chars
        # followed by 5 spaces. ``progress_bar`` formats the suffix as
        # ``' {percent:>5}%{suffix} '`` so the percent is preceded by 2
        # spaces (one leading + one from the right-aligned ``50.0``); split
        # on those 2 spaces to extract the bar exactly.
        bar_segment = output.split('Progress: ', 1)[1].split('  50.0%', 1)[0]
        assert bar_segment == '━━━━━     ', repr(bar_segment)

    def test_non_interactive_uses_rich_bar_on_stream(self):
        EspLog._reset()
        out = StringIO()
        with patch('sys.stdout', out):
            logger = EspLog()
            with patch.object(logger, '_get_interactive_console', return_value=None):
                logger.progress_bar(
                    cur_iter=2,
                    total_iters=4,
                    prefix='Progress: ',
                    suffix=' (2/4)',
                    bar_length=10,
                )
        text = out.getvalue()
        assert_progress_bar_not_empty(text)

    def test_verbose_piped_progress_ends_each_line(self):
        EspLog._reset()
        out = StringIO()
        with patch('sys.stdout', out):
            logger = EspLog()
            logger.set_verbosity(Verbosity.VERBOSE)
            with patch.object(logger, '_get_interactive_console', return_value=None):
                logger.progress_bar(cur_iter=1, total_iters=10, prefix='P1 ', suffix='')
                logger.progress_bar(cur_iter=10, total_iters=10, prefix='P2 ', suffix='')
        text = out.getvalue()
        assert text.endswith('\n')
        assert text.count('\n') >= 2

    def test_completion_prints_newline(self):
        EspLog._reset()
        out = StringIO()
        fake_console = Console(file=out, force_terminal=True, highlight=False, emoji=False)
        with patch('sys.stdout', out):
            logger = EspLog()
            with patch.object(logger, '_get_interactive_console', return_value=fake_console):
                logger.progress_bar(
                    cur_iter=4,
                    total_iters=4,
                    prefix='Done: ',
                    suffix='',
                    bar_length=10,
                )
        assert out.getvalue().endswith('\n')

    def test_silent_suppresses_progress(self):
        EspLog._reset()
        out = StringIO()
        fake_console = Console(file=out, force_terminal=True, highlight=False, emoji=False)
        with patch('sys.stdout', out):
            logger = EspLog()
            logger.set_verbosity(Verbosity.SILENT)
            with patch.object(logger, '_get_interactive_console', return_value=fake_console):
                logger.progress_bar(cur_iter=1, total_iters=2)
        assert out.getvalue() == ''

    def test_zero_total_renders_complete_bar(self):
        # 0/0 is treated as "nothing to do, already complete" and rendered as a
        # full bar so empty work loops still surface a visible progress line
        # (matches the prior rich.Progress behaviour expected by esp-idf-sbom).
        EspLog._reset()
        out = StringIO()
        fake_console = Console(file=out, force_terminal=True, highlight=False, emoji=False)
        with patch('sys.stdout', out):
            logger = EspLog()
            with patch.object(logger, '_get_interactive_console', return_value=fake_console):
                logger.progress_bar(cur_iter=0, total_iters=0, prefix='Z ', suffix=' 0/0 [0s]')
        text = out.getvalue()
        assert text != ''
        assert '100.0%' in text
        assert '0/0' in text
        assert 'Z' in text
        assert text.endswith('\n')

    def test_cp1252_stdout_uses_ascii_bar(self):
        """Plain progress bar on cp1252 uses ASCII glyphs (``=``/``>``), not Unicode.

        Rich may auto-detect color on a TTY; pin ``no_color`` and ``color_system=None``
        so the test always exercises the padded plain renderer and ASCII fallback.
        """
        EspLog._reset()
        buffer = io.BytesIO()
        cp1252_out = io.TextIOWrapper(buffer, encoding='cp1252', newline='', write_through=True)
        cp1252_out.isatty = lambda: True  # type: ignore[method-assign]
        fake_console = Console(
            file=cp1252_out,
            force_terminal=True,
            no_color=True,
            color_system=None,
            highlight=False,
            emoji=False,
        )
        with patch('sys.stdout', cp1252_out):
            logger = EspLog()
            with patch.object(logger, '_get_interactive_console', return_value=fake_console):
                logger.progress_bar(
                    cur_iter=1,
                    total_iters=4,
                    prefix='Progress: ',
                    suffix=' (1/4)',
                    bar_length=10,
                )
                partial = buffer.getvalue().decode('cp1252')
                logger.progress_bar(
                    cur_iter=4,
                    total_iters=4,
                    prefix='Reading: ',
                    bar_length=10,
                )
                complete = buffer.getvalue().decode('cp1252')
        assert '\u2501' not in partial and '\u2501' not in complete
        assert '25.0%' in partial
        bar_segment = partial.split('Progress: ', 1)[1].split('  25.0%', 1)[0]
        assert bar_segment == '==>       ', repr(bar_segment)
        assert '==========' in complete
        assert '100.0%' in complete

    def test_negative_total_is_noop(self):
        EspLog._reset()
        out = StringIO()
        fake_console = Console(file=out, force_terminal=True, highlight=False, emoji=False)
        with patch('sys.stdout', out):
            logger = EspLog()
            with patch.object(logger, '_get_interactive_console', return_value=fake_console):
                logger.progress_bar(cur_iter=0, total_iters=-1)
        assert out.getvalue() == ''


class TestProgress:
    def test_progress_calls_progress_bar(self):
        custom = CaptureLogger()
        EspLog.set_logger(custom)
        current = EspLog()
        with current.progress(total=4, description='Test') as bar:
            bar.update(2)
            bar.update(2)
        assert len(custom.progress_bar_calls) == 2
        assert custom.progress_bar_calls[0][0] == 2
        assert custom.progress_bar_calls[0][1] == 4
        assert custom.progress_bar_calls[0][2].startswith('Test ')
        assert '/4' in custom.progress_bar_calls[0][3]
        assert '[' in custom.progress_bar_calls[0][3] and ']' in custom.progress_bar_calls[0][3]

    def test_progress_auto_completes_on_exit(self):
        custom = CaptureLogger()
        EspLog.set_logger(custom)
        current = EspLog()
        with current.progress(total=4, description='X') as bar:
            bar.update(1)
        assert custom.progress_bar_calls[-1][0] == 4
        assert custom.progress_bar_calls[-1][1] == 4

    def test_progress_description_change(self):
        custom = CaptureLogger()
        EspLog.set_logger(custom)
        current = EspLog()
        with current.progress(total=2, description='a') as bar:
            bar.update(1, description='pkg_a')
            bar.update(1, description='pkg_b')
        assert 'pkg_a' in custom.progress_bar_calls[0][2]
        assert 'pkg_b' in custom.progress_bar_calls[1][2]

    def test_progress_elapsed_time_format(self):
        custom = CaptureLogger()
        EspLog.set_logger(custom)
        current = EspLog()
        with patch('esp_pylib.logger.time.monotonic', side_effect=[0.0, 45.0]):
            with current.progress(total=1, description='T') as bar:
                bar.update(1)
        suffix = custom.progress_bar_calls[0][3]
        assert '[45s]' in suffix or '45' in suffix

    def test_progress_zero_total(self):
        # When the work set is empty, the context manager emits an initial bar
        # so the user still sees the activity line (e.g. "Searching ... 0/0").
        # bar.update() remains a no-op so callers don't get spurious renders.
        custom = CaptureLogger()
        EspLog.set_logger(custom)
        current = EspLog()
        with current.progress(total=0, description='N') as bar:
            bar.update(1)
        assert len(custom.progress_bar_calls) == 1
        cur, total, prefix, suffix, _ = custom.progress_bar_calls[0]
        assert cur == 0
        assert total == 0
        assert prefix.startswith('N')
        assert '0/0' in suffix

    def test_progress_with_real_logger_tty(self):
        EspLog._reset()
        out = StringIO()
        fake_console = Console(file=out, force_terminal=True, highlight=False, emoji=False)
        with patch('sys.stdout', out):
            logger = EspLog()
            with patch.object(logger, '_get_interactive_console', return_value=fake_console):
                with logger.progress(total=2, description='P') as bar:
                    bar.update(1)
                    bar.update(1)
        text = out.getvalue()
        assert text != ''
        assert 'P' in text
        assert '%' in text
        assert '100' in text

    def test_progress_with_real_logger_non_tty(self):
        EspLog._reset()
        out = StringIO()
        with patch('sys.stdout', out):
            logger = EspLog()
            with patch.object(logger, '_get_interactive_console', return_value=None):
                with logger.progress(total=2, description='P') as bar:
                    bar.update(1)
                    bar.update(1)
        text = out.getvalue()
        assert 'P' in text
        assert '50.0%' in text
        assert '100.0%' in text
        # Non-TTY path emits one line per update.
        assert text.count('\n') >= 2

    def test_progress_stderr_routing(self):
        EspLog._reset()
        err = StringIO()
        fake_stderr = Console(file=err, force_terminal=True, highlight=False, emoji=False)
        with patch('sys.stderr', err):
            logger = EspLog()
            logger._stderr = fake_stderr  # type: ignore[attr-defined]
            with patch.object(logger, '_get_interactive_console', return_value=fake_stderr):
                with logger.progress(total=1, description='E', file=sys.stderr) as bar:
                    bar.update(1)
        assert 'E' in err.getvalue()
        assert err.getvalue() != ''

    def test_progress_disable_skips_progress_bar(self):
        custom = CaptureLogger()
        EspLog.set_logger(custom)
        current = EspLog()
        with current.progress(total=4, disable=True) as bar:
            bar.update(4)
        assert custom.progress_bar_calls == []

    def test_progress_does_not_auto_complete_on_exception(self):
        """Bar must not jump to 100% right before an exception is raised."""
        custom = CaptureLogger()
        EspLog.set_logger(custom)
        current = EspLog()
        with pytest.raises(RuntimeError):
            with current.progress(total=10, description='X') as bar:
                bar.update(3)
                raise RuntimeError('boom')
        # Only the explicit update(3) should be visible — no synthetic 10/10.
        assert len(custom.progress_bar_calls) == 1
        assert custom.progress_bar_calls[0][0] == 3
        assert custom.progress_bar_calls[0][1] == 10

    def test_progress_negative_advance_is_clamped(self):
        custom = CaptureLogger()
        EspLog.set_logger(custom)
        current = EspLog()
        with current.progress(total=10, description='R') as bar:
            bar.update(3)
            bar.update(-100)  # would underflow without clamping
            bar.update(2)
        # 3, then 0 (clamped), then 2, then 10 (auto-complete on clean exit).
        currents = [call[0] for call in custom.progress_bar_calls]
        assert currents == [3, 0, 2, 10]
        # The key invariant: never goes negative.
        assert all(c >= 0 for c in currents)

    def test_progress_unit_bytes(self):
        custom = CaptureLogger()
        EspLog.set_logger(custom)
        current = EspLog()
        with current.progress(total=5_242_880, description='Uploading', unit='B') as bar:
            bar.update(1_258_291)
        suffix = custom.progress_bar_calls[0][3]
        assert '1.20MB/5.00MB' in suffix

    def test_progress_unit_bytes_tty(self):
        EspLog._reset()
        out = StringIO()
        fake_console = Console(file=out, force_terminal=True, highlight=False, emoji=False)
        with patch('sys.stdout', out):
            logger = EspLog()
            with patch.object(logger, '_get_interactive_console', return_value=fake_console):
                with logger.progress(total=5_242_880, description='Up', unit='B') as bar:
                    bar.update(1_258_291)
        assert '1.20MB/5.00MB' in out.getvalue()

    def test_progress_rejects_none_total(self):
        custom = CaptureLogger()
        EspLog.set_logger(custom)
        current = EspLog()
        with pytest.raises(TypeError, match='counter\\(\\) instead'):
            with current.progress(total=None, description='X'):
                pass

    def test_counter_mode(self):
        custom = CaptureLogger()
        EspLog.set_logger(custom)
        current = EspLog()
        with current.counter(description='Collecting') as bar:
            bar.update(1)
            bar.update(41)
        calls = custom.counter_line_calls
        assert custom.progress_bar_calls == []
        assert calls[0][0] == 'Collecting: '
        assert calls[0][1].startswith('0 [')
        assert calls[1][1].startswith('1 [')
        assert calls[2][1].startswith('42 [')
        assert calls[-1][2] is True

    def test_counter_disable(self):
        custom = CaptureLogger()
        EspLog.set_logger(custom)
        current = EspLog()
        with current.counter(description='Scan', disable=True) as bar:
            bar.update(5)
        assert custom.counter_line_calls == []

    def test_counter_tty(self):
        EspLog._reset()
        out = StringIO()
        fake_console = Console(file=out, force_terminal=True, highlight=False, emoji=False)
        with patch('sys.stdout', out):
            logger = EspLog()
            with patch.object(logger, '_get_interactive_console', return_value=fake_console):
                with logger.counter(description='Items') as bar:
                    bar.update(3)
        text = out.getvalue()
        assert 'Items: 3' in text
        assert '%' not in text

    def test_counter_non_tty_no_duplicate_final_line(self):
        """Without in-place overwrite each update is its own line, so the
        context manager's final flush must not reprint the last counter line."""
        EspLog._reset()
        out = StringIO()
        with patch('sys.stdout', out):
            logger = EspLog()
            with patch.object(logger, '_get_interactive_console', return_value=None):
                with logger.counter(description='Items') as bar:
                    bar.update(3)
        lines = [line for line in out.getvalue().splitlines() if line]
        # One line for the initial emit and one per update; no duplicated final line.
        assert sum(line.startswith('Items: 3 ') for line in lines) == 1
        assert lines[-1].startswith('Items: 3 ')

    def test_counter_verbose_no_duplicate_final_line(self):
        """Verbose mode already terminates each line, so the final flush must
        not reprint the last counter line."""
        EspLog._reset()
        out = StringIO()
        fake_console = Console(file=out, force_terminal=True, highlight=False, emoji=False)
        with patch('sys.stdout', out):
            logger = EspLog()
            logger.set_verbosity(Verbosity.VERBOSE)
            with patch.object(logger, '_get_interactive_console', return_value=fake_console):
                with logger.counter(description='Items') as bar:
                    bar.update(3)
        lines = [line for line in out.getvalue().splitlines() if line]
        assert sum(line.startswith('Items: 3 ') for line in lines) == 1


class TestProgressBarClamping:
    def test_progress_bar_clamps_overshoot(self):
        """Direct callers (bypassing ProgressTask) cannot render >100%."""
        EspLog._reset()
        out = StringIO()
        fake_console = Console(file=out, force_terminal=True, highlight=False, emoji=False)
        with patch('sys.stdout', out):
            logger = EspLog()
            with patch.object(logger, '_get_interactive_console', return_value=fake_console):
                logger.progress_bar(cur_iter=15, total_iters=10, prefix='O ', suffix='')
        text = out.getvalue()
        assert '100.0%' in text
        assert '150.0%' not in text
        # Must terminate with a newline since the bar is now considered complete.
        assert text.endswith('\n')


class TestProgressBarFixedWidthPlain:
    """When the active console can't render a dim background bar (``no_color``
    or no ``color_system``), the bar must be a fixed-width string of ``━`` and
    spaces so the suffix doesn't shift between redraws."""

    def _no_color_console(self, out: StringIO) -> Console:
        return Console(file=out, force_terminal=True, no_color=True, highlight=False, emoji=False)

    def test_suffix_column_is_stable_across_updates(self):
        EspLog._reset()
        suffix_columns = []
        for cur in (0, 1, 2, 3, 4):
            out = StringIO()
            fake_console = self._no_color_console(out)
            with patch('sys.stdout', out):
                logger = EspLog(no_color=True)
                with patch.object(logger, '_get_interactive_console', return_value=fake_console):
                    logger.progress_bar(
                        cur_iter=cur,
                        total_iters=4,
                        prefix='Progress: ',
                        suffix=' (rest)',
                        bar_length=10,
                    )
            output = out.getvalue()
            # Strip ANSI control sequences (carriage return, erase-in-line)
            # so we can locate the suffix column on the visible line.
            visible = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', output).lstrip('\r\n').rstrip('\n')
            idx = visible.index('%')
            suffix_columns.append(idx)
        # All suffix columns must be identical: the bar width is fixed at 10
        # so ``%`` always lands in the same place.
        assert len(set(suffix_columns)) == 1, f'suffix shifts between redraws (columns: {suffix_columns})'

    def test_plain_bar_combinations(self):
        """The plain renderer must produce a fixed-width string for every input."""
        # (completed, total, width) -> expected bar segment.
        cases = [
            (0, 4, 10, '          '),
            (1, 4, 10, '━━╸       '),
            (2, 4, 10, '━━━━━     '),
            (3, 4, 10, '━━━━━━━╸  '),
            (4, 4, 10, '━━━━━━━━━━'),
            (0, 0, 10, '━━━━━━━━━━'),
            (5, 4, 10, '━━━━━━━━━━'),
            (1, 1, 5, '━━━━━'),
            (0, 1, 0, ''),
        ]
        for completed, total, width, expected in cases:
            assert EspLog._render_plain_bar(completed, total, width) == expected, (
                f'completed={completed} total={total} width={width}: '
                f'got {EspLog._render_plain_bar(completed, total, width)!r}, '
                f'expected {expected!r}'
            )

    def test_plain_bar_used_when_color_system_is_none(self):
        """Even with ``no_color=False``, a console without a ``color_system``
        triggers the plain renderer because Rich would otherwise still skip
        the trailing dim bar."""
        EspLog._reset()
        out = StringIO()
        # ``no_color=False`` but no ``color_system`` (plain non-TTY-ish console).
        fake_console = Console(
            file=out,
            no_color=False,
            color_system=None,
            highlight=False,
            emoji=False,
        )
        with patch('sys.stdout', out):
            logger = EspLog()
            with patch.object(logger, '_get_interactive_console', return_value=fake_console):
                logger.progress_bar(
                    cur_iter=2,
                    total_iters=4,
                    prefix='P: ',
                    suffix='',
                    bar_length=10,
                )
        output = out.getvalue()
        bar_segment = output.split('P: ', 1)[1].split('  50.0%', 1)[0]
        assert bar_segment == '━━━━━     ', repr(bar_segment)

    def test_plain_bar_zero_total_renders_full_bar(self):
        EspLog._reset()
        out = StringIO()
        fake_console = self._no_color_console(out)
        with patch('sys.stdout', out):
            logger = EspLog(no_color=True)
            with patch.object(logger, '_get_interactive_console', return_value=fake_console):
                logger.progress_bar(
                    cur_iter=0,
                    total_iters=0,
                    prefix='Z ',
                    suffix=' 0/0',
                    bar_length=10,
                )
        output = out.getvalue()
        bar_segment = output.split('Z ', 1)[1].split(' 100.0%', 1)[0]
        # ``percent:>5`` right-aligns ``100.0`` to exactly 5 chars, so the
        # suffix begins with a single space (no extra padding to strip).
        assert bar_segment == '━━━━━━━━━━', repr(bar_segment)


class TestProgressBarNoHighlight:
    """Regression: numbers in the bar must not be auto-recolored even when the
    active console was built with Rich's default ``highlight=True`` (e.g. if a
    consumer-side ``EspLogBase`` subclass overrides ``set_console`` and omits
    ``highlight=False``, as esp-idf-sbom's ``SbomLog`` did)."""

    def test_no_ansi_color_on_numbers_with_highlight_console(self):
        EspLog._reset()
        out = StringIO()
        # ``highlight=True`` is Rich's default and is what triggers the issue:
        # the regex highlighter colors digits (``100.0%``, ``0/0``, ``[5s]``)
        # blue. Our progress code must opt out at the print site.
        hi_console = Console(file=out, force_terminal=True, highlight=True, emoji=False)
        with patch('sys.stdout', out):
            logger = EspLog()
            with patch.object(logger, '_get_interactive_console', return_value=hi_console):
                logger.progress_bar(
                    cur_iter=0,
                    total_iters=0,
                    prefix='Checking ',
                    suffix=' 0/0 [5s]',
                )
        text = out.getvalue()
        # The numeric span ``100.0% 0/0 [5s]`` must appear as ONE contiguous
        # substring. Rich's regex highlighter, if it had run, would slice the
        # numbers out and wrap each with SGR escapes (``\x1b[...m100\x1b[0m``
        # etc.), breaking this exact substring. The bar itself may still emit
        # ``\x1b[38;...m`` for its own ``bar.finished`` colour on a real
        # ``color_system`` — that's the whole point of using ``ProgressBar``
        # and is unrelated to this regression.
        assert ' 100.0% 0/0 [5s] ' in text


class TestStage:
    # ``print`` follows the live ``sys.stdout`` (see ``_live_console``), so the
    # cached ``_stdout`` console only receives output when its ``.file`` *is*
    # the current ``sys.stdout``. Each test therefore patches ``sys.stdout`` /
    # ``sys.stderr`` to the same buffers the cached consoles write to.
    @staticmethod
    def _erase_stdout_lines(logger: EspLog) -> None:
        """StringIO does not interpret cursor controls — drop the last N stdout lines."""
        count = logger._stage_newline_count
        if logger._stage_progress_visible:
            count += 1
        if count <= 0:
            return
        f = logger._stdout.file
        lines = f.getvalue().splitlines(keepends=True)
        f.truncate(0)
        f.seek(0)
        if count < len(lines):
            f.write(''.join(lines[:-count]))

    def test_finish_without_start_is_noop(self):
        logger = EspLog()
        logger.stage(finish=True)

    def test_stage_collapses_stdout_on_tty(self):
        EspLog._reset()
        out = StringIO()
        err = StringIO()
        with patch.object(Console, 'is_terminal', True), patch('sys.stdout', out), patch('sys.stderr', err):
            logger = EspLog()
            logger._stdout = Console(file=out, force_terminal=True, highlight=False, emoji=False)
            logger._stderr = Console(file=err, force_terminal=True, highlight=False, emoji=False)
            logger.set_verbosity(Verbosity.NORMAL)
            with patch.object(logger, '_stage_erase_stdout', side_effect=lambda: self._erase_stdout_lines(logger)):
                logger.stage()
                logger.print('transient detail')
                logger.note('saved note')
                logger.warn('saved warning')
                logger.stage(finish=True)
        assert 'transient detail' not in out.getvalue()
        assert 'NOTE:' in out.getvalue()
        assert 'saved note' in out.getvalue()
        assert 'WARNING:' in err.getvalue()
        assert 'saved warning' in err.getvalue()

    def test_stage_verbose_keeps_all_output(self):
        EspLog._reset()
        out = StringIO()
        with patch.object(Console, 'is_terminal', True), patch('sys.stdout', out):
            logger = EspLog()
            logger._stdout = Console(file=out, force_terminal=True, highlight=False, emoji=False)
            logger.set_verbosity(Verbosity.VERBOSE)
            logger.stage()
            logger.print('still visible')
            logger.stage(finish=True)
        assert 'still visible' in out.getvalue()

    def test_stage_non_tty_keeps_stdout(self):
        EspLog._reset()
        out = StringIO()
        with patch('sys.stdout', out):
            logger = EspLog()
            logger._stdout = Console(file=out, force_terminal=False, highlight=False, emoji=False)
            logger.set_verbosity(Verbosity.NORMAL)
            logger.stage()
            logger.print('stays on disk')
            logger.stage(finish=True)
        assert 'stays on disk' in out.getvalue()

    def test_stage_buffers_note_until_finish_on_tty(self):
        EspLog._reset()
        out = StringIO()
        with patch.object(Console, 'is_terminal', True), patch('sys.stdout', out):
            logger = EspLog()
            logger._stdout = Console(file=out, force_terminal=True, highlight=False, emoji=False)
            logger.set_verbosity(Verbosity.NORMAL)
            logger.stage()
            logger.note('only after finish')
            assert 'only after finish' not in out.getvalue()
            logger.stage(finish=True)
        assert 'only after finish' in out.getvalue()

    def test_stage_buffers_warn_until_finish_on_tty(self):
        """Counterpart of `test_stage_buffers_note_until_finish_on_tty`
        for `warn`: the formatted ``WARNING:`` line must go to stderr
        (not stdout) and only appear after ``stage(finish=True)``.
        """
        EspLog._reset()
        out = StringIO()
        err = StringIO()
        with patch.object(Console, 'is_terminal', True), patch('sys.stdout', out), patch('sys.stderr', err):
            logger = EspLog()
            logger._stdout = Console(file=out, force_terminal=True, highlight=False, emoji=False)
            logger._stderr = Console(file=err, force_terminal=True, highlight=False, emoji=False)
            logger.set_verbosity(Verbosity.NORMAL)
            logger.stage()
            logger.warn('only after finish')
            assert 'only after finish' not in err.getvalue()
            assert 'only after finish' not in out.getvalue()
            logger.stage(finish=True)
        assert 'only after finish' in err.getvalue()
        assert 'WARNING:' in err.getvalue()
        assert 'only after finish' not in out.getvalue(), 'warn must not leak to stdout when re-emitted'

    def test_progress_bar_stage_bookkeeping(self):
        """In-progress stdout progress inside a stage must count toward erase."""
        EspLog._reset()
        out = StringIO()
        with patch.object(Console, 'is_terminal', True), patch('sys.stdout', out):
            logger = EspLog()
            logger._stdout = Console(file=out, force_terminal=True, highlight=False, emoji=False)
            logger.set_verbosity(Verbosity.NORMAL)
            logger.no_color = True
            logger.stage()
            logger.progress_bar(4, 4, prefix='Reading: ', bar_length=10)
            assert logger._stage_newline_count == 1
            assert not logger._stage_progress_visible
            logger.stage(finish=True)
            assert logger._stage_newline_count == 0

            logger.stage()
            logger.progress_bar(2, 4, prefix='Reading: ', bar_length=10)
            assert logger._stage_newline_count == 0
            assert logger._stage_progress_visible
            logger.stage(finish=True)
            assert not logger._stage_progress_visible

    def test_stage_finish_with_mid_render_bar_erases_in_place(self):
        """An unfinished progress bar at ``stage(finish=True)`` time must be
        wiped with ``\\r`` + ``ERASE_IN_LINE`` on the *current* row — never
        ``CURSOR_UP`` (which would walk above the stage and erase unrelated
        output while leaving the partial bar visible).

        Trigger: an exception inside ``with log.progress(...)`` skips
        ``_ensure_complete()``, so the last bar render had ``end=''`` and the
        cursor sits mid-line on the bar's row.
        """
        EspLog._reset()
        out = StringIO()
        with patch.object(Console, 'is_terminal', True), patch('sys.stdout', out):
            logger = EspLog()
            logger._stdout = Console(file=out, force_terminal=True, highlight=False, emoji=False)
            logger.set_verbosity(Verbosity.NORMAL)
            logger.no_color = True
            logger.stage()
            logger.print('status...')
            logger.progress_bar(1, 4, prefix='Reading: ', bar_length=10)
            logger.progress_bar(2, 4, prefix='Reading: ', bar_length=10)
            assert logger._stage_progress_visible
            assert logger._stage_newline_count == 1
            logger.stage(finish=True)

        raw = out.getvalue()
        # The cleanup sequence emitted after the last bar must be:
        # ``\r`` + ``ESC[2K`` (wipe the in-place bar row), then exactly one
        # ``ESC[1A`` + ``ESC[2K`` pair for the one tracked newline. A second
        # ``ESC[1A`` would mean we walked above the stage start.
        cleanup = raw.rsplit('50.0% ', 1)[1]
        cleanup_count = cleanup.count('\x1b[1A')
        assert cleanup_count == 1, (
            f'expected exactly 1 CURSOR_UP for the one tracked newline, got {cleanup_count} in {cleanup!r}'
        )
        assert '\r\x1b[2K' in cleanup, (
            f'expected the bar row to be wiped in place with CR + ERASE_IN_LINE, got {cleanup!r}'
        )

    def test_progress_bar_outside_stage_does_not_poison_next_stage(self):
        """A finalized progress bar emitted *before* ``stage()`` must not be
        counted toward the next stage's erase. Regression for a state leak
        where ``progress_bar`` incremented ``_stage_newline_count``
        unconditionally and ``stage()`` did not reset it on entry — causing
        ``stage(finish=True)`` to walk above the stage start and eat the bar
        row that was supposed to remain on screen.
        """
        EspLog._reset()
        out = StringIO()
        with patch.object(Console, 'is_terminal', True), patch('sys.stdout', out):
            logger = EspLog()
            logger._stdout = Console(file=out, force_terminal=True, highlight=False, emoji=False)
            logger.set_verbosity(Verbosity.NORMAL)
            logger.no_color = True
            logger.progress_bar(4, 4, prefix='Reading: ', bar_length=10)
            # Counter must stay at 0 because no stage was active when the bar finalized.
            assert logger._stage_newline_count == 0
            logger.stage()
            assert logger._stage_newline_count == 0
            logger.print('inside stage')
            assert logger._stage_newline_count == 1
            with patch.object(logger, '_stage_erase_stdout', side_effect=lambda: self._erase_stdout_lines(logger)):
                logger.stage(finish=True)
            assert 'inside stage' not in out.getvalue()
            assert 'Reading:' in out.getvalue(), 'bar row before the stage must survive stage finish'

    def test_stage_restart_without_finish_resets_state(self):
        """Calling ``stage()`` again without an intervening ``stage(finish=True)``
        must start the new stage from a clean slate — stale buffered notes or
        counter state from the unfinished stage must not bleed in.
        """
        EspLog._reset()
        out = StringIO()
        err = StringIO()
        with patch.object(Console, 'is_terminal', True), patch('sys.stdout', out), patch('sys.stderr', err):
            logger = EspLog()
            logger._stdout = Console(file=out, force_terminal=True, highlight=False, emoji=False)
            logger._stderr = Console(file=err, force_terminal=True, highlight=False, emoji=False)
            logger.set_verbosity(Verbosity.NORMAL)
            logger.stage()
            logger.print('first stage line')
            logger.note('stale note')
            assert logger._stage_newline_count == 1
            assert logger._stage_kept_lines
            logger.stage()
            assert logger._stage_newline_count == 0
            assert not logger._stage_kept_lines
            with patch.object(logger, '_stage_erase_stdout', side_effect=lambda: self._erase_stdout_lines(logger)):
                logger.stage(finish=True)
        assert 'stale note' not in out.getvalue()
