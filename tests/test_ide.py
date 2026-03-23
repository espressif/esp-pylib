# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Tests for esp_pylib.ws (IDE WebSocket) and esp_pylib.excepthook."""

import json
import sys
import threading
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

import esp_pylib.ws as ws
from esp_pylib.errors import FatalError


def _reset_ws_state() -> None:
    """Reset module-level state in esp_pylib.ws between tests.

    Tests reach into private attributes (``_ws_url``, ``_connection``, ``_URL_UNREAD``)
    on purpose: the module deliberately exposes no public reset hook so production
    code never has a way to wipe its singleton state. Restoring the unread sentinel
    (rather than ``None``) is required for the negative-cache fast path to be
    re-evaluated on the next call.
    """
    with ws._lock:
        if ws._connection is not None:
            try:
                ws._connection.close()
            except Exception:
                pass
            ws._connection = None
        ws._ws_url = ws._URL_UNREAD  # type: ignore[assignment]


@pytest.fixture(autouse=True)
def reset_ws_state():
    _reset_ws_state()
    yield
    _reset_ws_state()


@pytest.fixture
def restore_hooks():
    """Restore sys.excepthook and threading.excepthook after tests."""
    old_sys = sys.excepthook
    old_thread = getattr(threading, 'excepthook', None)
    yield
    sys.excepthook = old_sys
    # (py37-drop): the `hasattr` guard exists only for Python 3.7; drop it once 3.8+ is required.
    if hasattr(threading, 'excepthook') and old_thread is not None:
        threading.excepthook = old_thread


class TestWsUrl:
    def test_no_env_returns_none(self, monkeypatch):
        monkeypatch.delenv('ESPRESSIF_IDE_WS', raising=False)
        assert ws._get_ws_url() is None

    def test_env_returns_url(self, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://a')
        assert ws._get_ws_url() == 'ws://a'

    def test_negative_result_is_cached(self, monkeypatch):
        """First call reads the env var; subsequent calls must not re-read it.

        Pins the perf claim that ``is_enabled()`` is one-shot — without negative caching,
        every CLI warn/err with no IDE configured would re-enter os.environ.get.
        """
        monkeypatch.delenv('ESPRESSIF_IDE_WS', raising=False)
        assert ws._get_ws_url() is None
        # Setting the env var afterwards must NOT change the cached negative result.
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://late')
        assert ws._get_ws_url() is None


class TestSetWsUrl:
    def test_explicit_url_overrides_env(self, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://from-env')
        ws.set_ws_url('ws://explicit')
        assert ws._get_ws_url() == 'ws://explicit'

    def test_clear_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://from-env')
        ws.set_ws_url('ws://explicit')
        ws.set_ws_url(None)
        assert ws._get_ws_url() == 'ws://from-env'

    def test_set_closes_existing_connection(self):
        existing = MagicMock()
        ws._connection = existing
        ws.set_ws_url('ws://new')
        existing.close.assert_called_once()
        assert ws._connection is None


class TestEnsureConnected:
    def test_raises_fatal_when_url_not_configured(self, monkeypatch):
        monkeypatch.delenv('ESPRESSIF_IDE_WS', raising=False)
        with pytest.raises(FatalError, match='WebSocket not configured'):
            ws.ensure_connected()

    def test_succeeds_when_connect_works(self, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:12')
        fake_conn = MagicMock()
        fake_module = MagicMock()
        fake_module.connect.return_value = fake_conn
        with patch.dict(
            sys.modules,
            {'websockets': MagicMock(), 'websockets.sync': MagicMock(), 'websockets.sync.client': fake_module},
        ):
            ws.ensure_connected(retries=1)
        assert ws._connection is fake_conn

    def test_raises_after_exhausting_retries(self, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:13')
        fake_module = MagicMock()
        fake_module.connect.side_effect = OSError('refused')
        with patch.dict(
            sys.modules,
            {'websockets': MagicMock(), 'websockets.sync': MagicMock(), 'websockets.sync.client': fake_module},
        ):
            # Failure must report both the target URL and the underlying transport error so
            # operators can debug without enabling extra logging.
            with pytest.raises(FatalError, match=r'Cannot connect.*ws://localhost:13.*refused') as excinfo:
                ws.ensure_connected(retries=2, delay=0)
        assert fake_module.connect.call_count == 2
        # The original transport exception should be chained for full context.
        assert isinstance(excinfo.value.__cause__, OSError)

    def test_concurrent_first_connect_does_not_leak(self, monkeypatch):
        """Two threads calling ``_ensure_connection`` simultaneously may both reach ``connect()``
        (since the lock is released for I/O). The loser must close its own socket instead of
        leaking it, and both callers must end up with the same shared connection."""
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:99')

        barrier = threading.Barrier(2)
        created: list = []

        def synced_connect(_url):
            # Force both threads to be inside connect() at the same time.
            barrier.wait(timeout=2.0)
            conn = MagicMock(name=f'conn-{len(created)}')
            created.append(conn)
            return conn

        fake_module = MagicMock()
        fake_module.connect.side_effect = synced_connect

        results: list = []
        errors: list = []

        def runner():
            try:
                with patch.dict(
                    sys.modules,
                    {
                        'websockets': MagicMock(),
                        'websockets.sync': MagicMock(),
                        'websockets.sync.client': fake_module,
                    },
                ):
                    results.append(ws._ensure_connection(retries=1))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=runner) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2.0)

        assert not errors, f'concurrent connect raised: {errors}'
        assert len(results) == 2 and results[0] is results[1], (
            f'both callers should converge on the same connection, got {results!r}'
        )
        assert ws._connection is results[0]
        assert len(created) == 2, 'both threads were expected to race past the initial check'
        # Exactly one of the two created sockets should be the "loser" that got closed.
        closed = [c for c in created if c.close.called]
        assert len(closed) == 1, f'expected 1 orphaned connection to be closed, got {len(closed)}'
        # The closed one must not be the one stored as _connection.
        assert closed[0] is not ws._connection


class TestSendLogMessage:
    @patch('esp_pylib.ws._ensure_connection')
    def test_sends_json_payload(self, mock_ensure, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:9')
        mock_conn = MagicMock()
        mock_ensure.return_value = mock_conn

        ws.send_log_message('error', 'bad', 'fix it', '/src/x.py', 7)

        mock_ensure.assert_called()
        mock_conn.send.assert_called_once()
        payload = json.loads(mock_conn.send.call_args[0][0])
        assert payload == {
            'type': 'error',
            'file': '/src/x.py',
            'line': 7,
            'message': 'bad',
            'suggestion': 'fix it',
        }

    def test_no_env_no_connect(self, monkeypatch):
        monkeypatch.delenv('ESPRESSIF_IDE_WS', raising=False)
        with patch('esp_pylib.ws._ensure_connection') as mock_ensure:
            ws.send_log_message('warning', 'w', None, 'f.py', 1)
            mock_ensure.assert_not_called()

    @patch('esp_pylib.ws._ensure_connection', return_value=None)
    def test_connect_failure_swallowed(self, _mock_ensure, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:1')
        ws.send_log_message('error', 'e', None, 'f.py', 1)

    @patch('esp_pylib.ws._ensure_connection')
    def test_send_retries_once_after_failure(self, mock_ensure, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:2')
        first = MagicMock()
        first.send.side_effect = OSError('broken pipe')
        second = MagicMock()
        mock_ensure.side_effect = [first, second]

        ws.send_log_message('error', 'msg', None, 'f.py', 3)

        assert mock_ensure.call_count == 2
        second.send.assert_called_once()
        payload = json.loads(second.send.call_args[0][0])
        assert payload['message'] == 'msg'


class TestSendEvent:
    def test_raises_when_not_configured(self, monkeypatch):
        monkeypatch.delenv('ESPRESSIF_IDE_WS', raising=False)
        with pytest.raises(FatalError, match='WebSocket not configured'):
            ws.send_event('gdb_stub', port='/dev/ttyUSB0', prog='/a.elf')

    @patch('esp_pylib.ws._ensure_connection')
    def test_sends_event_payload(self, mock_ensure, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:3')
        mock_conn = MagicMock()
        mock_ensure.return_value = mock_conn

        ws.send_event('gdb_stub', port='/dev/ttyUSB0', prog='/b.elf')

        mock_conn.send.assert_called_once()
        payload = json.loads(mock_conn.send.call_args[0][0])
        assert payload['type'] == 'event'
        assert payload['event'] == 'gdb_stub'
        assert payload['port'] == '/dev/ttyUSB0'
        assert payload['prog'] == '/b.elf'

    @patch('esp_pylib.ws._ensure_connection')
    def test_kwargs_cannot_override_protocol_type(self, mock_ensure, monkeypatch):
        """Caller-supplied ``type`` kwarg must not silently rewrite the envelope.

        ``event`` is protected by Python's call semantics (it is a positional parameter),
        so only ``type`` can realistically collide via ``**kwargs``.
        """
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:3')
        mock_conn = MagicMock()
        mock_ensure.return_value = mock_conn

        ws.send_event('gdb_stub', type='hijack', port='/dev/ttyUSB0')

        payload = json.loads(mock_conn.send.call_args[0][0])
        assert payload['type'] == 'event'
        assert payload['event'] == 'gdb_stub'
        assert payload['port'] == '/dev/ttyUSB0'

    @patch('esp_pylib.ws._ensure_connection')
    def test_send_failure_raises_fatal_and_drops_connection(self, mock_ensure, monkeypatch):
        """A transport failure on send must surface as FatalError (not the underlying OSError)
        and clear the cached connection so subsequent calls reconnect."""
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:3')
        mock_conn = MagicMock()
        mock_conn.send.side_effect = OSError('broken pipe')
        mock_ensure.return_value = mock_conn
        ws._connection = mock_conn

        with pytest.raises(FatalError, match=r"Failed to send event 'gdb_stub'"):
            ws.send_event('gdb_stub', port='/dev/ttyUSB0')
        assert ws._connection is None

    def test_raises_distinct_message_when_websockets_missing(self, monkeypatch):
        """URL is set but ``websockets`` import fails: error must point at the missing extra,
        not claim the env var is unset."""
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:3')
        with patch.dict(sys.modules, {'websockets': None, 'websockets.sync': None, 'websockets.sync.client': None}):
            with pytest.raises(FatalError, match=r'websockets.*esp-pylib\[ide\]'):
                ws.send_event('gdb_stub')

    def test_raises_distinct_message_when_connect_fails(self, monkeypatch):
        """URL is set, ``websockets`` is importable, but connect() fails: error must say
        'Cannot connect', not 'WebSocket not configured'."""
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:3')
        fake_module = MagicMock()
        fake_module.connect.side_effect = OSError('refused')
        with patch.dict(
            sys.modules,
            {'websockets': MagicMock(), 'websockets.sync': MagicMock(), 'websockets.sync.client': fake_module},
        ):
            with pytest.raises(FatalError, match='Cannot connect'):
                ws.send_event('gdb_stub')


class TestWaitForEvent:
    def test_raises_when_not_configured(self, monkeypatch):
        monkeypatch.delenv('ESPRESSIF_IDE_WS', raising=False)
        with pytest.raises(FatalError, match='WebSocket not configured'):
            ws.wait_for_event('debug_finished')

    @patch('esp_pylib.ws._ensure_connection')
    def test_returns_matching_message(self, mock_ensure, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:4')
        mock_conn = MagicMock()
        mock_conn.recv.return_value = json.dumps({'type': 'event', 'event': 'debug_finished'})
        mock_ensure.return_value = mock_conn

        msg = ws.wait_for_event('debug_finished')

        assert msg['event'] == 'debug_finished'

    @patch('esp_pylib.ws._ensure_connection')
    def test_skips_non_matching_until_match(self, mock_ensure, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:5')
        mock_conn = MagicMock()
        mock_conn.recv.side_effect = [
            json.dumps({'type': 'event', 'event': 'noise'}),
            json.dumps({'type': 'event', 'event': 'debug_finished'}),
        ]
        mock_ensure.return_value = mock_conn

        msg = ws.wait_for_event('debug_finished')

        assert msg['event'] == 'debug_finished'
        assert mock_conn.recv.call_count == 2

    @patch('esp_pylib.ws._ensure_connection')
    def test_malformed_json_skipped_without_reconnect(self, mock_ensure, monkeypatch):
        """Bad JSON is a content error, not a transport error: keep waiting on the same connection."""
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:14')
        mock_conn = MagicMock()
        mock_conn.recv.side_effect = [
            'not-json',
            json.dumps({'event': 'debug_finished'}),
        ]
        mock_ensure.return_value = mock_conn

        msg = ws.wait_for_event('debug_finished')

        assert msg['event'] == 'debug_finished'
        # _ensure_connection should be called exactly once: malformed JSON must not trigger a reconnect.
        assert mock_ensure.call_count == 1

    def test_raises_distinct_message_when_websockets_missing(self, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:6')
        with patch.dict(sys.modules, {'websockets': None, 'websockets.sync': None, 'websockets.sync.client': None}):
            with pytest.raises(FatalError, match=r'websockets.*esp-pylib\[ide\]'):
                ws.wait_for_event('debug_finished')

    def test_raises_distinct_message_when_connect_fails(self, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:6')
        fake_module = MagicMock()
        fake_module.connect.side_effect = OSError('refused')
        with patch.dict(
            sys.modules,
            {'websockets': MagicMock(), 'websockets.sync': MagicMock(), 'websockets.sync.client': fake_module},
        ):
            with pytest.raises(FatalError, match='Cannot connect'):
                ws.wait_for_event('debug_finished')

    @patch('esp_pylib.ws._ensure_connection')
    def test_raises_after_retries_on_persistent_failure(self, mock_ensure, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:6')
        mock_conn = MagicMock()
        mock_conn.recv.side_effect = OSError('eof')
        mock_ensure.return_value = mock_conn

        with pytest.raises(FatalError, match='Did not receive expected event'):
            ws.wait_for_event('debug_finished', retries=2)

    @patch('esp_pylib.ws._ensure_connection')
    def test_lost_connection_message_distinguished_from_no_event(self, mock_ensure, monkeypatch):
        """Persistent transport failure (reconnect returns None) must surface a different
        message from the case where the transport is healthy but the expected event never arrives.

        Strict mode is used for the first call (succeeds, returns mock_conn); the retry path
        uses non-strict mode (returns None on connect failure).
        """
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:15')
        mock_conn = MagicMock()
        mock_conn.recv.side_effect = OSError('eof')
        # First call (strict=True) succeeds; subsequent reconnects (non-strict) return None.
        mock_ensure.side_effect = [mock_conn, None]

        with pytest.raises(FatalError, match='Lost WebSocket connection'):
            ws.wait_for_event('debug_finished', retries=3)


class TestClose:
    def test_close_clears_connection(self, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:7')
        mock_conn = MagicMock()
        ws._connection = mock_conn

        ws.close()

        mock_conn.close.assert_called_once()
        assert ws._connection is None


class TestExcepthook:
    @pytest.mark.usefixtures('restore_hooks')
    def test_sys_excepthook_reports_innermost_location(self, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:8')
        sent = []

        def capture(typ, message, suggestion, file, line):
            sent.append((typ, message, suggestion, file, line))

        with patch('esp_pylib.excepthook.send_log_message', side_effect=capture):
            from esp_pylib.excepthook import install_exception_reporting

            install_exception_reporting()

            def inner():
                raise ValueError('boom')  # raise_line

            def outer():
                inner()

            raise_line = inner.__code__.co_firstlineno + 1

            try:
                outer()
            except ValueError:
                _typ, val, tb = sys.exc_info()
                assert _typ is ValueError
                sys.excepthook(_typ, val, tb)

        assert len(sent) == 1
        _typ, message, suggestion, file, line = sent[0]
        assert _typ == 'exception'
        assert 'boom' in message
        assert suggestion is not None and 'ValueError' in suggestion
        # Must report the *innermost* frame (the actual `raise` site),
        # not the outermost frame where the exception was caught.
        assert file == __file__
        assert line == raise_line

    @pytest.mark.usefixtures('restore_hooks')
    def test_skips_system_exit_and_keyboard_interrupt(self, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:8')
        mock_send = MagicMock()
        with patch('esp_pylib.excepthook.send_log_message', mock_send):
            from esp_pylib.excepthook import install_exception_reporting

            install_exception_reporting()
            sys.excepthook(SystemExit, SystemExit(0), None)
            sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)

        mock_send.assert_not_called()

    @pytest.mark.usefixtures('restore_hooks')
    def test_install_is_idempotent(self, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:8')
        with patch('esp_pylib.excepthook.send_log_message'):
            from esp_pylib import excepthook as eh

            eh.install_exception_reporting()
            first = sys.excepthook
            prev_after_first = eh._previous_sys_excepthook
            eh.install_exception_reporting()
            assert sys.excepthook is first
            assert eh._previous_sys_excepthook is prev_after_first

    # (py37-drop): remove this skipif once Python >=3.8 is required (see README cleanup checklist).
    @pytest.mark.skipif(not hasattr(threading, 'excepthook'), reason='threading.excepthook requires Python 3.8+')
    @pytest.mark.filterwarnings('ignore::pytest.PytestUnhandledThreadExceptionWarning')
    @pytest.mark.usefixtures('restore_hooks')
    def test_thread_excepthook_sends_exception(self, monkeypatch):
        monkeypatch.setenv('ESPRESSIF_IDE_WS', 'ws://localhost:8')
        sent = []

        def capture(typ, message, suggestion, file, line):
            sent.append((typ, message, file, line))

        with patch('esp_pylib.excepthook.send_log_message', side_effect=capture):
            from esp_pylib.excepthook import install_exception_reporting

            install_exception_reporting()

            def work():
                raise RuntimeError('thread err')

            t = threading.Thread(target=work)
            t.start()
            t.join(timeout=5.0)
            assert not t.is_alive()

        assert len(sent) == 1
        assert sent[0][0] == 'exception'
        assert 'thread err' in sent[0][1]
