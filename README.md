# esp-pylib

Python library for logging, utils and constants for Espressif Systems' Python projects.

## Installation

```bash
pip install esp-pylib
```

Optional **IDE WebSocket** support (structured messages to VS Code / other IDEs via `websockets`):

```bash
pip install esp-pylib[ide]
```

> [!NOTE]
> **IDE features require Python ≥ 3.8** (because `websockets ≥ 12` does). On Python 3.7, `pip install esp-pylib[ide]` still succeeds but pulls in no `websockets` — `esp_pylib.ws` becomes a no-op: `send_log_message()` returns silently, and `send_event` / `wait_for_event` / `ensure_connected` raise `FatalError`.

## Modules

- **`esp_pylib.constants`** — Single place for cross-tool constants (e.g. Espressif USB VID/PID, default ROM baud rate, serial port name patterns, and Unix `termios` modem-control bits where available).
- **`esp_pylib.errors`** — A small exception hierarchy (`FatalError` and common subclasses such as `NoSerialPortFoundError`, `ConfigError`) for consistent error handling across tools.
- **`esp_pylib.logger`** — Shared logging for Espressif Python tools: verbosity levels (`Verbosity`), the default Rich-based singleton (`log` / `EspLog`), and `EspLogBase` so you can plug in a custom implementation via `EspLog.set_logger()`.
- **`esp_pylib.ws`** — WebSocket client for IDE integration: sends structured JSON when an IDE sets the environment variable below. Requires `pip install esp-pylib[ide]` (pulls in `websockets`; effectively a no-op on Python 3.7 — see Installation note above). The connection is created lazily on first use; if no URL is set, log helpers no-op.
- **`esp_pylib.excepthook`** — Hooks (`sys.excepthook` and `threading.excepthook`, Python 3.8+) to report uncaught exceptions to the IDE over the same WebSocket channel, then chain to the previous hooks so normal stderr behavior is unchanged. Use together with `esp-pylib[ide]`.

### IDE integration (WebSocket)

Espressif IDEs can launch tools with a WebSocket URL so errors, warnings, and exceptions carry **file**, **line**, and optional **suggestion** text (e.g. full tracebacks) for click-to-navigate in the UI. CLI usage is unchanged when no URL is set: there is no connection and no overhead beyond reading the environment once.

#### Environment variables

| Variable | Purpose |
| -------- | ------- |
| `ESPRESSIF_IDE_WS` | WebSocket URL (e.g. `ws://127.0.0.1:12345`). Set by the IDE, not by end users. |

**`esp_pylib.ws` API**

- `send_log_message(typ, message, suggestion, file, line)` — Fire-and-forget. `typ` is one of `warning`, `error`, or `exception`. Failures are ignored so a broken IDE connection cannot crash the tool.
- `send_event(event, **kwargs)` — Debug coordination (e.g. GDB stub / coredump). Sends `{"type": "event", "event": "<name>", ...}`. Raises `FatalError` if the URL is unset, `websockets` is missing, the connection cannot be established, or the send fails (each case carries a distinct message). The reserved `type` envelope key always wins over an identically-named `**kwargs` entry.
- `wait_for_event(event, retries=3)` — Blocks until a JSON message with matching `event` is received (e.g. `debug_finished` from the IDE). Raises `FatalError` if the URL is unset, `websockets` is missing, the connection cannot be established, or no matching message arrives within `retries` reconnects.
- `set_ws_url(url)` — Programmatic override for tools that expose their own flag (e.g. esp-idf-monitor's `--ws`). Pass `None` to clear the override and fall back to `ESPRESSIF_IDE_WS` on next use. Closes any existing connection.
- `close()` — Closes the shared connection (call on clean tool exit if you opened one).

**Log message JSON shape** (tool → IDE):

```json
{
  "type": "warning | error | exception",
  "file": "/absolute/path/to/source.py",
  "line": 42,
  "message": "Human-readable description",
  "suggestion": "Optional fix text or full traceback, or null"
}
```

#### Uncaught exceptions

Call once at startup (after configuring logging if needed):

```python
from esp_pylib.excepthook import install_exception_reporting

install_exception_reporting()
```

This reports uncaught exceptions to the IDE when `ESPRESSIF_IDE_WS` is set (or `set_ws_url()` has been called). `SystemExit` and `KeyboardInterrupt` are not sent. The previous `sys.excepthook` / `threading.excepthook` handlers are always invoked afterward.

### Custom logger

Subclass `EspLogBase`, implement its methods, then register your instance so all code using the shared logger goes through your implementation:

```python
import sys

from esp_pylib.logger import EspLog, EspLogBase, Verbosity


class MyLogger(EspLogBase):
    def __init__(self):
        self._verbosity = Verbosity.NORMAL

    def print(self, *args, **kwargs):
        print(*args, **kwargs)

    def err(self, message, suggestion=None):
        print(f"ERROR: {message}", file=sys.stderr)

    def warn(self, message, suggestion=None):
        print(f"WARNING: {message}", file=sys.stderr)

    def note(self, message):
        print(f"Note: {message}")

    def debug(self, message):
        if self._verbosity == Verbosity.VERBOSE:
            print(message)

    def set_verbosity(self, mode):
        if isinstance(mode, str):
            mode = Verbosity[mode.upper()]
        self._verbosity = mode


EspLog.set_logger(MyLogger())
```

## How to Contribute

First, set up the development environment:

```bash
git clone https://github.com/espressif/esp-pylib.git
cd esp-pylib
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## How to Release (For Maintainers Only)

```bash
python -m venv venv
source venv/bin/activate
pip install commitizen czespressif
git fetch
git checkout -b update/release_v1.1.0
git reset --hard origin/master
cz bump
git push -u
git push --tags
```

Create a pull request and edit the automatically created draft [release notes](https://github.com/espressif/esp-pylib/releases).

## License

This document and the attached source code are released under Apache License Version 2. See the accompanying [LICENSE](./LICENSE) file for a copy.
