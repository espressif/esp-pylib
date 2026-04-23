# esp-pylib

Python library for logging, utils and constants for Espressif Systems' Python projects.

## Installation

```bash
pip install esp-pylib
```

## Modules

- **`esp_pylib.constants`** — Single place for cross-tool constants (e.g. Espressif USB VID/PID, default ROM baud rate, serial port name patterns, and Unix `termios` modem-control bits where available).
- **`esp_pylib.errors`** — A small exception hierarchy (`FatalError` and common subclasses such as `NoSerialPortFoundError`, `ConfigError`) for consistent error handling across tools.
- **`esp_pylib.logger`** — Shared logging for Espressif Python tools: verbosity levels (`Verbosity`), the default Rich-based singleton (`log` / `EspLog`), and `EspLogBase` so you can plug in a custom implementation via `EspLog.set_logger()`.

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
