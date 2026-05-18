# Implementation Plan: `esp-pylib` — Shared Python Library for Espressif Tools

---

## Table of Contents

- [Implementation Plan: `esp-pylib` — Shared Python Library for Espressif Tools](#implementation-plan-esp-pylib--shared-python-library-for-espressif-tools)
  - [Table of Contents](#table-of-contents)
  - [1. Purpose \& Scope](#1-purpose--scope)
    - [1.1 Problem](#11-problem)
    - [1.2 Goal](#12-goal)
    - [1.3 What This Library Does NOT Own](#13-what-this-library-does-not-own)
      - [Chip Definitions, IDs, and Target Lists](#chip-definitions-ids-and-target-lists)
      - [Raw ANSI Escape Codes (partial replacement)](#raw-ansi-escape-codes-partial-replacement)
      - [Tool-specific Environment Variables](#tool-specific-environment-variables)
    - [1.4 Consumer Repos](#14-consumer-repos)
    - [1.5 Python Version Decision](#15-python-version-decision)
  - [2. Package Structure](#2-package-structure)
  - [3. Dependency Graph](#3-dependency-graph)
    - [3.1 Current Dependencies](#31-current-dependencies)
    - [3.2 Target Dependencies](#32-target-dependencies)
    - [3.3 pyproject.toml for esp-pylib](#33-pyprojecttoml-for-esp-pylib)
  - [4. Design Details Per Module](#4-design-details-per-module)
    - [4.1 constants.py — Shared Constants](#41-constantspy--shared-constants)
      - [What's duplicated](#whats-duplicated)
      - [Implementation](#implementation)
    - [4.2 log.py — Unified Logger (Rich-Based)](#42-logpy--unified-logger-rich-based)
      - [What's being replaced (full inventory)](#whats-being-replaced-full-inventory)
      - [Logging requirements alignment (ESPTOOL.md / IDFPY.md)](#logging-requirements-alignment-esptoolmd--idfpymd)
      - [Implementation](#implementation-1)
      - [Custom logger classes (EspLogBase ABC)](#custom-logger-classes-esplogbase-abc)
      - [Advanced: esptool-specific extensions (stage, progress\_bar)](#advanced-esptool-specific-extensions-stage-progress_bar)
    - [4.3 errors.py — Common Error Classes](#43-errorspy--common-error-classes)
      - [What's duplicated](#whats-duplicated-1)
      - [Implementation](#implementation-2)
    - [4.4 serial/ports.py — Port Discovery \& Filtering](#44-serialportspy--port-discovery--filtering)
      - [What's duplicated](#whats-duplicated-2)
      - [Implementation](#implementation-3)
    - [4.5 serial/reset.py — Reset Handling](#45-serialresetpy--reset-handling)
      - [What's duplicated](#whats-duplicated-3)
      - [Implementation](#implementation-4)
    - [4.6 config.py — Config File Loader](#46-configpy--config-file-loader)
      - [What's duplicated](#whats-duplicated-4)
      - [Implementation](#implementation-5)
    - [4.7 rom.py — ROM ELF Path Resolution](#47-rompy--rom-elf-path-resolution)
      - [What's duplicated](#whats-duplicated-5)
      - [Implementation](#implementation-6)
    - [4.8 cli/ — Reusable CLI Pieces](#48-cli--reusable-cli-pieces)
      - [CLI framework unification: all tools migrate to rich-click](#cli-framework-unification-all-tools-migrate-to-rich-click)
      - [What's duplicated](#whats-duplicated-6)
      - [Implementation](#implementation-7)
    - [4.9 ide/ — WebSocket IDE Integration](#49-ide--websocket-ide-integration)
      - [Design rationale](#design-rationale)
      - [Protocol specification](#protocol-specification)
      - [Implementation](#implementation-8)
      - [Integration with EspLog](#integration-with-esplog)
      - [How consumers use IDE integration](#how-consumers-use-ide-integration)
  - [5. Phased Implementation](#5-phased-implementation)
    - [Phase 1: Scaffolding \& Constants (Week 1)](#phase-1-scaffolding--constants-week-1)
      - [Tasks](#tasks)
    - [Phase 2: Logging, Config, ROM ELF (Week 2)](#phase-2-logging-config-rom-elf-week-2)
      - [Tasks](#tasks-1)
    - [Phase 3: Serial Logic (Week 3)](#phase-3-serial-logic-week-3)
      - [Tasks](#tasks-2)
    - [Phase 4: Documentation \& Stabilization (Week 4)](#phase-4-documentation--stabilization-week-4)
      - [Tasks](#tasks-3)
    - [Phase 5: Migration of Consumer Repos (Weeks 5–8)](#phase-5-migration-of-consumer-repos-weeks-58)
      - [5.1 `esptool` (Week 5)](#51-esptool-week-5)
      - [5.2 `esp-idf-monitor` (Week 6)](#52-esp-idf-monitor-week-6)
      - [5.3 `esp-coredump` (Week 7)](#53-esp-coredump-week-7)
      - [5.4 `esp-idf-panic-decoder` (Week 7)](#54-esp-idf-panic-decoder-week-7)
      - [5.5 `esp-idf-size` (Week 8)](#55-esp-idf-size-week-8)
      - [5.6 `esp-idf-sbom` (Week 8)](#56-esp-idf-sbom-week-8)
      - [5.7 `clang-tidy-runner` (Week 8)](#57-clang-tidy-runner-week-8)
      - [5.8 `esp-idf` Python tools (Week 8)](#58-esp-idf-python-tools-week-8)
  - [6. Risk Management](#6-risk-management)
  - [7. Success Criteria](#7-success-criteria)
  - [8. Breaking Change Audit (Consumer Compatibility)](#8-breaking-change-audit-consumer-compatibility)
    - [8.1 esptool — Public API surface](#81-esptool--public-api-surface)
    - [8.2 esp-idf-monitor — Constants and WebSocket](#82-esp-idf-monitor--constants-and-websocket)
    - [8.3 esp-coredump](#83-esp-coredump)
    - [8.4 Config loader (ToolConfig) — Cross-cutting](#84-config-loader-toolconfig--cross-cutting)
    - [8.5 Summary of required plan/implementation updates](#85-summary-of-required-planimplementation-updates)
  - [9. Per-Tool Audit](#9-per-tool-audit)
    - [9.1 `esptool` / `espefuse` / `espsecure`](#91-esptool--espefuse--espsecure)
      - [Exceptions](#exceptions)
      - [Print statements](#print-statements)
      - [Logging module](#logging-module)
      - [sys.exit](#sysexit)
      - [CLI arguments](#cli-arguments)
      - [CLI framework](#cli-framework)
    - [9.2 `esp-idf-monitor`](#92-esp-idf-monitor)
      - [Exceptions](#exceptions-1)
      - [Print statements](#print-statements-1)
      - [Logging module](#logging-module-1)
      - [sys.exit](#sysexit-1)
      - [CLI framework](#cli-framework-1)
    - [9.3 `esp-coredump`](#93-esp-coredump)
      - [Exceptions](#exceptions-2)
      - [Print statements](#print-statements-2)
      - [Logging module (16+ calls — all migrate)](#logging-module-16-calls--all-migrate)
      - [sys.exit](#sysexit-2)
      - [CLI framework](#cli-framework-2)
    - [9.4 `esp-idf-panic-decoder`](#94-esp-idf-panic-decoder)
      - [Exceptions](#exceptions-3)
      - [Print statements](#print-statements-3)
      - [Logging module (migrate)](#logging-module-migrate)
      - [sys.exit](#sysexit-3)
      - [CLI framework](#cli-framework-3)
    - [9.5 `esp-idf-size`](#95-esp-idf-size)
      - [Exceptions](#exceptions-4)
      - [Print statements](#print-statements-4)
      - [Logging module](#logging-module-2)
      - [sys.exit](#sysexit-4)
      - [CLI framework](#cli-framework-4)
    - [9.6 `esp-idf-sbom`](#96-esp-idf-sbom)
      - [Exceptions](#exceptions-5)
      - [Print statements](#print-statements-5)
      - [Logging module](#logging-module-3)
      - [sys.exit](#sysexit-5)
      - [CLI framework](#cli-framework-5)
    - [9.7 Summary Table](#97-summary-table)

---

## 1. Purpose & Scope

### 1.1 Problem

Espressif maintains 8+ Python tool repositories that duplicate significant amounts of code:

| Repository | Description | Key deps |
|---|---|---|
| [`espressif/esptool`](https://github.com/espressif/esptool) | Serial flashing/provisioning | `pyserial`, `rich_click`, `click` |
| [`espressif/esp-idf-monitor`](https://github.com/espressif/esp-idf-monitor) | Serial monitor | `pyserial` |
| [`espressif/esp-coredump`](https://github.com/espressif/esp-coredump) | Core dump analysis | `esptool` (for `detect_chip`) |
| [`espressif/esp-idf-panic-decoder`](https://github.com/espressif/esp-idf-panic-decoder) | Panic output decoding | `pyelftools`, `pyparsing` |
| [`espressif/esp-idf-size`](https://github.com/espressif/esp-idf-size) | Firmware size analysis | `rich` |
| [`espressif/esp-idf-sbom`](https://github.com/espressif/esp-idf-sbom) | SBOM generation | `rich` |
| [`espressif/clang-tidy-runner`](https://github.com/espressif/clang-tidy-runner) | Static analysis runner | — |
| [`espressif/esp-idf`](https://github.com/espressif/esp-idf) | IDF framework (Python in `tools/`) | various |

Each tool independently implements serial port discovery, color output, reset sequences, config file loading, and error handling. There is no single source of truth for USB identifiers, port filtering logic, or reset pin control.

### 1.2 Goal

Create a new package **`esp-pylib`** (PyPI name) that:

1. Provides **shared constants** (USB VID/PID, default baud, port filter/sort patterns in `constants`; DTR/RTS pin levels, reset delays, and Unix `TIOCM*` ioctl symbols in `serial_reset` next to the primitives that use them)
2. Provides **unified output/logging** using `rich` — replacing all raw ANSI escape code usage across every repo
3. Provides **reusable serial port logic** (discovery, filtering, sorting, reset sequences)
4. Provides **shared config file loading**, **common error classes**, and **ROM ELF resolution**
5. Provides **IDE integration** via optional WebSocket channel for structured diagnostics

### 1.3 What This Library Does NOT Own

#### Chip Definitions, IDs, and Target Lists

All chip-related definitions (chip IDs, architecture groupings, `SUPPORTED_TARGETS` lists, reset timing configs) stay in their respective tools. The common lib does **not** provide a chip registry.

**Why not?** Adding a new chip would require updating and releasing `esp-pylib` before any tool could add support for it. Each tool adds chip support at its own pace — `esptool` might support a new chip immediately while `esp-coredump` needs months for SOC header and architecture handler work. A centralized chip registry creates a release-ordering bottleneck that outweighs the deduplication benefit.

Each tool continues to maintain its own chip definitions:
- `esptool`: `CHIP_DEFS` dict mapping chip name → ROM class, per-class `IMAGE_CHIP_ID`
- `esp-coredump`: `SUPPORTED_TARGETS = XTENSA_TARGETS + RISCV_TARGETS`, `EspCoreDumpVersion` chip ID class
- `esp-idf-monitor`: `chip_specific_config.py` with per-chip reset timings
- `esp-idf-size`: chip-specific memory map YAML files

#### Raw ANSI Escape Codes (partial replacement)

For **diagnostic messages** (tool warnings, errors, status notes written to stderr), `rich` replaces all raw ANSI code. The `rich` library handles terminal color support detection, `NO_COLOR`, Windows ANSI compatibility, and non-TTY pipe detection.

**Exception: `esp-idf-monitor`'s serial data coloring.** The monitor has a byte-level auto-coloring pipeline (`print_colored()` in `serial_handler.py`) that wraps raw serial bytes with pre-encoded ANSI byte constants (`ANSI_RED_B`, `ANSI_GREEN_B`, etc.) before writing to `sys.stdout.buffer`. This pipeline:
- Operates entirely on `bytes` (never decodes to `str`) for performance and binary safety
- Must handle arbitrary byte data from the serial port, including invalid UTF-8
- Processes thousands of lines per second at high baud rates
- On Windows, feeds through a custom `ANSIColorConverter` that converts ANSI byte sequences to Win32 `SetConsoleTextAttribute()` calls

`rich` cannot replace this because it requires `str` input, runs markup parsing/rendering per call, and has no mechanism for coloring raw byte streams. The monitor's `ANSI_*_B` byte constants and `print_colored()` stay local.

**What gets replaced in the monitor:** `note_print()`, `warning_print()`, `error_print()`, `yellow_print()`, `red_print()`, `green_print()`, `normal_print()` — all of which write **strings** to `sys.stderr` for diagnostic messages. These are replaced by `EspLog` methods.

#### Tool-specific Environment Variables

Most environment variables are package-specific and stay in their respective tools:

| Env var | Owner | Reason |
|---|---|---|
| `ESPTOOL_PORT` | esptool | Only esptool uses this default |
| `ESPTOOL_BAUD` | esptool | esptool-specific baud override |
| `ESPTOOL_CHIP` | esptool | esptool-specific chip override |
| `ESPTOOL_CONNECT_ATTEMPTS` | esptool | esptool-specific retry setting |
| `ESPTOOL_OPEN_PORT_ATTEMPTS` | esptool + monitor | esptool-originated, monitor also reads it |
| `ESPTOOL_CFGFILE` | esptool | esptool config file path |
| `ESP_IDF_MONITOR_CFGFILE` | monitor | monitor config file path |
| `ESPPORT` | monitor | monitor-specific legacy port variable |
| `MONITORBAUD` / `IDF_MONITOR_BAUD` | monitor | monitor-specific baud override |
| `ESP_IDF_MONITOR_WS` | monitor | monitor-specific WebSocket URL (being unified into `ESPRESSIF_IDE_WS`; kept as fallback for backward compat) |

The common lib only handles truly **cross-cutting** environment variables:
- `IDF_PATH` — used by both `esp-idf-monitor` and `esp-coredump` for ROM ELF resolution
- `ESP_ROM_ELF_DIR` — same: used by both for ROM ELF resolution
- `NO_COLOR` — de-facto standard respected by the unified logger
- `ESPRESSIF_IDE_WS` — WebSocket URL for IDE integration (set by IDE extensions, not by users)

### 1.4 Consumer Repos

| Package | Current `requires-python` | Current serial deps | Current output mechanism | Current CLI framework |
|---|---|---|---|---|
| `esptool` | `>=3.10` | `pyserial>=3.3` | `rich_click<2`, `click<9`, custom `EsptoolLogger` with raw ANSI | `rich_click` ✓ (`esp_rfc2217_server`: `argparse`) |
| `esp-idf-monitor` | `>=3.7` | `pyserial>=3.3` | Raw ANSI via `output_helpers.py` | `argparse` → convert |
| `esp-coredump` | `>=3.7` | via `esptool` | Raw `print()` + Python `logging` | `argparse` → convert |
| `esp-idf-panic-decoder` | `>=3.7` | — | Raw ANSI via `output_helpers.py` + Python `logging` | `argparse` → convert |
| `esp-idf-size` | `>=3.7` | — | `rich` directly (local `log.py`) | `argparse` → convert |
| `esp-idf-sbom` | `>=3.7` | — | `rich` directly (local `log.py`) | `argparse` → convert (`idf_ext.py`: `click` ✓) |
| `clang-tidy-runner` | (setup.py) | — | Raw `print()` | `argparse` → convert |

### 1.5 Python Version Decision

**Minimum: `>=3.7`**

Rationale:
- Multiple consumer repos (`esp-idf-monitor`, `esp-coredump`, `esp-idf-panic-decoder`, `esp-idf-size`, `esp-idf-sbom`) currently require `>=3.7`. Adding `esp-pylib` as a dependency must not force them to bump their Python version.
- EOL status and type hint syntax are **not** reasons to bump. A version bump is only justified by **missing functionality** — e.g., if a required stdlib feature (like a specific `inspect`, `asyncio`, or `typing` API) is unavailable on older versions.
- All core dependencies (`rich>=12.0`, `rich-click>=1.7`, `click>=8.0`) support Python 3.7.
- The `websockets` sync client (`websockets.sync.client`) requires Python >= 3.8 — but since `websockets` is an optional dependency (`esp-pylib[ide]`), this does not constrain the base package. Users on Python 3.7 can use everything except IDE WebSocket integration.
- For type annotations, all modules use `from __future__ import annotations` to enable modern syntax (`str | None`, `dict[str, ...]`) without requiring a runtime Python version bump.
- **Decision: `>=3.7`.** If a future feature requires a newer Python version for functional reasons (not style), bump with a minor release and document it in the changelog.

---

## 2. Package Structure

```
esp-pylib/
├── pyproject.toml
├── README.md
├── LICENSE                        # Apache-2.0
├── CHANGELOG.md
│
├── esp_pylib/
│   ├── __init__.py                # __version__, convenience imports, install exception hooks
│   │
│   ├── constants.py               # Hardware (VID/PID, baud) + serial port discovery (exclude list, device-name patterns)
│   │
│   ├── log.py                     # Unified rich-based logger: err/warn/note/print + WebSocket
│   ├── errors.py                  # FatalError, NoSerialPortFoundError, ConfigError
│   ├── config.py                  # INI config file loader (per-tool sections)
│   ├── rom.py                     # ROM ELF path resolution, roms.json lookup
│   │
│   ├── ide/
│   │   ├── __init__.py            # install_exception_reporting() entry point
│   │   ├── ws.py                  # WebSocket client (ESPRESSIF_IDE_WS env var)
│   │   └── excepthook.py          # sys.excepthook + threading.excepthook for IDE reporting
│   │
│   ├── serial/
│   │   ├── __init__.py
│   │   ├── ports.py               # get_port_list(), detect_port(), parse_port_filters()
│   │   └── reset.py               # DTR/RTS control, custom sequence parser, reset strategies
│   │
│   └── cli/
│       ├── __init__.py
│       ├── options.py             # Reusable Click option groups / argparse helpers
│       └── types.py               # SerialPortType (Click ParamType with completion)
│
└── tests/
    ├── test_constants.py
    ├── test_ports.py
    ├── test_reset.py
    ├── test_config.py
    ├── test_log.py
    ├── test_rom.py
    └── test_ide.py                # WebSocket + excepthook tests
```

---

## 3. Dependency Graph

### 3.1 Current Dependencies

```
esp-idf
├── esptool                              (pyserial, rich_click, click)
├── esp-idf-monitor                      (pyserial)
│   ├── esp-coredump                     (esptool, construct, pygdbmi)
│   └── esp-idf-panic-decoder            (pyelftools, pyparsing)
├── esp-idf-size                         (rich)
├── esp-idf-sbom                         (rich, pyparsing)
└── clang-tidy-runner                    (none)
```

### 3.2 Target Dependencies

`esp-pylib` is an **additional** shared dependency — it does **not** replace existing inter-tool dependencies. For example, `esp-coredump` continues to depend on `esptool` for chip detection and serial communication; it additionally depends on `esp-pylib` for shared constants, logging, and ROM ELF resolution.

```
esp-pylib  ← NEW (deps: rich, rich-click, click; optional: pyserial, websockets)
       ↑
       ├── esptool                       [serial]         (still has: pyserial, rich_click, click)
       ├── esp-idf-monitor               [serial]         (still has: pyserial)
       │   ├── esp-coredump                               (still has: esptool, construct, pygdbmi)
       │   └── esp-idf-panic-decoder                      (still has: pyelftools, pyparsing)
       ├── esp-idf-size                                   (still has: rich transitively)
       ├── esp-idf-sbom                                   (still has: rich transitively, pyparsing)
       └── clang-tidy-runner
```

**Key rule:** `esp-pylib` must **never** depend on any consumer tool. It sits at the absolute bottom of the dependency tree. Existing inter-tool dependencies (e.g., `esp-coredump` → `esptool`) are unchanged.

### 3.3 pyproject.toml for esp-pylib

```toml
[build-system]
requires = ["setuptools>=64", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "esp-pylib"
dynamic = ["version"]
description = "Python library for logging, utils and constants for Espressif Systems' Python projects"
readme = "README.md"
license = { text = "Apache-2.0" }
requires-python = ">=3.7"
authors = [
  { name = "Espressif Systems" }
]
keywords = ["python", "espressif"]
classifiers = [
  "Development Status :: 1 - Planning",
  "Intended Audience :: Developers",
  "Natural Language :: English",
  "Environment :: Console",
  "Topic :: Software Development :: Embedded Systems",
  "Programming Language :: Python :: 3.7",
  "Programming Language :: Python :: 3.8",
  "Programming Language :: Python :: 3.9",
  "Programming Language :: Python :: 3.10",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Programming Language :: Python :: 3.14",
  "License :: OSI Approved :: Apache Software License",
  "Operating System :: POSIX",
  "Operating System :: Microsoft :: Windows",
  "Operating System :: MacOS :: MacOS X",
]
dependencies = [
    "rich>=12.0",
    "rich-click>=1.7,<2",
    "click>=8.0,<9",
]

[project.optional-dependencies]
serial = ["pyserial>=3.3"]
ide = ["websockets>=12.0"]
dev = [
    "pre-commit",
    "pytest",
    "coverage[toml]",
    "czespressif",
    "websockets>=12.0",
]

[project.urls]
Homepage = "https://github.com/espressif/esp-pylib"
Repository = "https://github.com/espressif/esp-pylib"
Source = "https://github.com/espressif/esp-pylib/"
Tracker = "https://github.com/espressif/esp-pylib/issues/"
Changelog = "https://github.com/espressif/esp-pylib/blob/master/CHANGELOG.md"

[tool.setuptools.packages.find]
where = ["."]
include = ["esp_pylib*"]

[tool.setuptools.dynamic]
version = { attr = "esp_pylib.__version__.__version__" }

[tool.ruff]
line-length = 120
target-version = "py37"

[tool.ruff.format]
quote-style = "single"
indent-style = "space"
docstring-code-format = true

[tool.ruff.lint]
select = ["F", "E", "W", "I", "UP"]
fixable = ["ALL"]
unfixable = []

[tool.ruff.lint.isort]
known-first-party = ["esp_pylib"]
force-single-line = true

[tool.mypy]
python_version = "3.7"
disallow_untyped_defs = false
warn_return_any = true
warn_no_return = true
ignore_missing_imports = true
disallow_incomplete_defs = false

[tool.commitizen]
name = "czespressif"
version = "0.1.3"
update_changelog_on_bump = true
tag_format = "v$version"
changelog_start_rev = "v0.1"
changelog_merge_prerelease = true
annotated_tag = true
bump_message = "change(bump): Update version to $new_version"
version_files = ["esp_pylib/__version__.py"]
```

---

## 4. Design Details Per Module

### 4.1 constants.py — Shared Constants

**Split from reset primitives:** Values that are only used by DTR/RTS / `ioctl` reset code (`PIN_LOW` / `PIN_HIGH`, `DEFAULT_RESET_DELAY`, `MINIMAL_EN_LOW_DELAY`, Unix `TIOCM*`) live in **`esp_pylib.serial_reset`** next to `set_dtr` / `set_dtr_rts` (see Section 4.5). **`esp_pylib.constants`** holds hardware identifiers and **serial port discovery** tuples shared with `serial_ports.py` — one small module, no separate `hardware.py`.

#### What's duplicated

**Hardware (USB VID/PID, default baud):**

| Constant | Value | Where it currently lives |
|---|---|---|
| `ESPRESSIF_VID` | `0x303A` | Inline in `esptool/cli_util.py` inside `_get_port_list()` function |
| `USB_JTAG_SERIAL_PID` | `0x1001` | `esptool/loader.py` L305 (`ESPLoader.USB_JTAG_SERIAL_PID`), `esp_idf_monitor/base/constants.py` L71, `espefuse/efuse/emulate_efuse_controller_base.py` L33 |
| `ESP_ROM_BAUD` | `115200` | `esptool/loader.py` L302 (`ESPLoader.ESP_ROM_BAUD`), used as default in `esp_coredump/cli_ext.py` L38, `esp_idf_monitor/argument_parser.py` |

**Serial port discovery (sort/filter — stays in `constants.py`):**

| Constant | Where it currently lives |
|---|---|
| macOS port blacklist `('Bluetooth-Incoming-Port', 'wlan-debug', 'cu.debug-console')` | `esp_idf_monitor/base/constants.py` L76 as `FILTERED_PORTS`; inline in `esptool/cli_util.py` L546-549 inside an `if sys.platform == "darwin"` check |
| Linux/macOS device name patterns for sorting | `esptool/cli_util.py` (`ttyUSB`, `ttyACM`, `usbserial`, `usbmodem` used in sort key logic) |

**Reset / modem control (lives in `serial_reset.py`, not `constants.py`):**

| Constant | Where it currently lives |
|---|---|
| `LOW = True`, `HIGH = False` (DTR/RTS pin levels) | `esp_idf_monitor/base/constants.py` L74-75; concept used in both `esptool/reset.py` and `esp_idf_monitor/base/reset.py` — consumers import `PIN_LOW` / `PIN_HIGH` from `esp_pylib.serial_reset` |
| `DEFAULT_RESET_DELAY = 0.05` | `esptool/reset.py` L27 |
| `MINIMAL_EN_LOW_DELAY = 0.005` | `esp_idf_monitor/base/constants.py` L62 |
| `TIOCMSET`, `TIOCMGET`, `TIOCM_DTR`, `TIOCM_RTS` | `esptool/reset.py` L18-25 (via `termios`); identical pattern in `esp_idf_monitor/base/reset.py` |

Note: `DEFAULT_RESET_DELAY` and `MINIMAL_EN_LOW_DELAY` might not be needed as they are tool specific.

#### Implementation (`esp_pylib/constants.py`)

```python
# esp_pylib/constants.py
"""
Cross-tool constants: USB identity, ROM baud, and serial port discovery patterns.

DTR/RTS levels, reset delays, and Unix TIOCM ioctl symbols are in esp_pylib.serial_reset.
"""

# --- Hardware identifiers ---
ESPRESSIF_VID = 0x303A
USB_JTAG_SERIAL_PID = 0x1001
ESP_ROM_BAUD = 115200

# --- Serial port discovery (used by serial_ports) ---
MACOS_PORT_EXCLUDE_LIST = ('Bluetooth-Incoming-Port', 'wlan-debug', 'cu.debug-console')
LINUX_DEVICE_PATTERNS = ('ttyUSB', 'ttyACM')
MACOS_DEVICE_PATTERNS = ('usbserial', 'usbmodem')
```

### 4.2 log.py — Unified Logger (Rich-Based)

#### What's being replaced (full inventory)

| Repo | File | What it does | Lines |
|---|---|---|---|
| `esptool` | `esptool/logger.py` | `EsptoolLogger` singleton: `note()`, `warning()`, `error()`, `print()`, stage collapsing. Manually constructs ANSI codes (`\033[1;31m`) with `NO_COLOR` env check and Windows `colorama` fallback. | ~160 lines |
| `esp-idf-monitor` | `esp_idf_monitor/base/output_helpers.py` | `red_print()`, `yellow_print()`, `green_print()`, `color_print()`, `note_print()`, `warning_print()`, `error_print()` — all write raw ANSI to `sys.stderr`. **Note:** `ANSI_*_B` byte constants and `AUTO_COLOR_REGEX` stay local for serial data coloring (see Section 1.3). | ~40 lines replaced, ~20 lines stay |
| `esp-idf-panic-decoder` | `esp_idf_panic_decoder/output_helpers.py` | `ANSI_RED`, `ANSI_NORMAL` constants + `red_print()` — raw ANSI to stderr. | 15 lines |
| `esp-coredump` | `esp_coredump/__main__.py` | Python `logging` module with custom level mapping (debug 0-4 → CRITICAL/ERROR/WARNING/INFO/DEBUG). | ~15 lines |
| `esp-coredump` | `esp_coredump/coredump.py` L508-521 | `_handle_coredump_loader_error()` — uses raw `print(..., file=sys.stderr)` with hand-drawn box characters (`┌`, `│`, `└`). | ~12 lines |
| `esp-idf-size` | throughout | Direct `rich.console.Console` usage. | scattered |
| `esp-idf-sbom` | throughout | Direct `rich.console.Console` usage. | scattered |

All of the above get replaced by a single `rich`-based logger.

#### Logging requirements alignment (ESPTOOL.md / IDFPY.md)

The logger design is aligned with the requirements captured in **ESPTOOL.md** (esptool) and **IDFPY.md** (idf.py). Summary:

| Requirement | In esp-pylib | Notes |
|-------------|--------------|--------|
| **API** | `print`, `note`, `warning`/`warn`, `error`/`err`, `die`, `debug` | Aliases `warning`/`error` for compatibility. |
| **Streams** | Errors/warnings → stderr; normal/notes → **stdout** | Note goes to stdout with prefix `Note: `. |
| **Format** | `ERROR: {msg}`, `WARNING: {msg}`, `Note: {msg}`; prefixes added by library | Callers pass body only. No duplicate prefix if message already starts with `ERROR:`/`Error:`/`WARNING:`. |
| **print(..., file=...)** | Supported; stream resolved at call time | Enables dump-to-file and testability. |
| **Verbosity** | `set_verbosity("auto"\|"verbose"\|"silent"\|"compact")` | Maps to quiet/verbose/smart behavior. |
| **Smart features** | TTY, TERM, NO_COLOR; Rich handles; optional Windows colorama | Overridable via verbosity. |
| **Pluggable logger (ABC)** | `EspLogBase` ABC defines the interface; `set_logger(instance)` validates and replaces singleton | Any consumer can provide a custom logger class implementing `EspLogBase`. Also used for tests. |
| **No user backtraces** | Application responsibility | Library does not print tracebacks to user. |
| **Progress bar** | **Not in esp-pylib** | esptool implements callback-style `progress_bar` in its **EsptoolLogger** subclass. |
| **Stage (collapsible)** | **Not in esp-pylib** | esptool implements `stage()` / collapsible region in its **EsptoolLogger** subclass. |
| **idf.py-specific** | **Out of scope** | Async tee (subprocess to file + stream), ANSI strip for log files/non-TTY, and progression-line in-place update are implemented by idf.py (or a layer on top of esp-pylib), not by the shared library. |

#### Implementation

```python
# esp_pylib/log.py
"""
Unified logging for all Espressif tools.
Uses rich.console.Console — no raw ANSI codes needed.
Rich automatically handles NO_COLOR, non-TTY, and Windows support.

Architecture:
  EspLogBase (ABC) — defines the interface all loggers must implement.
  EspLog     — default Rich-based implementation (singleton).
  set_logger()  — replaces the singleton with any EspLogBase subclass.

Any consumer tool (esptool, esp-coredump, ...) or integrator can provide
a custom logger class by subclassing EspLogBase and calling set_logger().
"""
import os
import sys
from abc import ABC, abstractmethod
from typing import Optional

from rich.console import Console


class EspLogBase(ABC):
    """
    Abstract base class defining the logging interface for Espressif tools.

    All loggers used with esp-pylib must implement this interface.
    Consumer tools and third-party integrators can subclass this
    to redirect output (e.g. to a GUI, file, or network sink).
    """

    @abstractmethod
    def print(self, *args, **kwargs) -> None:
        """Plain output to stdout (or file= if provided)."""
        ...

    @abstractmethod
    def err(self, msg: str, suggestion: Optional[str] = None) -> None:
        """Error message to stderr."""
        ...

    @abstractmethod
    def warn(self, msg: str, suggestion: Optional[str] = None) -> None:
        """Warning message to stderr."""
        ...

    @abstractmethod
    def note(self, msg: str) -> None:
        """Informational note to stdout."""
        ...

    @abstractmethod
    def debug(self, msg: str) -> None:
        """Debug message (shown only in verbose mode)."""
        ...

    @abstractmethod
    def die(self, msg: str, exit_code: int = 1, suggestion: Optional[str] = None) -> None:
        """Print error and exit."""
        ...

    @abstractmethod
    def set_verbosity(self, mode: str) -> None:
        """Set verbosity: 'auto' | 'verbose' | 'silent' | 'compact'."""
        ...


class EspLog(EspLogBase):
    """
    Default Rich-based singleton logger for Espressif tools.

    - err()/error() and warn()/warning() → stderr, with ERROR:/WARNING: prefix (no duplicate if already present).
    - note() → stdout with "Note: " prefix (distinct style, e.g. bold cyan).
    - print() → stdout, or stream from file= if given; supports end=, sep=, flush=; stream resolved at call time.
    - Respects NO_COLOR env var and set_verbosity() (auto/verbose/silent/compact).
    - set_logger(instance) replaces the singleton with any EspLogBase implementation (for custom integrations and tests).
    """

    _instance: Optional['EspLogBase'] = None

    def __new__(cls) -> 'EspLog':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls.no_color = os.getenv('NO_COLOR', '').strip().lower() in ('1', 'true', 'yes')
            cls._instance._stderr = Console(stderr=True, no_color=cls.no_color)
            cls._instance._stdout = Console(no_color=cls.no_color)
            cls._instance._verbosity = 'auto'
        return cls._instance

    @classmethod
    def _reset(cls) -> None:
        """Reset singleton to default EspLog (for testing)."""
        cls._instance = None

    @classmethod
    def set_logger(cls, instance: 'EspLogBase') -> None:
        """
        Replace the global logger singleton with a custom implementation.

        The instance must be an EspLogBase subclass. This allows consumer
        tools and integrators to redirect all logging output — e.g. to a
        GUI widget, log file, network sink, or test capture.

        Call _reset() to restore the default Rich-based logger.
        """
        if not isinstance(instance, EspLogBase):
            raise TypeError(
                f"Logger must implement the EspLogBase interface, "
                f"got {type(instance).__name__!r}"
            )
        cls._instance = instance

    def set_quiet(self, quiet: bool) -> None:
        """Suppress non-error output."""
        self._quiet = quiet

    def set_verbose(self, verbose: bool) -> None:
        """Enable debug-level output."""
        self._verbose = verbose

    def set_verbosity(self, mode: str) -> None:
        """Set verbosity: 'auto' | 'verbose' | 'silent' | 'compact'. Affects smart features and what is shown."""
        self._verbosity = mode
        self._quiet = (mode == 'silent')
        self._verbose = (mode == 'verbose')
        # compact: force smart on; verbose: smart off; auto: from TTY/TERM/NO_COLOR

    def print(self, *args, **kwargs) -> None:
        """Plain output. Uses file= if provided (resolved at call time); else stdout. Suppressed when silent/quiet."""
        if self._quiet and kwargs.get('file') is None:
            return
        file = kwargs.pop('file', None)
        if file is not None:
            Console(file=file, no_color=self.no_color).print(*args, **kwargs)
        else:
            self._stdout.print(*args, **kwargs)

    def err(self, msg: str, suggestion: Optional[str] = None) -> None:
        """Error message (red, bold) to stderr."""
        self._stderr.print(f'[bold red]ERROR:[/bold red] {msg}')
        # ... IDE send_log_message('error', msg, suggestion, file, line) ...

    def warn(self, msg: str, suggestion: Optional[str] = None) -> None:
        """Warning message (yellow) to stderr."""
        self._stderr.print(f'[yellow]WARNING:[/yellow] {msg}')
        # ... IDE send_log_message('warning', msg, suggestion, file, line) ...

    def note(self, msg: str) -> None:
        """Informational note (cyan) to stdout with 'Note: ' prefix"""
        self._stdout.print(f'[cyan]Note:[/cyan] {msg}')

    def debug(self, msg: str) -> None:
        """Debug message. Only shown in verbose mode."""
        if self._verbose:
            self._stderr.print(f'[dim]{msg}[/dim]')

    def die(self, msg: str, exit_code: int = 1, suggestion: Optional[str] = None) -> None:
        """Print error and exit."""
        self.err(msg, suggestion)
        sys.exit(exit_code)

    # Backward compatibility API - consider moving to per project level

    def warning(self, msg: str, *args, **kwargs) -> None:
        """Alias for warn() — esptool/idf.py compatibility."""
        self.warn(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        """Alias for err() — esptool/idf.py compatibility."""
        self.err(msg, *args, **kwargs)


# Module-level convenience instance
log = EspLog()
```

#### Custom logger classes (EspLogBase ABC)

The `EspLogBase` ABC defines the contract that all loggers must satisfy. This is elevated from esptool's existing `TemplateLogger` pattern so that **all** consumer tools benefit from pluggable logging, not just esptool.

**Use cases for custom logger classes:**

- **IDE integration** — redirect output to a GUI panel or WebSocket sink instead of the terminal.
- **Testing** — capture output for assertions without monkey-patching.
- **Embedding** — when a tool is used as a library (e.g. esptool called from idf.py or a CI framework), the host can provide its own logger to unify output formatting.
- **Tool-specific extensions** — e.g. esptool adds `stage()` and `progress_bar()` (see below).

Any custom logger is installed via `EspLog.set_logger(instance)`, which validates that the instance implements `EspLogBase` (raises `TypeError` otherwise). Call `EspLog._reset()` to restore the default Rich-based logger.

```python
# Example: custom logger for a GUI application
from esp_pylib.log import EspLogBase, EspLog

class GuiLogger(EspLogBase):
    """Routes all log output to a GUI text widget."""

    def __init__(self, text_widget):
        self._widget = text_widget

    def print(self, *args, **kwargs) -> None:
        self._widget.append(" ".join(str(a) for a in args))

    def err(self, msg, suggestion=None) -> None:
        self._widget.append(f"ERROR: {msg}", color="red")

    def warn(self, msg, suggestion=None) -> None:
        self._widget.append(f"WARNING: {msg}", color="yellow")

    def note(self, msg) -> None:
        self._widget.append(f"Note: {msg}", color="cyan")

    def debug(self, msg) -> None:
        pass  # suppress in GUI

    def die(self, msg, exit_code=1, suggestion=None) -> None:
        self.err(msg, suggestion)
        raise SystemExit(exit_code)

    def set_verbosity(self, mode) -> None:
        pass  # GUI handles its own verbosity

# Install:
EspLog.set_logger(GuiLogger(my_widget))
```

#### Advanced: esptool-specific extensions (stage, progress_bar)

**Progress bar** and **collapsible stage** are required by esptool but are **not** part of the shared esp-pylib API. esptool implements them in its own **EsptoolLogger** subclass so that:

- **progress_bar(cur_iter, total_iters, prefix=..., suffix=..., bar_length=30)** — callback-style, in-place on stdout, with silent-mode suppression and non-TTY fallback — lives in esptool.
- **stage(finish: bool = False)** — collapsible region with replay of notes (stdout) and warnings (stderr) at finish — lives in esptool.

This keeps esp-pylib minimal while satisfying the requirement that “the library” support these behaviors for esptool: the shared `EspLogBase` ABC provides the stream/format contract; esptool’s subclass adds the UI behavior.

```python
# esptool/logger.py — AFTER migration
from esp_pylib.log import EspLog, EspLogBase

class EsptoolLogger(EspLog):
    """Extended logger with stage collapsing and progress bar for flash progress.

    Inherits from EspLog (the default Rich-based implementation) and adds
    esptool-specific UI features. Since EspLog implements EspLogBase,
    EsptoolLogger is also a valid EspLogBase and can be replaced via
    set_logger() with any other EspLogBase implementation.
    """
    _stage_active: bool = False
    _newline_count: int = 0

    def stage(self, finish: bool = False) -> None: ...
    def progress_bar(self, cur_iter: int, total_iters: int, prefix: str = "", suffix: str = "", bar_length: int = 30) -> None: ...
    def begin_stage(self, title: str) -> None: ...
    def end_stage(self) -> None: ...
```

### 4.3 errors.py — Common Error Classes

#### What's duplicated

| Repo | File | Class | Base |
|---|---|---|---|
| `esptool` | `esptool/util.py` L160 | `FatalError` | `RuntimeError` |
| `esptool` | `esptool/util.py` | `FatalError.WithResult` | classmethod returning `FatalError` subclass |
| `esp-coredump` | `esp_coredump/tools.py` L9 | `FatalError` | `Exception` |
| `esp-coredump` | `esp_coredump/corefile/__init__.py` L23-29 | `ESPCoreDumpError` → `ESPCoreDumpLoaderError` | `RuntimeError` |

#### Implementation

```python
# esp_pylib/errors.py
"""
Common error hierarchy for all Espressif tools.
Tools may subclass these for tool-specific errors.
"""


class FatalError(RuntimeError):
    """
    Base fatal error for all Espressif tools.
    Indicates an unrecoverable error that should terminate the tool.
    """
    pass


class NoSerialPortFoundError(FatalError):
    """Raised when no matching serial port is found."""
    pass


class ConfigError(FatalError):
    """Raised when configuration file is invalid or missing."""
    pass
```

Tools keep their specific subclasses locally:
- `esptool`: `FatalError.WithResult` (adds ROM error code context)
- `esp-coredump`: `ESPCoreDumpLoaderError(FatalError)` (adds `extra_output` field)

### 4.4 serial/ports.py — Port Discovery & Filtering

#### What's duplicated

The most extensive duplication. Two complete implementations exist:

**In esptool** (`esptool/cli_util.py` L487-600):
- `_get_port_list()` — calls `serial.tools.list_ports.comports()`, filters by VID/PID/name/serial
- Platform-specific sorting: Espressif VID (`0x303A`) ports first, then `ttyUSB` → `ttyACM` → others on Linux; `usbserial` → `usbmodem` → others on macOS
- macOS blacklist: inline check `if sys.platform == "darwin" and port.device.endswith(("Bluetooth-Incoming-Port", ...))`
- `parse_port_filters()` — parses `key=value` strings for vid/pid/name/serial
- `get_port_list()` — public API combining the above
- `SerialPortType(click.ParamType)` — with shell completion

**In esp-idf-monitor** (`esp_idf_monitor/base/constants.py` + `idf_monitor.py`):
- `FILTERED_PORTS` tuple for macOS blacklist
- `USB_JTAG_SERIAL_PID` for identifying JTAG-serial ports
- Port detection logic scattered through the monitor

**In esp-coredump** (`esp_coredump/cli_ext.py`):
- `parser.add_argument('--port', default=os.environ.get('ESPTOOL_PORT'))` — delegates to esptool for actual port detection

#### Implementation

```python
# esp_pylib/serial/ports.py
"""
Serial port discovery, filtering, and sorting.
Single implementation replacing duplicated code in esptool and esp-idf-monitor.
"""
import sys
from typing import Optional

from esp_pylib.constants import (
    ESPRESSIF_VID,
    MACOS_PORT_EXCLUDE_LIST,
    LINUX_DEVICE_PATTERNS,
    MACOS_DEVICE_PATTERNS,
)
from esp_pylib.errors import NoSerialPortFoundError

try:
    from serial.tools.list_ports import comports
    from serial.tools.list_ports_common import ListPortInfo
except ImportError:
    raise ImportError(
        'pyserial is required for serial port functionality. '
        'Install with: pip install esp-pylib[serial]'
    )


def _sort_key(port: ListPortInfo) -> tuple:
    """
    Sort key that prioritizes Espressif devices, then common device patterns.
    Espressif VID (0x303A) ports always come first.
    """
    is_espressif = 1 if port.vid == ESPRESSIF_VID else 0
    if sys.platform.startswith('linux'):
        pattern_priority = next(
            (i for i, p in enumerate(LINUX_DEVICE_PATTERNS) if p in port.device),
            len(LINUX_DEVICE_PATTERNS),
        )
    elif sys.platform == 'darwin':
        pattern_priority = next(
            (i for i, p in enumerate(MACOS_DEVICE_PATTERNS) if p in port.device),
            len(MACOS_DEVICE_PATTERNS),
        )
    else:
        pattern_priority = 0
    return (-is_espressif, pattern_priority, port.device)


def _is_blacklisted(port: ListPortInfo) -> bool:
    """Filter out macOS virtual ports that are not real serial devices."""
    if sys.platform == 'darwin':
        return port.device.endswith(MACOS_PORT_EXCLUDE_LIST)
    return False


def get_port_list(
    vids: Optional[list[int]] = None,
    pids: Optional[list[int]] = None,
    names: Optional[list[str]] = None,
    serials: Optional[list[str]] = None,
) -> list[ListPortInfo]:
    """
    Enumerate serial ports, filter, and sort by priority.

    :param vids: Filter by USB Vendor IDs
    :param pids: Filter by USB Product IDs
    :param names: Filter by device name substrings
    :param serials: Filter by serial number substrings
    :return: Sorted list of matching ports (best candidates first)
    """
    ports = []
    for port in comports():
        if _is_blacklisted(port):
            continue
        if vids and (port.vid not in vids):
            continue
        if pids and (port.pid not in pids):
            continue
        if names and not any(n.lower() in port.device.lower() for n in names):
            continue
        if serials and not any(
            s.lower() in (port.serial_number or '').lower() for s in serials
        ):
            continue
        ports.append(port)
    return sorted(ports, key=_sort_key)


def get_port_names(**filters) -> list[str]:
    """Convenience: return just device paths, sorted."""
    return [p.device for p in get_port_list(**filters)]


def detect_port(**filters) -> str:
    """
    Auto-detect the best single serial port.
    Raises NoSerialPortFoundError if no matching port is found.
    """
    ports = get_port_list(**filters)
    if not ports:
        raise NoSerialPortFoundError(
            'No serial ports found. Check the connection and drivers.'
        )
    return ports[0].device


def parse_port_filters(values: tuple[str, ...]) -> dict[str, list]:
    """
    Parse port filter arguments in 'key=value' format.
    Supported keys: vid, pid, name, serial.

    Example: ('vid=0x303A', 'pid=0x1001') → {'vids': [0x303A], 'pids': [0x1001]}
    """
    result: dict[str, list] = {'vids': [], 'pids': [], 'names': [], 'serials': []}
    key_map = {'vid': 'vids', 'pid': 'pids', 'name': 'names', 'serial': 'serials'}
    for value in values:
        if '=' not in value:
            raise ValueError(f'Invalid port filter format: {value!r}. Expected key=value.')
        key, val = value.split('=', 1)
        key = key.strip().lower()
        if key not in key_map:
            raise ValueError(f'Unknown port filter key: {key!r}. Valid keys: {list(key_map.keys())}')
        if key in ('vid', 'pid'):
            result[key_map[key]].append(int(val.strip(), 0))
        else:
            result[key_map[key]].append(val.strip())
    return result
```

### 4.5 serial/reset.py — Reset Handling

#### What's duplicated

**In esptool** (`esptool/reset.py`, ~250 lines):
- `_setDTR()`, `_setRTS()` — with Windows `usbser.sys` workaround
- `_setDTRandRTS()` — Unix-only simultaneous set via `fcntl.ioctl` with TIOCM constants
- Full class hierarchy: `ResetStrategy` (base), `ClassicReset`, `UnixTightReset`, `USBJTAGSerialReset`, `HardReset`, `CustomReset`
- `DEFAULT_RESET_DELAY = 0.05`

**In esp-idf-monitor** (`esp_idf_monitor/base/reset.py`, ~80 lines):
- `_setDTR()`, `_setRTS()` — **identical** Windows workaround code
- `_setDTRandRTS()` — **identical** Unix ioctl code
- Single `Reset` class with `hard()` and `to_bootloader()` methods that use chip-specific timing from `chip_specific_config.py`

The DTR/RTS primitive functions are copied verbatim between the two repos.

#### Implementation

```python
# esp_pylib/serial_reset.py  (actual layout; plan diagram may still show esp_pylib/serial/reset.py)
"""
DTR/RTS pin control and reset sequence handling.
Single implementation replacing duplicated code in esptool/reset.py
and esp_idf_monitor/base/reset.py.

Module-level exports (defined at top of the real file, omitted here): PIN_LOW,
PIN_HIGH, DEFAULT_RESET_DELAY, MINIMAL_EN_LOW_DELAY, and Unix TIOCM*
constants (or None on Windows) — co-located with set_dtr / set_dtr_rts, not
imported from esp_pylib.constants.
"""
import sys
import time
from typing import Optional

# PIN_LOW, PIN_HIGH, DEFAULT_RESET_DELAY, TIOCMGET, TIOCMSET, TIOCM_DTR, TIOCM_RTS
# are defined on this same module (see repo).


def _setDTR(port, state: bool) -> None:
    """Set DTR pin state with Windows usbser.sys workaround."""
    port.dtr = state
    # usbser.sys on Windows toggles RTS when DTR is set
    if sys.platform == 'win32':
        port.rts = port.rts  # restore RTS to its previous state


def _setRTS(port, state: bool) -> None:
    """Set RTS pin state with Windows usbser.sys workaround."""
    port.rts = state
    if sys.platform == 'win32':
        port.dtr = port.dtr  # restore DTR


def _setDTRandRTS(port, dtr: bool, rts: bool) -> None:
    """
    Set DTR and RTS simultaneously on Unix using ioctl.
    On Windows, falls back to sequential setting.
    """
    if sys.platform == 'win32':
        _setDTR(port, dtr)
        _setRTS(port, rts)
        return

    # Unix: use TIOCM ioctl for atomic DTR+RTS (TIOCM* are module-level in serial_reset)
    import fcntl
    import struct

    fd = port.fileno()
    status = struct.unpack('I', fcntl.ioctl(fd, TIOCMGET, b'\x00\x00\x00\x00'))[0]
    if dtr:
        status |= TIOCM_DTR
    else:
        status &= ~TIOCM_DTR
    if rts:
        status |= TIOCM_RTS
    else:
        status &= ~TIOCM_RTS
    fcntl.ioctl(fd, TIOCMSET, struct.pack('I', status))


def parse_custom_reset_sequence(seq_str: str) -> list[dict]:
    """
    Parse a custom reset sequence string in 'D0|R1|W0.1' format.
    D = DTR, R = RTS, W = wait (seconds). 0 = low, 1 = high.
    """
    steps = []
    for token in seq_str.split('|'):
        token = token.strip()
        if not token:
            continue
        cmd = token[0].upper()
        val = token[1:]
        if cmd == 'D':
            steps.append({'type': 'dtr', 'state': bool(int(val))})
        elif cmd == 'R':
            steps.append({'type': 'rts', 'state': bool(int(val))})
        elif cmd == 'W':
            steps.append({'type': 'wait', 'duration': float(val)})
        else:
            raise ValueError(f'Unknown reset sequence command: {token!r}')
    return steps


def execute_custom_reset(port, seq_str: str) -> None:
    """Parse and execute a custom reset sequence."""
    for step in parse_custom_reset_sequence(seq_str):
        if step['type'] == 'dtr':
            _setDTR(port, step['state'])
        elif step['type'] == 'rts':
            _setRTS(port, step['state'])
        elif step['type'] == 'wait':
            time.sleep(step['duration'])
```

#### Named reset sequences (sequence-level dedup)

Beyond the primitives, the actual DTR/RTS *pulse trains* (classic, Unix-tight,
USB-JTAG, hard) are also duplicated between esptool and esp-idf-monitor with
subtle drift. Lifting the pulse trains into named functions — while leaving
strategy selection, retry, and config plumbing in each tool — gives a single
source of truth for the chip-revision-sensitive ordering and lets both tools
delete their `format_dict` + `exec()` paths in favor of `execute_custom_reset`.

Implementation lives in `esp_pylib/serial_reset.py`:

- `classic_bootloader_reset(port, enter_boot_delay=0.1, reset_delay=0.05)` —
  sequential DTR/RTS bootloader entry; replaces esptool's `ClassicReset.reset()`
  and esp-idf-monitor's traditional `Reset.to_bootloader()` path.
- `unix_tight_bootloader_reset(port, enter_boot_delay=0.1, reset_delay=0.05)` —
  atomic-DTR/RTS variant via `set_dtr_rts`; replaces esptool's
  `UnixTightReset.reset()`. Raises `NotImplementedError` on Windows so callers
  fall back to `classic_bootloader_reset`.
- `usb_jtag_bootloader_reset(port, settle_delay=0.1)` — USB-Serial-JTAG pulse
  train; replaces esptool's `USBJTAGSerialReset.reset()` and esp-idf-monitor's
  USB-JTAG branch in `to_bootloader()`.
- `hard_reset(port, hold_delay=0.1, post_release_delay=0.0)` — EN pulse;
  replaces esptool's `HardReset.reset()` (use `hold_delay=0.2,
  post_release_delay=0.2` for `uses_usb=True`) and esp-idf-monitor's `hard()`
  (pass `chip_config['reset']` as `hold_delay`).

Tools keep their wrappers — esptool's `ClassicReset(port, reset_delay).reset()`
becomes a one-liner around `classic_bootloader_reset(port, 0.1, reset_delay)`;
esp-idf-monitor's `to_bootloader()` keeps its PID-based selection and config
loading but the per-branch body becomes a call to one of the new functions.

### 4.6 config.py — Config File Loader

#### What's duplicated

**In esptool** (`esptool/config.py`, ~80 lines):
- `_find_config_file()` — searches cwd → `~/.config/esptool/` → `~` for `esptool.cfg`
- `_validate_config_file()` — checks file has `[esptool]` section
- `load_config_file()` — public API combining the above
- Uses `ESPTOOL_CFGFILE` env var for override

**In esp-idf-monitor** (`esp_idf_monitor/config.py`, ~60 lines):
- Nearly identical structure: searches for `idf_monitor.cfg`
- Uses `ESP_IDF_MONITOR_CFGFILE` env var for override
- Same search order: cwd → `~/.config/...` → `~`

#### Implementation

```python
# esp_pylib/config.py
"""
Config file loader for Espressif tools.
Each tool passes its own section name, filenames, and env var.
"""
import configparser
import os
from pathlib import Path
from typing import Optional

from esp_pylib.errors import ConfigError


class ToolConfig:
    """
    Load and parse INI-style config files for a specific tool.

    Each tool creates its own instance:
        config = ToolConfig(
            section_name='esptool',
            config_filenames=['esptool.cfg'],
            env_var='ESPTOOL_CFGFILE',
        )
    """

    def __init__(
        self,
        section_name: str,
        config_filenames: list[str],
        env_var: Optional[str] = None,
    ):
        self.section_name = section_name
        self.config_filenames = config_filenames
        self.env_var = env_var

    def find(self) -> Optional[Path]:
        """
        Search for config file in standard locations.
        Order: env var override → cwd → ~/.config/<tool>/ → ~/
        """
        # 1. Environment variable override
        if self.env_var:
            env_path = os.environ.get(self.env_var)
            if env_path:
                p = Path(env_path)
                if p.is_file():
                    return p
                raise ConfigError(
                    f'Config file specified by {self.env_var} not found: {env_path}'
                )

        # 2. Standard search paths
        search_dirs = [
            Path.cwd(),
            Path.home() / '.config' / self.section_name,
            Path.home(),
        ]
        for directory in search_dirs:
            for filename in self.config_filenames:
                candidate = directory / filename
                if candidate.is_file():
                    return candidate
        return None

    def load(self) -> configparser.ConfigParser:
        """
        Find and parse the config file. Returns a ConfigParser.
        The tool's section is guaranteed to exist if a file is found.
        """
        path = self.find()
        if path is None:
            return configparser.ConfigParser()

        parser = configparser.ConfigParser()
        parser.read(str(path))

        if not parser.has_section(self.section_name):
            raise ConfigError(
                f'Config file {path} does not have [{self.section_name}] section.'
            )
        return parser

    def get(self, key: str, fallback: Optional[str] = None) -> Optional[str]:
        """Convenience: load config and get a single value."""
        parser = self.load()
        return parser.get(self.section_name, key, fallback=fallback)
```

**Compatibility (no breaking changes):**
- **Return path:** For esptool compatibility, `load()` should return `(ConfigParser, Optional[Path])` so callers can do `cfg, path = config.load()`. Implement by caching the path from `find()` and returning it together with the parser.
- **Windows:** Search dirs must include `Path.home() / 'AppData' / 'Local' / section_name` on Windows (esptool currently uses this).
- **Caching:** Cache the result of `find()` and the parsed ConfigParser after first `load()` so repeated `get()` or `load()` do not re-scan or re-read the file.

### 4.7 rom.py — ROM ELF Path Resolution

#### What's duplicated

**Near-identical code** in two repos — even the comments are identical:

**`esp_idf_monitor/base/rom_elf_getter.py`** (37 lines):
```python
IDF_PATH = os.getenv('IDF_PATH', '')
ESP_ROM_ELF_DIR = os.getenv('ESP_ROM_ELF_DIR', '')
# 'tools/idf_py_actions/roms.json' is used for compatibility with ESP-IDF before v5.5, when the file was moved
ROMS_JSON = [
    os.path.join(IDF_PATH, 'components', 'esp_rom', 'roms.json'),
    os.path.join(IDF_PATH, 'tools', 'idf_py_actions', 'roms.json'),
]
```

**`esp_coredump/coredump.py`** L40-43:
```python
IDF_PATH = os.getenv('IDF_PATH', '')
ESP_ROM_ELF_DIR = os.getenv('ESP_ROM_ELF_DIR')
# 'tools/idf_py_actions/roms.json' is used for compatibility with ESP-IDF before v5.5, when the file was moved
ROMS_JSON = [os.path.join(IDF_PATH, 'components', 'esp_rom', 'roms.json'), ...]
```

Both also implement `get_rom_elf_path(target, chip_rev)` with identical logic: iterate `roms.json`, find matching revision, construct path.

#### Implementation

```python
# esp_pylib/rom.py
"""
ROM ELF file resolution.
Single implementation replacing duplicated code in esp-idf-monitor and esp-coredump.

Uses IDF_PATH and ESP_ROM_ELF_DIR from environment — these are the only
truly cross-tool environment variables (besides NO_COLOR).
"""
import json
import os
from typing import Optional


def get_idf_path() -> str:
    """Get IDF_PATH from environment."""
    return os.getenv('IDF_PATH', '')


def get_rom_elf_dir() -> str:
    """Get ESP_ROM_ELF_DIR from environment."""
    return os.getenv('ESP_ROM_ELF_DIR', '')


def get_roms_json_paths() -> list[str]:
    """
    Return both possible roms.json locations.
    'tools/idf_py_actions/roms.json' is used for compatibility
    with ESP-IDF before v5.5, when the file was moved.
    """
    idf = get_idf_path()
    return [
        os.path.join(idf, 'components', 'esp_rom', 'roms.json'),
        os.path.join(idf, 'tools', 'idf_py_actions', 'roms.json'),
    ]


def get_rom_elf_path(target: str, chip_rev: int) -> Optional[str]:
    """
    Resolve ROM ELF file path for a given target and chip revision.

    Returns None if IDF_PATH or ESP_ROM_ELF_DIR are not set,
    or if no matching ROM is found.
    """
    idf_path = get_idf_path()
    rom_elf_dir = get_rom_elf_dir()

    if not idf_path or not rom_elf_dir:
        return None

    target_roms = None
    for roms_json_path in get_roms_json_paths():
        try:
            with open(roms_json_path) as f:
                target_roms = json.load(f).get(target, [])
            break
        except FileNotFoundError:
            continue

    if not target_roms:
        return None

    for rom in target_roms:
        if rom.get('rev') == chip_rev:
            return os.path.join(rom_elf_dir, f'{target}_rev{chip_rev}_rom.elf')

    return None
```

### 4.8 cli/ — Reusable CLI Pieces

#### CLI framework unification: all tools migrate to rich-click

As part of the esp-pylib migration, **all consumer tools convert from `argparse` to `rich-click`** for their CLI parsing. This provides:
- Consistent `--help` styling across all Espressif tools (rich-click's colored, grouped output)
- Reusable Click parameter types (`SerialPortType`, `AnyIntType`) and option decorators
- Shell completion support out of the box
- A single CLI framework across the ecosystem (esptool/espefuse/espsecure already use rich-click)

| Tool | Current CLI | Migration |
|------|-------------|-----------|
| `esptool` / `espefuse` / `espsecure` | `rich_click` | Already done — no conversion needed |
| `esp_rfc2217_server` | `argparse` (26 lines) | Convert to `rich_click` |
| `esp-idf-monitor` | `argparse` (24 `add_argument` calls in `argument_parser.py`) | Convert to `rich_click` |
| `esp-coredump` | `argparse` (16 `add_argument` calls in `cli_ext.py`) | Convert to `rich_click` |
| `esp-idf-panic-decoder` | `argparse` (3 `add_argument` calls in `gdb_panic_server.py`) | Convert to `rich_click` |
| `esp-idf-size` | `argparse` (25 `add_argument` calls in `main.py`) | Convert to `rich_click` |
| `esp-idf-sbom` | `argparse` (38 `add_argument` calls in `sbom.py`) + `click` in `idf_ext.py` | Convert main CLI to `rich_click`; `idf_ext.py` already uses `click` |
| `clang-tidy-runner` | `argparse` or none | Convert to `rich_click` |

**Subcommand handling:** Tools that currently use argparse subparsers (esp-coredump, esp-idf-size, esp-idf-sbom) convert to Click groups with `@click.group()` / `@group.command()`.

#### What's duplicated

**Click param types** in `esptool/cli_util.py`:
- `SerialPortType(click.ParamType)` — with shell completion returning available port names
- `ChipType(click.Choice)` — accepts chip names in any case, with/without hyphen
- `AnyIntType(click.ParamType)` — parses hex/oct/bin/dec integers

**argparse options** (to be converted to Click) in `esp_coredump/cli_ext.py`:
- `--chip`, `--port`, `--baud` — repeated with same defaults and env var lookups
- `--debug` / verbosity level — duplicated logging setup

**argparse options** (to be converted to Click) in `esp_idf_monitor/argument_parser.py`:
- `--port`, `--baud`, `--target` — same pattern

#### Implementation

```python
# esp_pylib/cli/types.py
"""Reusable Click parameter types."""
import rich_click as click
from click.shell_completion import CompletionItem


class SerialPortType(click.ParamType):
    """
    Click parameter type for serial ports.
    Provides shell completion with available port names.
    """
    name = 'serial_port'

    def shell_complete(self, ctx, param, incomplete):
        try:
            from esp_pylib.serial_ports import get_port_list
            return [
                CompletionItem(p.device, help=p.description or '')
                for p in get_port_list()
                if p.device.startswith(incomplete)
            ]
        except ImportError:
            return []
```

```python
# esp_pylib/cli/options.py
"""
Reusable CLI option decorators.
Each tool can compose these with its own tool-specific options.
"""
import rich_click as click


def add_output_options(function):
    """Add --quiet and --no-color options."""
    function = click.option(
        '--quiet', '-q',
        is_flag=True,
        default=False,
        help='Suppress non-error output.',
    )(function)
    function = click.option(
        '--no-color',
        is_flag=True,
        default=False,
        help='Disable colored output.',
    )(function)
    return function
```

### 4.9 ide/ — WebSocket IDE Integration

#### Design rationale

IDEs (VS Code with the Espressif extension, Eclipse, etc.) currently have no structured way to consume warnings, errors, and diagnostics from Espressif CLI tools. Tools write human-readable colored text to stderr, and the IDE must parse that text with fragile regex patterns to extract actionable information.

Additionally, `esp-idf-monitor` already has its own WebSocket implementation (`web_socket_client.py`, ~100 lines) for **debug event coordination**: when a GDB stub or core dump is detected, the monitor sends a JSON event to the IDE, which launches a debugger, and the monitor blocks until the IDE responds with `debug_finished`. This implementation uses the `websocket-client` library (not `websockets`), has its own env var (`ESP_IDF_MONITOR_WS` / `--ws`), and is completely independent from the logging use case.

`esp-pylib` unifies both use cases — **structured logging** (all tools) and **debug event coordination** (monitor-specific) — onto a single WebSocket connection with a shared protocol. This replaces the monitor's `web_socket_client.py` and the `websocket-client` dependency.

This design was prototyped in [`ide-logger-test`](https://gitlab.espressif.cn:6688/roland/ide-logger-test) and is now incorporated into `esp-pylib` so all consumer tools get IDE integration for free.

**Key design decisions:**
- **Opt-in via environment variable** (`ESPRESSIF_IDE_WS`): Tools behave identically in normal CLI usage. No performance overhead when WebSocket is not active. Replaces monitor's `ESP_IDF_MONITOR_WS` (backward compat: if `ESPRESSIF_IDE_WS` is unset, fall back to `ESP_IDF_MONITOR_WS`).
- **Dual output**: stderr (for humans) and WebSocket (for IDEs) always carry the same information. The WebSocket adds structured metadata (file, line, suggestion) that stderr doesn't have.
- **Call-site capture**: `inspect.stack()` is used to report the actual file/line where the warning or error originated, enabling IDE "click-to-navigate" features.
- **Exception reporting**: Uncaught exceptions are automatically reported to the IDE via `sys.excepthook` and `threading.excepthook` hooks, with full traceback in the `suggestion` field.
- **Bidirectional support**: For tools that need it (e.g., monitor's GDB stub / coredump handshake), the WebSocket module exposes `send_event()` and `wait_for_event()` alongside the fire-and-forget `send_log_message()`.
- **Resilient**: WebSocket failures are silently swallowed for log messages — a broken IDE connection must never crash the tool. Debug event methods (`send_event`, `wait_for_event`) may raise on failure since the tool is explicitly expecting IDE interaction.

#### Protocol specification

**Transport:** WebSocket (RFC 6455), synchronous client from the `websockets` library.

**Activation:** The IDE sets `ESPRESSIF_IDE_WS=ws://localhost:<port>` before launching a tool. The tool connects lazily on first message.

**Message format:** JSON text frames. Each message is a single JSON object with a `type` field that determines the schema.

**Log messages** (tool → IDE, fire-and-forget):

```json
{
  "type": "warning | error | exception",
  "file": "/absolute/path/to/source.py",
  "line": 42,
  "message": "Human-readable description of the issue",
  "suggestion": "Optional actionable fix or full traceback, or null"
}
```

| Field | Type | Description |
|---|---|---|
| `type` | `string` | One of `"warning"`, `"error"`, `"exception"` |
| `file` | `string` | Absolute path to the source file where the issue was raised |
| `line` | `int` | Line number in the source file |
| `message` | `string` | Main human-readable message |
| `suggestion` | `string \| null` | Optional fix suggestion; for exceptions, contains the full traceback string |

**Debug events** (tool → IDE, tool waits for IDE response):

```json
{
  "type": "event",
  "event": "gdb_stub | coredump",
  "port": "/dev/ttyUSB0",
  "prog": "/path/to/build/app.elf",
  "file": "/tmp/coredump.bin"
}
```

| Field | Type | Description |
|---|---|---|
| `type` | `string` | Always `"event"` for debug events |
| `event` | `string` | One of `"gdb_stub"`, `"coredump"` |
| `port` | `string \| null` | Serial port (for GDB stub) |
| `prog` | `string` | Path to the ELF file |
| `file` | `string \| null` | Path to the coredump file (for coredump events) |

**IDE responses** (IDE → tool):

```json
{
  "type": "event",
  "event": "debug_finished"
}
```

This replaces the protocol currently used by `esp-idf-monitor`'s `WebSocketClient` (`web_socket_client.py`), which sends `{'event': 'gdb_stub', ...}` and `{'event': 'coredump', ...}` and blocks on `{'event': 'debug_finished'}`. The new protocol wraps these in the unified `type`-discriminated format so the IDE can distinguish log messages from debug events on the same connection.

#### Implementation

```python
# esp_pylib/ide/__init__.py
"""WebSocket IDE integration — optional structured logging to IDEs."""
```

```python
# esp_pylib/ide/ws.py
"""
WebSocket client: send structured log messages to an IDE when ESPRESSIF_IDE_WS is set.
Silently does nothing when the env var is unset or the connection fails.
"""
import json
import os
from typing import Optional

_ws_url: Optional[str] = None
_connection = None
_ws_url_checked = False


def _get_ws_url() -> Optional[str]:
    global _ws_url, _ws_url_checked
    if not _ws_url_checked:
        _ws_url = (
            os.environ.get('ESPRESSIF_IDE_WS')
            or os.environ.get('ESP_IDF_MONITOR_WS')  # backward compat
            or None
        )
        _ws_url_checked = True
    return _ws_url


def _ensure_connection():
    """Return existing connection or create new one; None if not configured."""
    global _connection
    url = _get_ws_url()
    if not url:
        return None
    if _connection is not None:
        return _connection
    try:
        from websockets.sync.client import connect
        _connection = connect(url)
        return _connection
    except Exception:
        _connection = None
        return None


def send_log_message(
    typ: str,
    message: str,
    suggestion: Optional[str],
    file: str,
    line: int,
) -> None:
    """Send a structured log message to the IDE. No-op if ESPRESSIF_IDE_WS is unset."""
    if not _get_ws_url():
        return
    payload = json.dumps({
        'type': typ,
        'file': file,
        'line': line,
        'message': message,
        'suggestion': suggestion,
    })
    conn = _ensure_connection()
    if conn is None:
        return
    try:
        conn.send(payload)
    except Exception:
        global _connection
        _connection = None
        conn = _ensure_connection()
        if conn is not None:
            try:
                conn.send(payload)
            except Exception:
                pass


def send_event(event: str, **kwargs) -> None:
    """
    Send a debug event to the IDE. Raises RuntimeError if not connected.
    Used by esp-idf-monitor for GDB stub and coredump coordination.
    """
    conn = _ensure_connection()
    if conn is None:
        raise RuntimeError('WebSocket not configured (ESPRESSIF_IDE_WS not set)')
    payload = json.dumps({'type': 'event', 'event': event, **kwargs})
    conn.send(payload)


def wait_for_event(event: str, retries: int = 3) -> dict:
    """
    Block until the IDE sends a message with matching event type.
    Used by esp-idf-monitor to wait for 'debug_finished' from the IDE.
    Raises RuntimeError if connection fails or retries are exhausted.
    """
    conn = _ensure_connection()
    if conn is None:
        raise RuntimeError('WebSocket not configured (ESPRESSIF_IDE_WS not set)')
    for _ in range(retries):
        try:
            raw = conn.recv()
            msg = json.loads(raw)
            if msg.get('event') == event:
                return msg
        except Exception:
            _reconnect()
            conn = _ensure_connection()
            if conn is None:
                break
    raise RuntimeError(f'Did not receive expected event: {event}')


def close() -> None:
    """Close the WebSocket connection (call on tool exit)."""
    global _connection
    if _connection is not None:
        try:
            _connection.close()
        except Exception:
            pass
        _connection = None
```

```python
# esp_pylib/ide/excepthook.py
"""
Exception reporting hooks: sys.excepthook and threading.excepthook.
Reports uncaught exceptions to the IDE via WebSocket with full traceback.
"""
import sys
import threading
import traceback
from types import TracebackType
from typing import Callable, Optional

from esp_pylib.ide.ws import send_log_message

_SysExcepthook = Callable[[type[BaseException], BaseException, Optional[TracebackType]], None]

_previous_sys_excepthook: _SysExcepthook = sys.excepthook
_previous_thread_excepthook = getattr(threading, 'excepthook', None)


def _extract_location(tb: Optional[TracebackType]) -> tuple[Optional[str], Optional[int]]:
    """Return (file, line) from the innermost frame of the traceback."""
    if tb is None:
        return (None, None)
    while tb.tb_next is not None:
        tb = tb.tb_next
    return (tb.tb_frame.f_code.co_filename, tb.tb_lineno)


def _format_traceback(
    typ: type[BaseException], value: BaseException, tb: Optional[TracebackType]
) -> Optional[str]:
    if tb is None:
        return None
    return ''.join(traceback.format_exception(typ, value, tb)).strip() or None


def _should_report(typ: type[BaseException]) -> bool:
    return typ is not SystemExit and typ is not KeyboardInterrupt


def _sys_excepthook(
    typ: type[BaseException], value: BaseException, tb: Optional[TracebackType]
) -> None:
    try:
        if _should_report(typ):
            file, line = _extract_location(tb)
            send_log_message(
                'exception',
                str(value) if value else '',
                _format_traceback(typ, value, tb),
                file or '<unknown>',
                line if line is not None else 0,
            )
    except Exception:
        pass
    finally:
        _previous_sys_excepthook(typ, value, tb)


def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
    try:
        typ, value, tb = args.exc_type, args.exc_value, args.exc_traceback
        if typ is not None and _should_report(typ):
            if value is None:
                value = typ()
            file, line = _extract_location(tb)
            send_log_message(
                'exception',
                str(value) if value else '',
                _format_traceback(typ, value, tb) if tb else None,
                file or '<unknown>',
                line if line is not None else 0,
            )
    except Exception:
        pass
    finally:
        if _previous_thread_excepthook is not None:
            _previous_thread_excepthook(args)


def install_exception_reporting() -> None:
    """Install exception hooks for IDE reporting. Safe to call multiple times."""
    global _previous_sys_excepthook, _previous_thread_excepthook
    if sys.excepthook is not _sys_excepthook:
        _previous_sys_excepthook = sys.excepthook
        sys.excepthook = _sys_excepthook
    if hasattr(threading, 'excepthook') and threading.excepthook is not _thread_excepthook:
        _previous_thread_excepthook = threading.excepthook
        threading.excepthook = _thread_excepthook
```

#### Integration with EspLog

The `EspLog` class (Section 4.4) is extended to send structured messages over WebSocket alongside stderr output:

```python
# In esp_pylib/log.py — updated err/warn methods

import inspect
from esp_pylib.ide.ws import send_log_message

class EspLog:
    # ... (existing __new__, set_quiet, set_verbose, print, debug as before) ...

    def _get_call_site(self) -> tuple[str, int]:
        """Return (file, line) of the caller that invoked err/warn/note."""
        frame = inspect.stack()[2]  # 0=_get_call_site, 1=err/warn, 2=caller
        return (frame.filename, frame.lineno)

    def err(self, msg: str, suggestion: str | None = None) -> None:
        """Error message (red, bold) to stderr + WebSocket."""
        self._stderr.print(f'[bold red]ERROR:[/bold red] {msg}')
        file, line = self._get_call_site()
        send_log_message('error', msg, suggestion, file, line)

    def warn(self, msg: str, suggestion: str | None = None) -> None:
        """Warning message (yellow) to stderr + WebSocket."""
        self._stderr.print(f'[yellow]WARNING:[/yellow] {msg}')
        file, line = self._get_call_site()
        send_log_message('warning', msg, suggestion, file, line)

    def die(self, msg: str, suggestion: str | None = None, exit_code: int = 1) -> None:
        """Print error and exit."""
        self.err(msg, suggestion)
        sys.exit(exit_code)
```

The `suggestion` parameter is optional. In normal CLI usage, it is not printed to stderr — it exists exclusively for IDE consumption. This enables IDE-specific features like "Quick Fix" actions without cluttering terminal output.

#### How consumers use IDE integration

**Zero-effort adoption:** Any tool that uses `EspLog` automatically gets IDE integration. No code changes needed in consumer repos — the `ESPRESSIF_IDE_WS` env var is set by the IDE extension, not by the tool.

```python
# Example: esptool using the logger (unchanged from non-IDE usage)
from esp_pylib.log import log

log.warn(
    'Flash size mismatch: detected 4MB but binary expects 8MB.',
    suggestion='Use --flash_size 4MB or flash a binary built for 4MB.',
)
```

When run from the IDE, the warning appears both in the terminal (yellow text) and as a structured diagnostic in the IDE's Problems panel with a clickable file:line link and the suggestion as a tooltip/action.

**Exception reporting** is also automatic — tools that `import esp_pylib` get exception hooks installed. An uncaught exception during `esptool.py write_flash` will appear in the IDE with the full traceback and the offending file:line highlighted.

---

## 5. Phased Implementation

### Phase 1: Scaffolding & Constants (Week 1)

#### Tasks

1. ~~**Create repository** `espressif/esp-pylib` on GitHub~~ (done)
2. ~~**Set up `pyproject.toml`** with setuptools build backend, commitizen, ruff, mypy~~ (done)
3. ~~**Set up GitHub Actions CI** (lint, type check, test, publish)~~ (done)
4. **Implement `constants.py`:**
   - Hardware: `ESPRESSIF_VID`, `USB_JTAG_SERIAL_PID`, `ESP_ROM_BAUD`
   - Serial discovery only: `MACOS_PORT_EXCLUDE_LIST`, `LINUX_DEVICE_PATTERNS`, `MACOS_DEVICE_PATTERNS`
5. **`serial_reset.py` (with `[serial]` extra):** define `PIN_LOW`, `PIN_HIGH`, `DEFAULT_RESET_DELAY`, `MINIMAL_EN_LOW_DELAY`, and Unix-only `TIOCMSET`, `TIOCMGET`, `TIOCM_DTR`, `TIOCM_RTS` alongside `set_dtr` / `set_rts` / `set_dtr_rts` (not in `constants.py`).
6. **Implement `errors.py`:**
   - `FatalError(RuntimeError)`
   - `NoSerialPortFoundError(FatalError)`
   - `ConfigError(FatalError)`


### Phase 2: Logging, Config, ROM ELF (Week 2)

#### Tasks

1. **Implement `log.py`:**
   - `EspLog` singleton class with rich `Console`
   - Methods: `print()`, `err()`, `warn()`, `note()`, `debug()`, `die()`; aliases `warning`, `error`
   - **Streams:** errors/warnings → stderr; **note → stdout** with **"Note: "** prefix; plain → stdout or `file=` if given
   - **print(..., file=..., end=..., sep=..., flush=...)** — stream resolved at call time (dump-to-file, tests)
   - `set_quiet()`, `set_verbose()`, **`set_verbosity(mode: str)`** — `"auto"` | `"verbose"` | `"silent"` | `"compact"`
   - **`EspLogBase`** ABC defining the logger interface; **`set_logger(instance)`** to replace with any `EspLogBase` implementation (custom integrations, tests); `_reset()` to restore default
   - `NO_COLOR` env var and smart-feature behavior (TTY/TERM; optional Windows colorama)
   - Module-level `log = EspLog()` instance
   - `suggestion` parameter on `err()`, `warn()`, `die()` for IDE consumption
   - Call-site capture via `inspect.stack()` for file:line metadata
   - **Out of scope in esp-pylib:** progress_bar and stage (esptool implements in EsptoolLogger subclass); idf.py async tee, ANSI strip, progression line (idf.py layer)
2. **Implement `ide/ws.py`:**
   - WebSocket client activated by `ESPRESSIF_IDE_WS` env var
   - `send_log_message()` — sends structured JSON to IDE
   - Lazy connection with reconnect-on-failure
   - Silent no-op when env var is unset (zero overhead)
3. **Implement `ide/excepthook.py`:**
   - Custom `sys.excepthook` and `threading.excepthook`
   - Reports uncaught exceptions with full traceback to IDE via WebSocket
   - Chains to previous hooks (non-invasive)
   - Filters `SystemExit` and `KeyboardInterrupt`
4. **Implement `config.py`:**
   - `ToolConfig` class: `__init__(section_name, config_filenames, env_var)`
   - `find()` — search cwd → `~/.config/<tool>/` → `~`
   - `load()` → return `ConfigParser`
   - `get(key, fallback)` — convenience method
5. **Implement `rom.py`:**
   - `get_idf_path()`, `get_rom_elf_dir()`
   - `get_roms_json_paths()` — both locations for IDF v5.5 compat
   - `get_rom_elf_path(target, chip_rev)` — full resolution logic
6. **Write tests:**
   - Log: capture stderr, verify `NO_COLOR` behavior, test quiet mode
   - IDE: WebSocket send with in-process server, verify JSON payload shape, exception hooks
   - Config: test search order with tmp dirs, env var override, missing section error
   - ROM: test with mock `roms.json` files, missing IDF_PATH, missing rev

**Deliverable:** Publish `v0.2.0` — logging, IDE integration, config, ROM ELF resolution.

### Phase 3: Serial Logic (Week 3)

#### Tasks

1. **Implement `serial/ports.py`:**
   - `_sort_key()` — platform-aware sorting with Espressif VID priority
   - `_is_blacklisted()` — macOS virtual port filter
   - `get_port_list()` — enumerate, filter, sort
   - `get_port_names()` — convenience returning device paths
   - `detect_port()` — auto-detect best port, raise `NoSerialPortFoundError`
   - `parse_port_filters()` — parse `key=value` CLI filter args
2. **Implement `serial/reset.py`:**
   - `set_dtr()`, `set_rts()` — with Windows `usbser.sys` workaround
   - `set_dtr_rts()` — Unix ioctl atomic set
   - `parse_custom_reset_sequence()` — parse `D0|R1|U1,0|W0.1` format
   - `execute_custom_reset()` — run parsed sequence (replaces both tools' `exec()` paths)
   - `classic_bootloader_reset()`, `unix_tight_bootloader_reset()`,
     `usb_jtag_bootloader_reset()`, `hard_reset()` — named pulse-train sequences
     parameterized on timing so esptool passes its constants and esp-idf-monitor
     passes per-chip `chip_config` values
3. **Implement `cli/types.py`:**
   - `SerialPortType(click.ParamType)` with shell completion
4. **Write tests** with mocked `serial.tools.list_ports`:
   - Port listing: verify filtering, sorting, VID priority
   - Port detection: verify best-port selection, error on empty
   - Reset primitives: verify DTR/RTS calls with mock port objects
   - Reset sequences: verify exact (kind, value) call ordering against the
     legacy esptool/esp-idf-monitor sequences they replace
   - Filters: verify `key=value` parsing and error handling

**Deliverable:** Publish `v0.3.0` — feature-complete serial + CLI modules.

### Phase 4: Documentation & Stabilization (Week 4)

#### Tasks

1. **Write README.md** with:
   - Installation instructions
   - Quick-start examples for each module
   - Migration guide per consumer repo (summary table)
2. **Add API documentation** (docstrings are already in place; optionally add Sphinx/mkdocs)
3. **Add CI check** that prevents `esp-pylib` from importing any consumer tool (circular dep guard)
4. **Run compatibility testing** — install `esp-pylib` alongside each consumer tool, verify no conflicts
5. **Stabilize API** — review all public interfaces, mark anything experimental
6. **Create skill.md file** - should help with automated adoption of repository by AI

**Deliverable:** Publish `v1.0.0` — stable, documented, ready for consumer migration.

### Phase 5: Migration of Consumer Repos (Weeks 5–8)

Migrate one repo at a time, each in its own PR. Each PR should:
- Add `esp-pylib` dependency to `pyproject.toml`
- Replace duplicated code with imports
- Delete files that are now redundant
- Run full test suite
- Note: tool-specific constants (CMD_*, TAG_*, panic states, etc.) stay local
- **No breaking changes:** Preserve existing public APIs and behavior for each package. See **Section 9 (Breaking Change Audit)** for required compatibility wrappers (e.g. esptool must keep `get_port_list()` returning `list[str]`, `load_config_file()` returning `(cfg, path)`, and `parse_port_filters()` returning a tuple). Implement mitigations in esp-pylib (e.g. EspLog aliases, ToolConfig return shape and Windows paths) before or in sync with migration.

#### 5.1 `esptool` (Week 5)

| Action | File | Details |
|---|---|---|
| Add dependency | `pyproject.toml` | Add `"esp-pylib[serial]>=1.0.0"` to `dependencies` |
| Replace VID/PID | `esptool/loader.py` L305 | `from esp_pylib.constants import USB_JTAG_SERIAL_PID` |
| Replace VID/PID | `espefuse/efuse/emulate_efuse_controller_base.py` L33 | Same import |
| Replace port logic | `esptool/cli_util.py` L487-600 | Use esp_pylib internally but **keep public API**: `get_port_list()` must still return `list[str]` (wrap: `[p.device for p in esp_pylib.serial_ports.get_port_list(...)]`). `parse_port_filters()` must still return `(vids, pids, names, serials)` tuple (wrap esp_pylib's dict return). Re-export both in `__init__.py` so external callers (tests, esp_rfc2217_server) do not break. |
| Replace SerialPortType | `esptool/cli_util.py` L85-110 | Import from `esp_pylib.cli_types` (or keep local if esptool has extra customization) |
| Replace DTR/RTS primitives | `esptool/reset.py` L14-80 | `from esp_pylib.serial_reset import set_dtr, set_rts, set_dtr_rts`. Delete the local Unix-only TIOCM constants block. |
| Replace reset sequences | `esptool/reset.py` L93-167 | Strategy classes (`ClassicReset`, `UnixTightReset`, `USBJTAGSerialReset`, `HardReset`) stay locally for their `__call__` retry/reopen behavior, but `reset()` bodies become one-line calls into `esp_pylib.serial_reset`: `classic_bootloader_reset(self.port, 0.1, self.reset_delay)`, `unix_tight_bootloader_reset(self.port, 0.1, self.reset_delay)`, `usb_jtag_bootloader_reset(self.port)`, and `hard_reset(self.port, 0.2, 0.2) if self.uses_usb else hard_reset(self.port, 0.1, 0.0)`. |
| Delete `CustomReset` `exec()` | `esptool/reset.py` L169-211 | Replace `CustomReset.format_dict` + `_parse_string_to_seq` + `exec(self.constructed_strategy)` with `from esp_pylib.serial_reset import execute_custom_reset; execute_custom_reset(self.port, seq_str)`. Keep `CustomReset` as a thin `ResetStrategy` wrapper so the retry/reopen behavior is preserved. Convert `FatalError` raise on parse error into catching the `ValueError` raised by `parse_custom_reset_sequence` and re-raising as `FatalError`. |
| Replace config loader | `esptool/config.py` | Use `ToolConfig` (with `config_filenames=['esptool.cfg', 'setup.cfg', 'tox.ini']`). **Keep `load_config_file(verbose=False)` as public API:** return `(cfg, cfg_file_path)` where cfg is the parser and path from ToolConfig.load(); implement via wrapper so `loader.py` and `esp_rfc2217_server` continue to work. ToolConfig must support Windows path (AppData) and return path (see Section 9). |
| Replace FatalError base | `esptool/util.py` | `from esp_pylib.errors import FatalError`. Keep `FatalError.WithResult` as local extension. |
| Keep locally | `esptool/logger.py` | Keep `EsptoolLogger` — it extends the common logger with stage collapsing. Refactor to subclass `EspLog` from `esp_pylib.log`. |
| Migrate sys.exit | `esptool/__init__.py`, `espefuse/__init__.py`, `espsecure/__init__.py`, `espsecure/esp_hsm_sign/__init__.py` | ~20+ `sys.exit()` calls (exit codes 0, 1, 2). Evaluate each: error exits → `log.die(msg, exit_code=N)`; success exits and `SystemExit` catches stay as-is. Notably `esp_hsm_sign/__init__.py` has 8 `sys.exit(1)` calls that should become `log.die()`. |
| Convert esp_rfc2217_server CLI | `esp_rfc2217_server/__init__.py` | Convert from `argparse` to `rich_click`. Replace Python `logging` module usage (`logging.getLogger`, `logger.info`) with `EspLog`. |
| Keep locally | `esptool/targets/__init__.py` | `CHIP_DEFS`, `CHIP_LIST`, `ROM_LIST` — all tied to ROM classes. Stay in esptool. |
| Keep locally | All env var defaults | `ESPTOOL_PORT`, `ESPTOOL_BAUD`, `ESPTOOL_CHIP`, etc. — package-specific, stay in `esptool/__init__.py` Click option defaults. |

#### 5.2 `esp-idf-monitor` (Week 6)

| Action | File | Details |
|---|---|---|
| Add dependency | `pyproject.toml` | Add `"esp-pylib[serial,ide]>=1.0.0"`. Remove `websocket-client` from `[ide]` optional deps (replaced by `websockets` via esp-pylib). |
| Replace constants | `esp_idf_monitor/base/constants.py` L62-76 | Delete `MINIMAL_EN_LOW_DELAY`, `USB_JTAG_SERIAL_PID`, `LOW`, `HIGH`, `FILTERED_PORTS`. Replace with: `USB_JTAG_SERIAL_PID` and port-filter tuple from `esp_pylib.constants`; `MINIMAL_EN_LOW_DELAY`, `LOW`/`HIGH` (as `PIN_LOW`/`PIN_HIGH`) from `esp_pylib.serial_reset`. Keep all monitor-specific constants (CMD_*, TAG_*, panic states, key chars, timeouts). |
| Refactor output_helpers | `esp_idf_monitor/base/output_helpers.py` | Delete diagnostic print functions (`note_print`, `warning_print`, `error_print`, `red_print`, `yellow_print`, `green_print`, `normal_print`, `color_print`). All callers switch to `from esp_pylib.log import log; log.err(msg)` / `log.warn(msg)` / `log.note(msg)`. **Keep locally:** `ANSI_*_B` byte constants, `AUTO_COLOR_REGEX`, and `COMMON_PREFIX` — these are used by `print_colored()` for byte-level serial data coloring (cannot use `rich` for raw byte streams, see Section 1.3). |
| Delete rom_elf_getter | `esp_idf_monitor/base/rom_elf_getter.py` | Delete (37 lines). Replace with `from esp_pylib.rom import get_rom_elf_path`. |
| Replace reset primitives | `esp_idf_monitor/base/reset.py` L20-30, L83-106 | Delete `_setDTR`, `_setRTS`, `_setDTRandRTS` and the local TIOCM constants. Import `set_dtr`, `set_rts`, `set_dtr_rts` from `esp_pylib.serial_reset`. |
| Replace reset sequences | `esp_idf_monitor/base/reset.py` L118-162 | `Reset.hard()` body becomes `hard_reset(self.serial_instance, hold_delay=self.chip_config['reset'])`. `Reset.to_bootloader()` keeps its PID-based branching and config-loading, but the two built-in branches collapse to `usb_jtag_bootloader_reset(self.serial_instance)` and `classic_bootloader_reset(self.serial_instance, self.chip_config['enter_boot_set'], self.chip_config['enter_boot_unset'])`. |
| Delete custom-reset `exec()` | `esp_idf_monitor/base/reset.py` L34-39, L108-116, L123, L135 | Delete `format_dict` and `_parse_string_to_seq`. Replace both `exec(self._parse_string_to_seq(...))` call sites with `from esp_pylib.serial_reset import execute_custom_reset; execute_custom_reset(self.serial_instance, self.custom_seq)` (and same for `custom_hard_seq`). The `error_print` on parse failure becomes a `try/except ValueError` around `execute_custom_reset` that calls `error_print(str(exc))`. |
| Replace config | `esp_idf_monitor/config.py` | `ToolConfig(section_name='esp-idf-monitor', config_filenames=['idf_monitor.cfg'], env_var='ESP_IDF_MONITOR_CFGFILE')` |
| Delete WebSocketClient | `esp_idf_monitor/base/web_socket_client.py` | Delete entirely (~100 lines). Replace with `from esp_pylib.ide.ws import send_event, wait_for_event, close`. In `gdbhelper.py`: replace `websocket_client.send({'event': 'gdb_stub', ...})` → `send_event('gdb_stub', port=..., prog=...)` and `websocket_client.wait(...)` → `wait_for_event('debug_finished')`. Same pattern in `coredump.py`. Remove `websocket-client` from `pyproject.toml` deps (replaced by `websockets` via `esp-pylib[ide]`). |
| Unify WS env var | `esp_idf_monitor/base/argument_parser.py` | Change `--ws` default from `ESP_IDF_MONITOR_WS` to `ESPRESSIF_IDE_WS` (esp-pylib falls back to `ESP_IDF_MONITOR_WS` for backward compat). |
| **Convert CLI to rich-click** | `esp_idf_monitor/base/argument_parser.py` | Convert all 24 `add_argument` calls from `argparse` to `rich_click`. Replace `argparse.ArgumentParser` with `@click.command()` / `@click.option()` / `@click.argument()`. Options: `--port`, `--no-reset`, `--disable-address-decoding`, `--baud`, `--make`, `--encrypted`, `--toolchain-prefix`, `--eol`, `elf_files` (positional), `--rom-elf-file`, `--print_filter`, `--decode-coredumps`, `--decode-panic`, `--target`, `--revision`, `--ws`, `--timestamps`, `--timestamp-format`, `--force-color`, `--disable-auto-color`, `--open-port-attempts`, `--save-log`. Use `esp_pylib.cli_types.SerialPortType` for `--port`. |
| Migrate sys.exit | `esp_idf_monitor/idf_monitor.py` | 3 `sys.exit()` calls (lines 183, 419, 427) → convert error exits to `log.die()`. `SystemExit` catch in `coredump.py:82` stays. |
| Replace bare print | `esp_idf_monitor/base/serial_reader.py` L62 | Replace `print(e)` with `log.err(str(e))`. |
| Keep locally | `esp_idf_monitor/base/constants.py` | `CTRL_C`, `CTRL_H`, `CONSOLE_STATUS_QUERY`, `CMD_*`, `TAG_*`, `PANIC_*`, `DEFAULT_TOOLCHAIN_PREFIX`, `EVENT_QUEUE_TIMEOUT`, `RECONNECT_DELAY`, `GDB_*`, `ESPPORT_ENVIRON`, `ESPTOOL_OPEN_PORT_ATTEMPTS_ENVIRON`, etc. |
| Keep locally | `esp_idf_monitor/base/exceptions.py` | `SerialStopException(Exception)` — monitor-specific control flow exception. |
| Keep locally | `esp_idf_monitor/base/serial_handler.py` | `print_colored()` method and its use of `ANSI_*_B` byte constants — byte-level serial data coloring pipeline. |
| Keep locally | `esp_idf_monitor/base/ansi_color_converter.py` | `ANSIColorConverter` — Windows byte-level ANSI → Win32 console API conversion. |

#### 5.3 `esp-coredump` (Week 7)

| Action | File | Details |
|---|---|---|
| Add dependency | `pyproject.toml` | Add `"esp-pylib>=1.0.0"` (no `[serial]` extra needed — coredump delegates serial to esptool) |
| Replace ROM ELF | `esp_coredump/coredump.py` L40-43 + `get_rom_elf_path()` | Delete module-level `IDF_PATH`, `ESP_ROM_ELF_DIR`, `ROMS_JSON`. Replace `get_rom_elf_path()` method with `from esp_pylib.rom import get_rom_elf_path`. |
| Replace FatalError | `esp_coredump/tools.py` | Delete `class FatalError(Exception)`. `from esp_pylib.errors import FatalError`. |
| Replace output (stderr) | `esp_coredump/coredump.py` L513-520 + `corefile/_parse_soc_header.py` L48 | Replace `print(..., file=sys.stderr)` and box-drawing error output with `log.err(msg)`. |
| Replace output (stdout) | `esp_coredump/coredump.py` ~20 calls | ~20 `print()` calls for task info, GDB output, thread tables, chip revision messages. Migrate to `log.print()` for consistent output handling. Version banner in `__main__.py` L16 also migrates. |
| Replace logging | `esp_coredump/corefile/loader.py`, `corefile/gdb.py`, `__main__.py` | **16 `logging.warning/debug/error/info` calls** in `loader.py` + `logging.warning` in `gdb.py` + `logging.basicConfig` setup in `__main__.py`. Replace `logging.warning(msg)` → `log.warn(msg)`, `logging.error(msg)` → `log.err(msg)`, `logging.debug(msg)` → `log.debug(msg)`, `logging.info(msg)` → `log.print(msg)`. Delete `import logging` and custom level mapping in `__main__.py`. |
| **Convert CLI to rich-click** | `esp_coredump/cli_ext.py` | Convert 16 `add_argument` calls from `argparse` to `rich_click`. Replace `argparse.ArgumentParser` + subparsers with `@click.group()` / `@group.command()`. Options: `--chip`, `--chip-rev`, `--port` (use `SerialPortType`), `--baud`, `--gdb-timeout-sec`, `--version`, `--debug`/`-d`, `--gdb`, `--extra-gdbinit-file`, `--core`, `--core-format`, `--off`, `--parttable-off`, `--save-core`, `--rom-elf`, `prog` (positional). Subcommand `info_corefile` has `--print-mem`. Replace debug level mapping (`-d` count → log level) with `log.set_verbosity()`. |
| Migrate sys.exit | `esp_coredump/coredump.py`, `corefile/loader.py`, `corefile/_parse_soc_header.py` | 3 `sys.exit(1)` + 2 `raise SystemExit(...)`. Convert error exits to `log.die()` or `raise FatalError(...)`. `raise SystemExit(...)` in `loader.py:106` (invalid core format) → `raise ESPCoreDumpLoaderError(...)`. |
| Keep locally | `esp_coredump/corefile/__init__.py` | `SUPPORTED_TARGETS`, `XTENSA_TARGETS`, `RISCV_TARGETS` — coredump's own supported subset. `ESPCoreDumpError`, `ESPCoreDumpLoaderError` — coredump-specific error subclasses (extend `FatalError` from esp-pylib). |

#### 5.4 `esp-idf-panic-decoder` (Week 7)

| Action | File | Details |
|---|---|---|
| Add dependency | `pyproject.toml` | Add `"esp-pylib>=1.0.0"` |
| Delete output_helpers | `esp_idf_panic_decoder/output_helpers.py` | Delete entire file (15 lines: `ANSI_RED`, `ANSI_NORMAL`, `red_print()`). |
| Update callers | `panic_output_decoder.py` L52, `pc_address_decoder.py` L156,159,160 | Replace `from .output_helpers import red_print` → `from esp_pylib.log import log`. Replace `red_print(msg)` → `log.err(msg)`. |
| Replace logging | `gdb_panic_server.py` L25, 166, 188, 224, 229 | Replace `import logging` / `logging.getLogger('GdbServer')` / `logger.debug(...)` with `from esp_pylib.log import log` / `log.debug(...)`. |
| **Convert CLI to rich-click** | `gdb_panic_server.py` L266-272 | Convert 3 `add_argument` calls from `argparse` to `rich_click`: `input_file` (positional), `--target`, `--gdb-log`. Replace `argparse.ArgumentParser` with `@click.command()`. |
| Migrate sys.exit | `gdb_panic_server.py` L213, 232, 282 | 2 `raise SystemExit(0/1)` + 1 `sys.exit(0)`. Convert error exit (`SystemExit(1)`) → `log.die()`. Success/clean exits stay as `raise SystemExit(0)`. |

#### 5.5 `esp-idf-size` (Week 8)

| Action | File | Details |
|---|---|---|
| Add dependency | `pyproject.toml` | Add `"esp-pylib>=1.0.0"`. Can remove direct `"rich"` dependency (comes transitively). |
| Replace log module | `esp_idf_size/log.py` | Delete local `log.py` (~50 lines, has `console_stdout`, `console_stderr`, custom `print()`, `err()`, `die()`). Replace all imports with `from esp_pylib.log import log`. |
| Replace console | Various (`format_table.py`, `format_tree.py`, `format_raw.py`, `format_json.py`, `format_dot.py`, `format_csv.py`) | Replace `log.print(...)` calls (currently using local log module) with `esp_pylib.log.log.print(...)`. |
| Replace raw prints | `memorymap.py` L25, 30, 41, 49 | Replace `print(e, file=sys.stderr)` → `log.err(str(e))`. Replace stdout `print()` → `log.print()`. |
| **Convert CLI to rich-click** | `esp_idf_size/main.py` | Convert 25 `add_argument` calls from `argparse` to `rich_click`. Replace `argparse.ArgumentParser` + subparsers with `@click.group()` / `@group.command()`. Main arguments include input files, `--format` (table/csv/json/tree/raw/dot), `--output`, `--diff`, `--archives`, `--files`, `--target`, `--config`, `--filter`, `--depth`, etc. |
| Migrate sys.exit | `main.py` L280, `log.py` L38 | 2 `sys.exit(1)` calls. `log.py:38` is already a `die()` equivalent — replaced when log module is deleted. `main.py:280` → `log.die()`. |
| Keep locally | `esp_idf_size/memorymap.py`, `mapfile.py`, `elf.py` | Custom exceptions `MemMapException`, `MapFileException`, `Elf_Exception` — tool-specific parsing errors, stay local. 21 raise sites use these internally. |

#### 5.6 `esp-idf-sbom` (Week 8)

| Action | File | Details |
|---|---|---|
| Add dependency | `pyproject.toml` | Add `"esp-pylib>=1.0.0"`. Can remove direct `"rich"` dependency. |
| Replace log module | `esp_idf_sbom/libsbom/log.py` | Delete local `log.py` (~40 lines, has Rich-based `err()`, `warn()`, `debug()`, `die()`, `print()` — very similar to `EspLog`). Replace all imports with `from esp_pylib.log import log`. Note: local `die()` calls `sys.exit(128)` — verify exit code expectations when switching to `log.die()`. |
| Replace output | `sbom.py`, `libsbom/report.py` | Replace `log.print(...)` calls with `esp_pylib.log.log.print(...)`. Report formatting (`report.py` ~9 calls) uses Rich tables/panels — pass through `log.print()`. |
| **Convert main CLI to rich-click** | `esp_idf_sbom/sbom.py` | Convert 38 `add_argument` calls from `argparse` to `rich_click`. Replace `argparse.ArgumentParser` + 5 subparsers (`create`, `check`, `license`, `manifest-validate`, `manifest-check`) with `@click.group()` / `@group.command()`. Key options include `--input-file`, `--output-file`, `--config`, `--format`, `--target`, `--project-dir`, `--build-dir`, etc. |
| Keep idf_ext.py as click | `esp_idf_sbom/idf_ext.py` | Already uses `click` for ESP-IDF extension integration — no conversion needed. |
| Migrate sys.exit | `sbom.py` L66, 935, 940, 947; `__main__.py` L9 | 5 `sys.exit()` calls. Error exits → `log.die()`. `sys.exit(main())` pattern in `__main__.py` and `sbom.py:947` stays as-is. |

#### 5.7 `clang-tidy-runner` (Week 8)

| Action | File | Details |
|---|---|---|
| Add dependency | `pyproject.toml` (needs to be created/migrated from `setup.py`) | Add `"esp-pylib>=1.0.0"` |
| Use logger | Various | Replace `print()` calls with `from esp_pylib.log import log`. |
| **Convert CLI to rich-click** | Various | Convert any `argparse` usage to `rich_click`. Full audit of CLI arguments, `sys.exit()` calls, exceptions, and `logging` usage needed (repo not in local workspace — audit during migration). |

#### 5.8 `esp-idf` Python tools (Week 8)

| Action | File | Details |
|---|---|---|
| Add dependency | `tools/requirements/requirements.core.txt` | Add `esp-pylib>=1.0.0` |
| Replace port detection | `tools/idf_py_actions/serial_ext.py` | Use `from esp_pylib.serial_ports import detect_port` |
| Replace error classes | `tools/idf_py_actions/errors.py` | Subclass from `esp_pylib.errors.FatalError` |

---

## 6. Risk Management

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Breaking existing tools during migration** | Medium | High | Migrate one repo per PR. Keep backward-compat shims (deprecated re-exports) for one major version. Run each tool's full test suite after migration. |
| **Circular dependency** | Low | Critical | `esp-pylib` must never import from any consumer. Add CI lint rule: `import esp_pylib` must not trigger import of `esptool`, `esp_coredump`, etc. |
| **Rich/Click version conflicts** | Low | Medium | Pin `rich>=12.0`, `rich-click>=1.7,<2`, `click>=8.0,<9` — already compatible with esptool's current pins (`rich_click<2`, `click<9`). |
| **Rich output breaks monitor's binary serial stream** | Low | High | `log.py` writes to `Console(stderr=True)`. Monitor's binary serial output goes to stdout/serial port directly. These paths don't intersect. |
| **WebSocket connection slows down tool execution** | Low | Low | WebSocket is lazy-connected on first message and reused. `send_log_message()` is synchronous but fast (localhost JSON). If connection fails, it is silently skipped — no retries or blocking. When `ESPRESSIF_IDE_WS` is unset, the code path is a single `None` check with zero overhead. |
| **WebSocket dependency adds weight for CLI-only users** | Low | Low | `websockets` is an optional dependency (`esp-pylib[ide]`). CLI-only users don't install it. The `ide/ws.py` module gracefully handles `ImportError` — `send_log_message()` becomes a no-op. |
| **`inspect.stack()` performance in hot paths** | Medium | Low | `inspect.stack()` is called only on `err()`, `warn()`, and `die()` — these are infrequent error-path calls, not hot-loop operations. If profiling reveals issues, call-site capture can be made opt-in. |
| **Adoption resistance from other maintainers** | Medium | Medium | Provide clear migration guides per-repo, keep PRs small and reviewable, demonstrate value (LOC removed, files deleted). |
| **argparse→rich-click CLI behavior changes** | Medium | Medium | argparse and Click have different parsing semantics (e.g., `nargs='*'` vs `multiple=True`, subparser handling, `--` separator). Each tool's CLI test suite must cover all existing argument combinations. For tools with no CLI tests, add them before converting. Document any intentional behavior changes in the migration PR. |

---

## 7. Success Criteria

1. **Port discovery logic** exists in exactly one place — the common lib. `esptool` and `esp-idf-monitor` both import from it.
2. **No raw ANSI escape codes for diagnostic messages** remain in any consumer repo. All tool warnings, errors, and status notes go through `rich` via the common logger. (Exception: `esp-idf-monitor`'s byte-level serial data coloring retains pre-encoded `ANSI_*_B` constants locally — `rich` cannot color raw byte streams.)
3. **ROM ELF resolution** exists in exactly one place — the 37-line file in monitor and the equivalent code in coredump are both deleted.
4. **Reset sequences** (DTR/RTS primitives *and* the named pulse trains — classic, Unix-tight, USB-JTAG, hard) exist in exactly one place. Both esptool and monitor import the shared implementation. Neither tool ships its own `format_dict` + `exec()` custom-reset path anymore; both route through `execute_custom_reset`.
5. **Config file loading** exists in exactly one place. Both esptool and monitor use `ToolConfig` with their own section names.
6. **IDE integration** works across all consumer tools with zero per-tool effort: any tool that uses `EspLog` automatically sends structured diagnostics to the IDE when `ESPRESSIF_IDE_WS` is set.
7. **All consumer repos' test suites pass** after migration with zero regressions.
8. **The package is published** on PyPI with semantic versioning, changelog, and automated CI/CD.
9. **Net code reduction** across all repos is measurable (estimate: ~500-800 LOC removed from consumer repos).
10. **All tools use `rich-click`** for CLI parsing — no `argparse` remains in any consumer tool's main CLI. Consistent `--help` styling, shell completion, and reusable Click types across the ecosystem.
11. **No raw `print()` for diagnostics** remains — all error, warning, and status output goes through `EspLog`. Direct `print()` is only used for primary data output (e.g., GDB backtrace text, ELF dump) where the content is not a diagnostic message.
12. **No Python `logging` module usage** remains — all tools use `EspLog` instead of `logging.getLogger()` / `logging.warning()` / `logging.debug()`.

---

## 8. Breaking Change Audit (Consumer Compatibility)

To ensure **no breaking changes** for packages that migrate to esp-pylib, the following compatibility requirements and mitigations must be applied. External scripts, tests, and IDE extensions that depend on current public APIs or behavior must continue to work.

### 8.1 esptool — Public API surface

| Item | Current behavior | esp-pylib / plan | Mitigation |
|------|------------------|------------------|------------|
| **`get_port_list()`** | Returns `list[str]` (device paths). Signature: `get_port_list(vids=[], pids=[], names=[], serials=[])`. Exported in `esptool.__init__`. | Plan’s `get_port_list()` returns `list[ListPortInfo]`; `get_port_names()` returns `list[str]`. | **esptool must keep a wrapper:** `def get_port_list(vids=None, ...): return [p.device for p in esp_pylib.serial_ports.get_port_list(vids=vids, ...)]` so that `esptool.get_port_list()` still returns `list[str]` and existing callers (e.g. tests, `esp_rfc2217_server`) do not break. |
| **`parse_port_filters()`** | Returns `tuple[list[int], list[int], list[str], list[str]]` (vids, pids, names, serials). Used as `get_port_list(*parse_port_filters(...))`. | Plan’s `parse_port_filters()` returns `dict` with keys `vids`, `pids`, `names`, `serials`. | **Either** esp-pylib adds a return shape that can be passed as `*args` (e.g. a tuple), **or** esptool keeps a wrapper that does `f = esp_pylib.parse_port_filters(...); return (f['vids'], f['pids'], f['names'], f['serials'])` and continues to call `get_port_list(*filters)`. Prefer esptool wrapper to avoid changing esp-pylib API for other consumers. |
| **`load_config_file(verbose=False)`** | Returns `(cfg: ConfigParser, cfg_file_path: Optional[str])`. Callers use `cfg, _ = load_config_file()` and `cfg["esptool"]`. | Plan’s `ToolConfig.load()` returns only `ConfigParser`; path is not returned. | **ToolConfig** should support returning the path (e.g. `load()` returns `(parser, path)` or expose `last_found_path` after `find()`), **or** esptool implements `def load_config_file(verbose=False): c = ToolConfig(...); path = c.find(); return c.load(), path` (and ensure `load()` does not re-search if path already known, or ToolConfig caches `find()` result). Prefer extending ToolConfig so one call gives both. |
| **`load_config_file` search path (Windows)** | esptool uses `~/.config/esptool` on POSIX and `%USERPROFILE%\AppData\Local\esptool\` on Windows. | Plan’s ToolConfig uses `Path.home() / '.config' / section_name` on all platforms. | **Breaking for Windows:** Config in `AppData\Local\esptool\` would no longer be found. **Mitigation:** ToolConfig must support OS-specific search dirs (e.g. on Windows add `Path.home() / 'AppData' / 'Local' / section_name` or make search dirs configurable per tool). |
| **`load_config_file` config filenames** | esptool searches `("esptool.cfg", "setup.cfg", "tox.ini")` in each directory. | Plan allows `config_filenames=['esptool.cfg', ...]`. | Use `config_filenames=['esptool.cfg', 'setup.cfg', 'tox.ini']` when constructing ToolConfig for esptool. No API change. |
| **`FatalError.WithResult`** | Static method on `FatalError`; used across esptool. | FatalError in esp-pylib has no WithResult. | esptool keeps `from esp_pylib.errors import FatalError` and attaches `FatalError.WithResult = staticmethod(...)` (or a subclass that adds WithResult) so all existing `FatalError.WithResult(...)` calls remain valid. |
| **Logger method names** | esptool and espefuse use `log.warning()`, `log.error()`, `log.note()`. | EspLog has `warn()`, `err()`, `note()`. | **EspLog** should provide **aliases** `warning = warn` and `error = err` so that existing `log.warning()` / `log.error()` call sites work without change. Alternatively, EsptoolLogger (subclass) defines `warning` and `error` that delegate to `warn`/`err`. Prefer aliases on EspLog so any consumer using the same names is compatible. |

### 8.2 esp-idf-monitor — Constants and WebSocket

| Item | Current behavior | esp-pylib / plan | Mitigation |
|------|------------------|------------------|------------|
| **WebSocket wire format** | Monitor sends `{'event': 'gdb_stub', 'port': ..., 'prog': ...}`; IDE sends `{'event': 'debug_finished'}`. | Plan sends `{'type': 'event', 'event': event, **kwargs}`. | IDE extensions must accept messages that include an extra `"type": "event"` field (or only key off `"event"`). Document that IDEs should ignore unknown top-level keys. Coordinate IDE extension release so it supports both legacy and new format. |
| **WebSocket `prog` type** | coredump.py sends `'prog': self.elf_files` (may be list). | Protocol spec says `prog` is "Path to the ELF file" (string). | When migrating, pass the first ELF path as string, e.g. `send_event('coredump', file=..., prog=self.elf_files[0] if isinstance(self.elf_files, list) else self.elf_files)`. |

### 8.3 esp-coredump

| Item | Current behavior | esp-pylib / plan | Mitigation |
|------|------------------|------------------|------------|
| **FatalError base** | coredump’s `FatalError` in tools.py inherits from `Exception`. | esp-pylib `FatalError` subclasses `RuntimeError`. | `RuntimeError` is a subclass of `Exception`, so `except Exception` still catches it. No change needed for exception handling. Keep `ESPCoreDumpLoaderError(FatalError)` extending esp_pylib’s FatalError. |

### 8.4 Config loader (ToolConfig) — Cross-cutting

| Item | Requirement | Mitigation |
|------|-------------|------------|
| **Return value** | esptool needs `(ConfigParser, path_or_None)` from a single logical “load” call. | Extend ToolConfig: e.g. `load()` returns `(parser, path)` where `path` is the result of `find()`, or add `get_path()` that returns the path used by the last `load()`. |
| **Windows search path** | esptool (and any tool using AppData on Windows) must find config in `AppData\Local\<tool>\`. | ToolConfig should take optional `search_dirs` or detect OS and add `Path.home() / 'AppData' / 'Local' / section_name` on Windows. |
| **Repeated get()** | If tools call `config.get(key)` multiple times, avoid re-reading the file every time. | Cache the ConfigParser (and path) after first `load()` so subsequent `get()`/`load()` use the cached result unless the API explicitly offers “reload”. |

### 8.5 Summary of required plan/implementation updates

1. **esp-pylib `log.py`:** (See also **Logging requirements alignment** in Section 4.3.) Implement: `warning`/`error` aliases; **note → stdout** with **"Note: "** prefix; **print(..., file=...)** with stream at call time; **set_verbosity("auto"|"verbose"|"silent"|"compact")**; **`EspLogBase` ABC** for pluggable custom loggers + **`set_logger(instance)`** for custom integrations and tests; **no duplicate ERROR:/WARNING: prefix** when message already has it (FatalError / idf.py). Progress bar and stage remain **esptool-only** (EsptoolLogger subclass). idf.py-specific features (async tee, ANSI strip, progression line) are out of scope for esp-pylib.
2. **esp-pylib `config.py` (ToolConfig):**
   - Return path together with parser (e.g. `load()` → `(ConfigParser, Optional[Path])`).
   - Support Windows: include `Path.home() / 'AppData' / 'Local' / section_name` in search dirs on Windows.
   - Cache result of `find()`/`load()` so repeated `get()` does not re-read the file.
3. **esptool migration:** Keep **compatibility wrappers** in esptool:
   - `get_port_list(...)` → call esp_pylib and return `[p.device for p in ...]`.
   - `parse_port_filters(...)` → call esp_pylib and return `(result['vids'], result['pids'], result['names'], result['serials'])`.
   - `load_config_file(verbose=False)` → use ToolConfig and return `(parser, path)`; preserve verbose behavior (e.g. log when config loaded).
4. **IDE WebSocket:** Document or implement backward compatibility for message format (IDE ignores `type` or supports both shapes).

---

## 9. Per-Tool Audit

Comprehensive inventory of exceptions, prints, logging, `sys.exit`, CLI arguments, and CLI framework for each consumer tool. This section serves as the migration checklist — every item must be addressed (migrated, kept locally, or explicitly excluded) during the Phase 5 PRs.

### 9.1 `esptool` / `espefuse` / `espsecure`

#### Exceptions

| File | Class / Pattern | Action |
|------|----------------|--------|
| `esptool/util.py` L159 | `FatalError(RuntimeError)` | **Migrate** → `from esp_pylib.errors import FatalError` |
| `esptool/util.py` L219 | `NotImplementedInROMError(FatalError)` | Keep locally (esptool-specific) |
| `esptool/util.py` L232 | `NotSupportedError(FatalError)` | Keep locally |
| `esptool/util.py` L240 | `UnsupportedCommandError(RuntimeError)` | Keep locally |
| `espefuse/efuse/csv_table_parser.py` L262, 267 | `InputError(RuntimeError)`, `ValidationError(InputError)` | Keep locally |
| `esptool/cmds.py` | ~28 `raise FatalError(...)` | No change (uses base class) |
| `espefuse/efuse/base_operations.py` | `raise click.BadParameter(...)`, `raise click.BadOptionUsage(...)` | Keep (Click-native errors) |
| `espsecure/__init__.py` | `raise esptool.FatalError(...)`, `raise ValueError(...)` | No change |

No `sys.excepthook` usage.

#### Print statements

No raw `print()` in `esptool/`, `espefuse/`, `espsecure/` source. All output uses `log.print()` via `EsptoolLogger`. Already migrated to structured logging.

- `esptool/logger.py` L187: `self.print(formatted_message, file=sys.stderr)` — error messages to stderr.
- `espefuse/efuse/base_operations.py` L788: `log.print(line, file=file)` — writes to a file object.

#### Logging module

No Python `logging` in main source. `esp_rfc2217_server/` uses `import logging`, `logging.getLogger`, `logger.info` — **migrate to EspLog** during CLI conversion.

#### sys.exit

| File | Line(s) | Exit code | Action |
|------|---------|-----------|--------|
| `esptool/__init__.py` | 454 | `raise SystemExit("Invalid value...")` | → `log.die(msg)` |
| `esptool/__init__.py` | 1199, 1211, 1215, 1218 | `sys.exit(1)`, `sys.exit(2)` | Evaluate: error exits → `log.die()` |
| `esptool/__init__.py` | 1091 | `except SystemExit as e` (catch) | Keep |
| `espefuse/__init__.py` | 214, 243, 246 | `sys.exit(2)` | → `log.die(msg, exit_code=2)` |
| `espefuse/__init__.py` | 232 | `except SystemExit as e` (catch) | Keep |
| `espefuse/efuse/esp32*/fields.py` | various | `sys.exit(0)` (success) | Keep (clean exit) |
| `espsecure/__init__.py` | 2012, 2025 | `sys.exit(2)` | → `log.die()` |
| `espsecure/esp_hsm_sign/__init__.py` | 58, 71, 87, 133, 141, 169, 185, 195 | `sys.exit(1)` (8 calls) | → `log.die()` |

#### CLI arguments

Already `rich_click`. ~100+ `@click.option` / `@click.argument` across `esptool/__init__.py`, `espefuse/__init__.py`, `espefuse/efuse/base_operations.py`, chip-specific `operations.py`, and `espsecure/__init__.py`. No conversion needed.

`esp_rfc2217_server/__init__.py` uses `argparse` (4 arguments) — **convert to rich-click**.

#### CLI framework

| Component | Framework | Action |
|-----------|-----------|--------|
| `esptool`, `espefuse`, `espsecure` | `rich_click` | No change |
| `esp_rfc2217_server` | `argparse` | **Convert to rich-click** |

---

### 9.2 `esp-idf-monitor`

#### Exceptions

| File | Class / Pattern | Action |
|------|----------------|--------|
| `base/exceptions.py` L5 | `SerialStopException(Exception)` | Keep locally (monitor control flow) |
| `base/serial_handler.py` L227, 397 | `raise SerialStopException()` | Keep |
| `base/serial_handler.py` L377 | `raise RuntimeError('Bad command data ...')` | Keep |
| `idf_monitor.py` L226, 278, 281 | `raise NotImplementedError` | Keep (abstract methods) |
| `idf_monitor.py` L336 | `raise RuntimeError('Bad event data ...')` | Keep |
| `base/web_socket_client.py` L50, 55, 79, 99 | `raise RuntimeError(...)` | **Deleted** (file replaced by esp-pylib) |
| `base/line_matcher.py` L51, 55, 57 | `raise ValueError(...)` | Keep |
| `base/coredump.py` L53 | `raise NotImplementedError(...)` | Keep |

No `sys.excepthook` usage.

#### Print statements

| File | Line | What | Action |
|------|------|------|--------|
| `base/serial_reader.py` | 62 | `print(e)` (bare, stdout) | → `log.err(str(e))` |
| `base/output_helpers.py` | Various | `red_print`, `yellow_print`, `note_print`, `warning_print`, `error_print`, `green_print`, `normal_print`, `color_print` — all write to stderr via `sys.stderr.write()` | **Delete** all diagnostic helpers; callers → `log.err()` / `log.warn()` / `log.note()` |
| `base/output_helpers.py` | Various | `ANSI_*_B` byte constants, `AUTO_COLOR_REGEX`, `COMMON_PREFIX` | **Keep** (byte-level serial coloring) |

#### Logging module

No Python `logging` module usage. No migration needed.

#### sys.exit

| File | Line | Exit code | Action |
|------|------|-----------|--------|
| `idf_monitor.py` | 183 | `sys.exit(1)` (ELF missing) | → `log.die('ELF file not found...')` |
| `idf_monitor.py` | 419 | `sys.exit('No serial ports detected.')` | → `log.die('No serial ports detected.')` |
| `idf_monitor.py` | 427 | `sys.exit('Error: Monitor requires standard input...')` | → `log.die(msg)` |
| `base/coredump.py` | 82 | `except (Exception, SystemExit) as e` (catch) | Keep |

#### CLI framework

Currently: **argparse** only. Action: **Convert to rich-click**.

---

### 9.3 `esp-coredump`

#### Exceptions

| File | Class / Pattern | Action |
|------|----------------|--------|
| `tools.py` L9 | `FatalError(Exception)` | **Migrate** → `from esp_pylib.errors import FatalError` |
| `corefile/__init__.py` L23 | `ESPCoreDumpError(RuntimeError)` | Keep locally, optionally re-base on `FatalError` |
| `corefile/__init__.py` L27 | `ESPCoreDumpLoaderError(ESPCoreDumpError)` | Keep locally |
| `corefile/loader.py` | ~15 `raise ESPCoreDumpLoaderError(...)` | Keep |
| `corefile/loader.py` L106 | `raise SystemExit(...)` (invalid core format) | → `raise ESPCoreDumpLoaderError(...)` |
| `coredump.py` L521 | `raise SystemExit(1)` | → `log.die()` or `raise FatalError(...)` |
| `coredump.py` | `raise ValueError(...)`, `raise FileNotFoundError(...)` | Keep (standard exceptions) |

No `sys.excepthook` usage.

#### Print statements

| File | Line(s) | What | Action |
|------|---------|------|--------|
| `__main__.py` | 16 | Version banner (`print(...)`) | → `log.print(...)` |
| `coredump.py` | 141, 221, 251, 288, 301, 314 | Error/warning messages (stdout) | → `log.err()` or `log.warn()` |
| `coredump.py` | 153-154, 224 | Warning with stderr continuation | → `log.warn()` |
| `coredump.py` | 339, 342, 346, 353, 356, 361-363, 382, 386, 393, 396, 398 | Task info, GDB output, thread tables (stdout) | → `log.print()` (data output) |
| `coredump.py` | 513-520 | Box-drawing error output (`file=sys.stderr`) | → `log.err()` |
| `corefile/_parse_soc_header.py` | 48 | `print(..., file=sys.stderr)` | → `log.warn()` |

#### Logging module (16+ calls — all migrate)

| File | Line(s) | Calls | Action |
|------|---------|-------|--------|
| `__main__.py` | 7, 20-29 | `import logging`, `logging.basicConfig(level=...)` with custom debug level mapping | **Delete** — replace with `log.set_verbosity()` based on `-d` count |
| `corefile/loader.py` | 10, 366, 385-386, 463, 482, 489, 525, 532, 537, 542, 580, 583, 590, 610, 612, 622 | `import logging`, 8× `logging.warning(...)`, 3× `logging.debug(...)`, 1× `logging.error(...)`, 2× `logging.info(...)` | → `log.warn()`, `log.debug()`, `log.err()`, `log.print()` |
| `corefile/gdb.py` | 7, 54 | `import logging`, `logging.warning(...)` | → `log.warn()` |

#### sys.exit

| File | Line | Exit code | Action |
|------|------|-----------|--------|
| `coredump.py` | 142 | `sys.exit(1)` (IDF setup error) | → `log.die()` |
| `coredump.py` | 252 | `sys.exit(1)` (GDB not found) | → `log.die()` |
| `coredump.py` | 521 | `raise SystemExit(1)` (load failure) | → `log.die()` |
| `corefile/loader.py` | 106 | `raise SystemExit(...)` (invalid core) | → `raise ESPCoreDumpLoaderError(...)` |
| `corefile/_parse_soc_header.py` | 59 | `sys.exit(1)` | → `log.die()` |

#### CLI framework

Currently: **argparse** only. Action: **Convert to rich-click**.

---

### 9.4 `esp-idf-panic-decoder`

#### Exceptions

No custom exception classes. Standard exceptions only:

| File | Line | Pattern | Action |
|------|------|---------|--------|
| `gdb_panic_server.py` | 130 | `raise ValueError("Couldn't parse...")` | Keep |
| `gdb_panic_server.py` | 134 | `raise NotImplementedError(...)` | Keep |
| `gdb_panic_server.py` | 213, 232 | `raise SystemExit(0/1)` | See sys.exit section |

No `sys.excepthook` usage.

#### Print statements

| File | Line(s) | What | Action |
|------|---------|------|--------|
| `output_helpers.py` | 12-15 | `red_print()` → `sys.stderr.write()` | **Delete file** |
| `panic_output_decoder.py` | 52 | `red_print(...)` | → `log.err(...)` |
| `pc_address_decoder.py` | 156, 159, 160 | `red_print(...)` | → `log.err(...)` |

No other `print()` calls found.

#### Logging module (migrate)

| File | Line(s) | Calls | Action |
|------|---------|-------|--------|
| `gdb_panic_server.py` | 25, 166, 188, 224, 229 | `import logging`, `logging.getLogger('GdbServer')`, 3× `logger.debug(...)` | → `from esp_pylib.log import log`, `log.debug(...)` |

#### sys.exit

| File | Line | Exit code | Action |
|------|------|-----------|--------|
| `gdb_panic_server.py` | 213 | `raise SystemExit(0)` (clean exit) | Keep |
| `gdb_panic_server.py` | 232 | `raise SystemExit(1)` (error) | → `log.die(...)` |
| `gdb_panic_server.py` | 282 | `sys.exit(0)` (KeyboardInterrupt) | Keep |

#### CLI framework

Currently: **argparse** only. Action: **Convert to rich-click**.

---

### 9.5 `esp-idf-size`

#### Exceptions

| File | Class | Action |
|------|-------|--------|
| `memorymap.py` L70 | `MemMapException(Exception)` | Keep locally (tool-specific) |
| `mapfile.py` L10 | `MapFileException(Exception)` | Keep locally |
| `elf.py` L1328 | `Elf_Exception(Exception)` | Keep locally |

21 raise sites across `memorymap.py`, `mapfile.py`, `elf.py` using these exceptions. All stay local.

No `sys.excepthook` usage.

#### Print statements

| File | Line(s) | What | Action |
|------|---------|------|--------|
| `log.py` | 20, 25, 50 | Local `console_stdout.print(...)`, `console_stderr.print(...)`, `def print()` | **Delete** local `log.py`; replace with esp-pylib |
| `memorymap.py` | 25, 41 | `print(e, file=sys.stderr)` | → `log.err(str(e))` |
| `memorymap.py` | 30, 49 | `print(...)` (stdout) | → `log.print(...)` |
| `main.py` | 42 | `console.print(md)` (Rich Markdown) | → `log.print(md)` |
| `format_*.py` | Various (~15 calls) | `log.print(table)`, `log.print(tree)`, etc. | Update import to esp-pylib `log` |
| `elf.py` | 2202-2250 | `print(...)` (DWARF debug dump utility) | Keep (debug/dev utility, not user-facing) |

#### Logging module

No Python `logging` module usage. Uses Rich-based local `log.py`. No migration needed beyond replacing the local module.

#### sys.exit

| File | Line | Exit code | Action |
|------|------|-----------|--------|
| `main.py` | 280 | `sys.exit(1)` | → `log.die()` |
| `log.py` | 38 | `sys.exit(1)` (inside local `die()`) | Deleted with local `log.py` |

#### CLI framework

Currently: **argparse** only. Action: **Convert to rich-click**.

---

### 9.6 `esp-idf-sbom`

#### Exceptions

No custom exception classes. Uses `RuntimeError`, `ValueError`, `KeyError`, `schema.SchemaError`:

| File | Pattern | Action |
|------|---------|--------|
| `libsbom/utils.py` | `raise RuntimeError(err)` | Keep |
| `libsbom/spdx.py` | `raise ValueError(...)`, `raise KeyError(...)` | Keep |
| `libsbom/nvd.py` | `raise RuntimeError(...)` | Keep |
| `libsbom/mft.py` | `raise RuntimeError(...)`, `raise schema.SchemaError(...)` | Keep |

No `sys.excepthook` usage.

#### Print statements

| File | Line(s) | What | Action |
|------|---------|------|--------|
| `libsbom/log.py` | 15, 19, 29, 33, 36-37 | Local Rich-based `err()`, `warn()`, `debug()`, `die()`, `print()` | **Delete** local `log.py`; replace with esp-pylib |
| `sbom.py` | 54, 257, 268, 298, 505, 541 | `log.print(...)` | Update import to esp-pylib `log` |
| `libsbom/report.py` | ~9 calls | `log.print(...)` (Rich tables/panels) | Update import to esp-pylib `log` |

No raw `print()` calls found.

Note: `libsbom/log.py` already implements `err()`, `warn()`, `debug()`, `die()`, `print()` using Rich — very similar to `EspLog`. Migration is nearly a drop-in replacement. One difference: local `die()` calls `sys.exit(128)` — verify exit code expectations.

#### Logging module

No Python `logging` module usage. No migration needed.

#### sys.exit

| File | Line | Exit code | Action |
|------|------|-----------|--------|
| `sbom.py` | 66 | `sys.exit(f'cannot read SBOM file: {e}')` | → `log.die(f'cannot read SBOM file: {e}')` |
| `sbom.py` | 935, 940 | `sys.exit(1)` | → `log.die()` |
| `sbom.py` | 947 | `sys.exit(main())` (entry point) | Keep |
| `libsbom/log.py` | 24 | `sys.exit(128)` (inside local `die()`) | Deleted with local `log.py` |
| `__main__.py` | 9 | `sys.exit(main())` (entry point) | Keep |

#### CLI framework

Currently: **argparse** for main CLI (`sbom.py`), **click** for IDF extension (`idf_ext.py`). Action: **Convert `sbom.py` to rich-click**; `idf_ext.py` stays.

---

### 9.7 Summary Table

| Tool | Exceptions | Prints | Logging | sys.exit | CLI args | CLI framework | Key migration actions |
|------|-----------|--------|---------|----------|----------|---------------|----------------------|
| **esptool** | `FatalError` → esp-pylib; 4 local subclasses stay | All via `log.print()` already | `esp_rfc2217_server` only | ~20+ calls, migrate error exits | rich-click already | rich-click ✓ (`esp_rfc2217_server`: argparse → convert) | FatalError base, sys.exit→die, rfc2217 conversion |
| **esp-idf-monitor** | `SerialStopException` stays local | 8 diagnostic helpers → delete; 1 bare `print(e)` | None | 3 calls → `log.die()` | 24 argparse options | argparse → **rich-click** | CLI conversion, output_helpers deletion, WebSocket replacement |
| **esp-coredump** | `FatalError` → esp-pylib; `ESPCoreDumpError` stays | ~25 `print()` calls (mixed stdout/stderr) | **16+ calls** (`logging.warning/debug/error/info`) | 5 calls → `log.die()` or `raise FatalError` | 16 argparse options | argparse → **rich-click** | CLI conversion, logging replacement, print migration |
| **esp-idf-panic-decoder** | No custom classes | `red_print()` only → delete | **3 `logger.debug()` calls** | 3 calls (1 error → `log.die()`) | 3 argparse options | argparse → **rich-click** | CLI conversion, logging replacement, output_helpers deletion |
| **esp-idf-size** | 3 local exceptions stay | Local `log.py` + raw `print()` | None (uses Rich) | 2 calls | 25 argparse options | argparse → **rich-click** | CLI conversion, local log.py deletion |
| **esp-idf-sbom** | No custom classes | Local `log.py` (nearly identical to EspLog) | None (uses Rich) | 5 calls (3 migrate) | 38 argparse options + 5 subparsers | argparse → **rich-click** (idf_ext stays click) | CLI conversion, local log.py deletion |
| **clang-tidy-runner** | TBD | TBD | TBD | TBD | TBD | TBD → **rich-click** | Full audit needed during migration |
