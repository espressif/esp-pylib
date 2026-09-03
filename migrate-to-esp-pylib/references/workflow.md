# Migration workflow (detailed)

Step-by-step instructions for migrating an Espressif Python tool to `esp-pylib`. Use with [SKILL.md](../SKILL.md) for the module status table, task checklist, and critical rules. For per-parameter semantics, platform quirks, and edge cases, read the relevant `esp_pylib` module docstrings during migration.

## What stays local

The library deliberately does not own:

- Chip definitions, command opcodes, protocol tags, panic state, control characters, tool-specific env-var names, tool-specific timings (other than the shared reset delays in `esp_pylib.serial_reset`).
- Byte-level ANSI byte-stream constants for high-throughput serial-data coloring (Rich operates on `str`, not bytes).
- Reset *strategy selection* (which sequence to run for a given chip + connection mode), retry orchestration, `--before` / `--after` flag plumbing, per-chip `chip_config` tables, tool-specific state coupling (resuming a paused monitor, clearing a stub flag).
- Tool-specific port-selection heuristics that aren't expressible via `parse_port_filters`.

### Step 1: Audit

Inventory candidates for migration. Look for:

- Inline VID/PID literals (`0x303A`, `0x1001`), baud defaults, macOS port blacklists, hardware-flow-control adapter lists → Step 3.
- Local `class FatalError(Exception | RuntimeError)` definitions → Step 4.
- Raw ANSI escape codes (`\033[…m`), `red_print` / `yellow_print` / `note_print` helpers, direct `rich.console.Console()` use, `import logging`, hand-rolled `print(..., file=sys.stderr)`, ad-hoc progress printers → Step 5.
- Local WebSocket clients → Step 11.
- Local INI config loader → Step 7.
- Module-level ``IDF_PATH`` / ``ESP_ROM_ELF_DIR`` / ``ROMS_JSON`` constants and a local ``get_rom_elf_path()`` → Step 8.
- Local serial port enumeration → Step 9.
- Inline `PIN_LOW` / `PIN_HIGH`, hard-coded reset delays, local `TIOCM*` fallbacks, local copies of `classic_bootloader_reset` / `unix_tight_bootloader_reset` / `usb_jtag_bootloader_reset` / `hard_reset`, per-adapter `flow_control` flags → Step 10.
- `argparse` (`ArgumentParser`, `add_argument`, subparsers) or duplicated local Click helpers (`SerialPortType`, `AnyIntType`, `AutoSizeType`, `BaudRateType`, `arg_auto_int`, `MutuallyExclusiveOption`, `OptionEatAll`) → Step 12 (framework conversion + shared `cli_types` / `cli_options`).
- Tool-specific public APIs that external consumers depend on — these need backward-compat wrappers (see [§ Backward-compatibility patterns](#backward-compatibility-patterns)).

### Step 2: Add dependency

In `pyproject.toml` (or `setup.py`) add `esp-pylib` with the smallest extras set matching the steps performed. Before committing, look up the current version on PyPI (`pip index versions esp-pylib`, or `https://pypi.org/project/esp-pylib/`) and substitute it for the `X.Y.Z` shown below — do **not** leave `X.Y.Z` literally in `pyproject.toml` or `setup.py`.

```toml
"esp-pylib>=X.Y.Z"            # logger / errors / constants / config (pure stdlib)
"esp-pylib[ide]>=X.Y.Z"       # + websockets (Step 6, Step 11)
"esp-pylib[serial]>=X.Y.Z"    # + pyserial   (Step 9, Step 10)
"esp-pylib[cli]>=X.Y.Z"       # + rich-click + click (Step 12 cli_types + cli_options)
```

Extras combine: `esp-pylib[ide,serial,cli]>=X.Y.Z`. Bump the pin again whenever a `[Planned]` row flips to `[Available]` and the tool starts depending on the new module.

**Direct vs transitive dependencies:** Installing `esp-pylib` (and its extras) pulls in `rich`, `pyserial`, `rich-click`, `click`, and `websockets` transitively — do **not** rely on that alone. Keep (or add) a **direct** dependency for every third-party package the tool still **imports**, even when the same package is already pulled in via an `esp-pylib` extra. Imports may not match PyPI package names (e.g. `import rich_click` → `rich-click`, `import serial` → `pyserial`). Remove a direct dep only when nothing in the repo imports it anymore (e.g. drop `websocket-client` after Step 11). Pin versions on direct deps when the tool has special compatibility requirements.

### Step 3: Replace constants

```python
from esp_pylib.constants import (
    ESPRESSIF_VID,                  # 0x303A
    USB_JTAG_SERIAL_PID,            # 0x1001
    ESP_ROM_BAUD,                   # 115200
    HARDWARE_FLOW_CONTROL_VID_PIDS, # adapters whose CTS is tied to chip-RTS
    MACOS_PORT_EXCLUDE_LIST,
    LINUX_DEVICE_PATTERNS,
    MACOS_DEVICE_PATTERNS,
)
```

Reset-related constants (`PIN_LOW`, `PIN_HIGH`, `DEFAULT_RESET_DELAY`, `MINIMAL_EN_LOW_DELAY`) live in `esp_pylib.serial_reset` next to the primitives that use them — import them from there. Prefer the named `PIN_LOW` / `PIN_HIGH` constants over bare booleans at call sites. The raw `TIOCM*` symbols are also exported for tools doing their own `ioctl`, but they are `None` on Windows and on POSIX builds whose `termios` lacks them — prefer the `set_dtr_rts` helper, which already handles those fallbacks.

`HARDWARE_FLOW_CONTROL_VID_PIDS` is the single source of truth for the hardware-flow-control quirk that drives the `flow_control=True` reset paths in Step 10. Don't maintain a parallel local list — add entries here when a new adapter family shows up. `esp_pylib.serial_reset.uses_hardware_flow_control((vid, pid))` does the membership check.

### Step 4: Replace error classes

```python
from esp_pylib.errors import (
    FatalError,
    NoSerialPortFoundError,
    PortVidPidNotFoundError,  # LookupError, NOT a FatalError — catch locally
    ConfigError,
)
```

`PortVidPidNotFoundError` (raised by `get_port_vid_pid`, Step 9) is a `LookupError` — failing to identify the adapter is a *recoverable* condition, the caller is expected to fall back to the standard reset path. Catch it locally; do **not** add it to a top-level `except FatalError` exit handler. (`except Exception` still catches it because `LookupError` is a normal `Exception` subclass.)

Tool-specific error subclasses stay local but should extend `esp_pylib.errors.FatalError`:

```python
from esp_pylib.errors import FatalError

class MyToolLoaderError(FatalError):
    def __init__(self, message, extra_output=None):
        super().__init__(message)
        self.extra_output = extra_output
```

`FatalError` is a `RuntimeError`, so existing `except Exception` / `except RuntimeError` blocks keep working. If the local class had class-level attachments (e.g. a `WithResult` static method), reattach them to the imported class after import.

### Step 5: Replace logging / output

Use the `log` proxy from `esp_pylib.logger` — it always delegates to the current `EspLog` singleton, so a custom logger installed via `EspLog.set_logger(...)` is honoured automatically.

**A) Raw ANSI helpers:**

```python
# Before
from .output_helpers import red_print, yellow_print, note_print
red_print("Something failed"); yellow_print("Watch out"); note_print("FYI")

# After
from esp_pylib.logger import log
log.err("Something failed"); log.warn("Watch out"); log.note("FYI")
```

For idf.py-style build hints (`yellow_print("HINT: …")` in `idf_py_actions/tools.py`) or component-manager hints (cyan `HINT:` on stdout), use `log.hint(message)` — same `HINT:` prefix on stdout, cyan instead of yellow so hints do not collide with `log.warn` on stderr (bold yellow). Tools that suppress hints via an env flag (e.g. component manager's `NO_HINTS`) should override `hint()` on an `EspLog` subclass and call `super().hint()` when enabled.

`log.print` / `err` / `warn` / `note` / `hint` / `debug` render the message as Rich markup and do **not** escape it, so callers can style parts of the text (`log.note('Wrote [bold]flash[/bold]')`). When migrating a call whose message embeds dynamic text that may contain `[` / `]` (file paths, identifiers, regexes), wrap that text with `rich.markup.escape(...)` to avoid mis-rendering or markup parse errors.

If the tool must keep stdout reserved for machine-readable output (e.g. a tool that emits structured data such as JSON on stdout), call `log.set_info_stream(sys.stderr)` once at startup so `note` / `hint` / `debug` go to stderr alongside `err` / `warn` (pass `None` to restore the stdout default). This is a logger-level switch, so the `note` / `hint` / `debug` method signatures stay frozen — don't add a `file=` parameter to them (it would break custom loggers built from the `EspLogBase` template). The stream is captured at call time and is not updated if `sys.stderr` is later reassigned; call `set_info_stream` before any redirection.

Tools that wrap **raw bytes** with pre-encoded ANSI byte constants for serial-data coloring should keep those byte-level helpers local.

**B) Python `logging` module:**

```python
# Before                              # After
logging.warning("Bad format")    →    log.warn("Bad format")
logging.debug("Parsing...")      →    log.debug("Parsing...")
logging.error("Failed")          →    log.err("Failed")
logging.info("Status update")    →    log.print("Status update")
```

Delete `logging.basicConfig(...)` setup and any custom level-mapping helpers.

**C) Local Rich-based `log.py` modules:**

```python
# Before                              # After
from . import log                →    from esp_pylib.logger import log
log.print(table)                      log.print(table)
log.err("Failed")                     log.err("Failed")
log.die("Fatal")                      log.die("Fatal")
```

Delete the local `log.py`. If the previous `die()` used a non-1 exit code, pass `exit_code=N` explicitly — `EspLog.die()` defaults to `1`.

**D) Raw `print()` calls:**

```python
print(error_msg, file=sys.stderr)   # → log.err(error_msg)        (diagnostic — gets ERROR: prefix + IDE forward)
print(progress, file=sys.stderr)    # → log.print(progress, file=sys.stderr)  (non-diagnostic stderr)
print(info_msg)                     # → log.print(info_msg)
```

Use `log.err` only for real error diagnostics — it adds `ERROR:` and forwards to the IDE WebSocket. Reserve plain `print()` only for primary data output that is not a diagnostic (e.g. final report bytes piped to stdout, GDB backtrace text for another process).

Tools whose stdout is machine output (JSON, a report, bytes for another process) can call `log.set_console_options(...)` once at startup to set the Rich `Console`: `width` for layout (progress bars, and folding when wrap is opted in), `force_terminal` to keep colour when spawned by `idf.py`, `no_color`, `highlight` for Rich auto-highlighting, `quiet` to mute all output (rely on the return code), or `file=` to pin stdout to an `--output` deliverable (the pinned console turns `force_terminal` off, so the file stays ANSI-free even when the environment sets `FORCE_COLOR`, as e.g. the esp-idf CI does; stderr is never pinned). Progress and counters follow that pin: in-place `\r` redraws require the pin target itself to be a TTY — a process TTY on `sys.stdout` is not enough. Soft wrap defaults to **on** (`soft_wrap=True`): Rich does not insert newlines — a real terminal wraps for display, so one `log.print()` stays one logical line for captures and last-line parsers. Pass `soft_wrap=False` only if a tool explicitly wants Rich to fold long lines. Stage collapse and in-place progress require a real TTY (`isatty`) on the destination stream; `FORCE_COLOR` alone (common in esp-idf CI) colours a pipe but does **not** enable cursor-up / `\r` redraws. Only those options are configurable — any other keyword raises `TypeError`, so the shared output style can't drift.

**E) Progress bars:**

Replace ad-hoc per-tool progress printers with `log.progress(...)`, a context manager yielding a `ProgressTask`:

```python
from esp_pylib.logger import log

with log.progress(total=len(packages), description='Resolving') as bar:
    for pkg in packages:
        do_work(pkg)
        bar.update(1, description=f'Resolving {pkg.name}')
```

Useful kwargs: `file=sys.stderr` (keep stdout clean for machine output), `disable=True` (honour `--no-progress`), `bar_length=30` (column-stable suffix), `unit='B'` (humanise byte M/N with 1024-based prefixes as `1.20MB/5.00MB`). For full control over rendering, override `EspLogBase.progress_bar(cur_iter, total_iters, prefix='', suffix='', bar_length=30)` — it's `@abstractmethod` on `EspLogBase`, so a from-scratch implementation **must** define it (a `pass` body is fine). The `progress_bar` signature is unchanged from legacy esptool.

```python
with log.progress(total=size, description='Uploading', unit='B') as bar:
    bar.update(chunk_len)

# Replace tqdm unbounded counter (bar_format='{desc}: {n_fmt}')
with log.counter(description='Collecting required components') as counter:
    counter.update(1)
```

Optional: override `counter_line(prefix, suffix, final=False)` for custom counter rendering (default no-op on `EspLogBase`; `EspLog` implements it).

**F) Collapsible stages (esptool-style):**

```python
from esp_pylib.logger import log

log.stage()
log.print('Connecting...')  # erased on finish when stdout is a TTY and verbosity is normal
log.note('Chip revision 3')  # buffered, printed after finish
log.warn('Unexpected voltage')  # buffered to stderr after finish
log.stage(finish=True)
```

Collapsing is disabled in verbose mode and when stdout is not a terminal (same idea as esptool's `--verbose` / non-smart terminal). `log.stage(finish=True)` without a matching start is a no-op.

**G) Subclass pattern:**

Subclass `EspLog` only when you need to restyle progress bars or change stage behaviour; use `EspLogBase` + `EspLog.set_logger()` to redirect all output (GUI, tests, log file):

```python
from esp_pylib.logger import EspLog

class MyToolLogger(EspLog):
    def progress_bar(self, cur_iter, total_iters, prefix='', suffix='', bar_length=30): ...  # optional restyle
```

Each subclass automatically gets its own singleton slot — no need to redeclare `instance = None` / `_initialized = False`.

`warn` / `err` / `note` / `hint` / `debug` accept multiple positional arguments, rendered together like `print(*args)`. `suggestion=` (on `warn` / `err` / `die`) and `exit_code=` (on `die`) are keyword-only, so any pre-existing positional calls such as `die(msg, 2)` or `err(msg, sug)` must move to `die(msg, exit_code=2)` / `err(msg, suggestion=sug)`. The `suggestion=` text is forwarded only to the IDE WebSocket — it never appears in the terminal.

### Step 6: Wire up IDE WebSocket + exception hooks

After Step 5, IDE diagnostics work automatically (`log.warn` / `err` / `die` forward via WebSocket when `ESP_IDE_WS` is set). To also forward uncaught exceptions, add one call near the entry point:

```python
from esp_pylib.excepthook import install_exception_reporting

install_exception_reporting()
```

It chains to the previous `sys.excepthook` / `threading.excepthook`, filters `SystemExit` / `KeyboardInterrupt`, and is safe to call multiple times. The `sys.excepthook` is always installed (so chaining to a previously installed hook keeps working); the `threading.excepthook` integration is skipped on Python 3.7 because that hook only exists in 3.8+. IDE *delivery* additionally requires the `[ide]` extra (`websockets`) and `ESP_IDE_WS` to be set — without them, `send_log_message` silently no-ops while the hooks still chain normally.

### Step 7: Replace config loader

`ToolConfig` finds, parses, validates, and caches an INI-style config file (pure stdlib, no extras).

```python
from esp_pylib.config import ToolConfig

config = ToolConfig(
    section_name='mytool',
    config_filenames=['mytool.cfg', 'setup.cfg', 'tox.ini'],
    env_var='MYTOOL_CFGFILE',
    valid_options=['timeout', 'connect_attempts', 'reset_delay'],  # turns INI typos into warnings
    permissive_env_var=True,    # tool reads config at import time; bad env-var path must not crash startup
    verbose=True,               # emit "Loaded custom configuration from ..." + unknown-option warnings
    logger=mytool_log,          # optional; defaults to esp_pylib.logger.log (the global proxy)
)
parser, path = config.load()    # parser always has [mytool] section; path is None when no file found
timeout = config.get('timeout', fallback='10')
```

Search order (first match wins): env-var path (**strict by default** — missing file or wrong-section file raises `ConfigError`; pass `permissive_env_var=True` to fall through to the directory search instead), CWD, OS user-config dir (`~/.config/<section_name>/` POSIX, `~/AppData/Local/<section_name>/` Windows), home dir. Within each dir, `config_filenames` is tried in order; files lacking the tool's section are silently skipped, so listing shared filenames (`setup.cfg`, `tox.ini`) is safe.

Migration tips — match these to avoid silently downgrading the user-facing behaviour the tool already has:

- Pass `verbose=True` at CLI entry points so the "Loaded custom configuration from …" line and unknown-option warnings still appear. Leave at the default `False` for module-import-time reads where unconditional output would surprise library users (and can produce duplicate messages when the same config is re-loaded later from the CLI entry point).
- Provide `valid_options` whenever `verbose=True`; this turns silent typos in the INI file into actionable warnings.
- Set `permissive_env_var=True` only for tools that load their config during module import (so a misconfigured override env var cannot crash startup). The default `False` is intentional everywhere else — it raises `ConfigError` instead of silently falling back to the search path when the env-var override points at a missing / wrong-section file, which is what users typically want from an explicit override.
- Inject `logger=<your EspLogBase>` explicitly when the tool already owns a logger — this keeps the dependency visible at the call site instead of relying on whichever `EspLog.set_logger(...)` happened to run first at import time. Without it, the loader uses `esp_pylib.logger.log` (the global proxy that dispatches to whatever singleton is installed).
- Call `reload()` between test cases that mutate the environment / on-disk config, or after the tool itself rewrites the file — both the resolved path and the parsed `ConfigParser` are cached on the first lookup.

To preserve a tool's existing `(ConfigParser, Path)` public API, wrap `ToolConfig` rather than exposing it directly — see [§ Backward-compatibility patterns](#backward-compatibility-patterns).

### Step 8: Replace ROM ELF resolution

Delete module-level ``IDF_PATH``, ``ESP_ROM_ELF_DIR``, and ``ROMS_JSON`` constants plus any local ``get_rom_elf_path()`` implementation. Replace with:

```python
from esp_pylib.rom import get_rom_elf_path

elf = get_rom_elf_path(target, chip_rev)  # str | None
```

``get_rom_elf_path`` returns ``None`` when ``IDF_PATH`` or ``ESP_ROM_ELF_DIR`` are unset, when no ``roms.json`` is found under ``IDF_PATH``, or when no entry has ``rev <= chip_rev``. *chip_rev* and ``roms.json`` ``rev`` values use ``major * 100 + minor`` (same as ``efuse_hal_chip_revision()``); for example ``0`` is v0.0, ``101`` is v1.1, ``300`` is v3.0. It prefers an exact revision match and otherwise selects the next lower revision listed in ``roms.json`` (see [esp-rom-elfs](https://github.com/espressif/esp-rom-elfs#choosing-the-rom-elf-file)). The ELF filename pattern is ``{target}_rev{selected_rev}_rom.elf`` under ``ESP_ROM_ELF_DIR``.

``roms.json`` candidates are tried in order (unreadable files, invalid JSON, JSON
that omits *target*, or lists *target* with an empty revision array are skipped):

1. ``$IDF_PATH/components/esp_rom/roms.json`` (ESP-IDF ≥ 5.5)
2. ``$IDF_PATH/tools/idf_py_actions/roms.json`` (legacy location)

Once a file lists *target* with a non-empty revision list, that file is
authoritative — a missing *chip_rev* there does not fall back to the other path.

For tests or tooling that need the raw paths without resolving an ELF:

```python
from esp_pylib.rom import get_idf_path, get_rom_elf_dir, get_roms_json_paths
```

### Step 9: Replace serial port logic

`esp_pylib.serial_ports` requires the `[serial]` extra.

```python
from esp_pylib.serial_ports import (
    detect_port,        # str — best candidate or NoSerialPortFoundError
    get_port_list,      # list[ListPortInfo] — sorted, filtered
    get_port_names,     # list[str]          — sorted, filtered (device paths)
    get_port_vid_pid,   # (vid, pid) for a device path, or PortVidPidNotFoundError
    parse_port_filters, # parse "vid=0x303A" / "pid=..." / "name=..." / "serial=..." into kwargs
)

ports = get_port_list(vids=[0x303A])
device = detect_port(vids=[0x303A])
```

Filters: within a list, values are OR'ed; distinct lists are AND'ed. `names` / `serials` are case-insensitive substring; `vids` / `pids` are exact int matches. Sorting prioritises Espressif VID, then platform-known device patterns from `LINUX_DEVICE_PATTERNS` / `MACOS_DEVICE_PATTERNS`. Within each priority bucket, relative order follows pyserial's `comports()` enumeration so the most recently attached port tends to rank first (`detect_port` returns `ports[0]`): preserved as-is on Linux/Windows, reversed on macOS (pyserial there often lists the newest port last). This within-bucket ordering is best-effort — it depends on pyserial and OS enumeration (e.g. Linux `glob` order is not guaranteed) and may vary between runs. `MACOS_PORT_EXCLUDE_LIST` is applied automatically on macOS regardless of caller filters; other platforms are unaffected.

`parse_port_filters(...)` returns a dict with all four keys (empty lists for unspecified) so it splats directly into `get_port_list(**parse_port_filters(...))`. `vid` / `pid` use `int(value, 0)` (decimal, `0x...`, `0o...`, `0b...` all accepted).

`get_port_vid_pid(port_name)` resolves a device path to its USB `(VID, PID)` — primarily for deciding `flow_control` in Step 10. On POSIX, udev aliases under `/dev/` (e.g. `/dev/esp0` → `ttyUSB0`, including nested paths like `/dev/serial_ports/...`) are followed via `os.path.realpath` before matching against `comports()`; a stale alias whose target node is gone raises `PortVidPidNotFoundError` (disconnected device). Catch `PortVidPidNotFoundError` locally and fall back to the standard reset path; do not route it through a top-level `except FatalError` handler.

For tools whose existing public API returns plain device-path strings (not `ListPortInfo`), wrap `get_port_list(...)` — see [§ Backward-compatibility patterns](#backward-compatibility-patterns).

### Step 10: Replace reset primitives + sequences

`esp_pylib.serial_reset` (requires `[serial]` extra) ships:

1. **DTR/RTS primitives**: `set_dtr`, `set_rts`, `set_dtr_rts`.
2. **Named reset sequences** previously duplicated between `esptool/reset.py` and `esp_idf_monitor/base/reset.py`:

| Function                       | When to call it                                                                                       |
|--------------------------------|-------------------------------------------------------------------------------------------------------|
| `classic_bootloader_reset`     | Portable bootloader entry; sequential DTR/RTS writes — every platform.                                |
| `unix_tight_bootloader_reset`  | Preferred on POSIX; atomic `ioctl(TIOCMSET)`. Raises `NotImplementedError` on Windows — fall back to `classic_bootloader_reset` there. |
| `usb_jtag_bootloader_reset`    | Chips talking over the internal USB-Serial-JTAG peripheral (PID `0x1001`).                            |
| `hard_reset`                   | Bounce `EN` to restart the chip (out of bootloader or restart a running app).                         |

3. **Flow-control variants**: every named sequence accepts `flow_control=True` for adapters whose CTS is tied to chip-RTS. Derive the flag from the live VID/PID:

```python
from esp_pylib.serial_reset import (
    classic_bootloader_reset, unix_tight_bootloader_reset,
    usb_jtag_bootloader_reset, hard_reset, uses_hardware_flow_control,
)
from esp_pylib.serial_ports import get_port_vid_pid
from esp_pylib.errors import PortVidPidNotFoundError

try:
    fc = uses_hardware_flow_control(get_port_vid_pid(port.name))
except PortVidPidNotFoundError:
    fc = False
classic_bootloader_reset(port, enter_boot_delay=0.1, reset_delay=0.05, flow_control=fc)
```

Pass per-chip timings from the tool's existing config table (`chip_config['enter_boot_set']`, `chip_config['enter_boot_unset']`, `chip_config['reset']`); defaults match the historical pin-toggle delays. See module docstrings for per-parameter semantics, Windows fallbacks, and the fixed-timing behaviour of `hard_reset(flow_control=True)`.

4. **Custom reset language** (the `D|R|U|W` mini-grammar consumed by per-tool config files):

```python
from esp_pylib.serial_reset import parse_custom_reset_sequence, execute_custom_reset

execute_custom_reset(port, 'D0|R1|W0.1|D1|R0')          # parse + run in one call
steps = parse_custom_reset_sequence('D0|R1|U1,0|W0.1')  # list[dict] for custom orchestration
```

`parse_custom_reset_sequence` raises `ValueError` (not `FatalError`) on unknown commands / malformed args — wrap if the tool wants a `--help` style hint.

### Step 11: Replace local WebSocket client

```python
from esp_pylib.ws import send_event, wait_for_event, set_ws_url, is_enabled, close, ensure_connected

set_ws_url(args.ws)         # optional — pass None to fall back to ESP_IDE_WS
send_event('gdb_stub', port=port, prog=prog)
wait_for_event('debug_finished')
close()                     # on clean shutdown
```

Use `is_enabled()` to gate work on whether an IDE link is configured — it's the same cached probe `EspLog.warn` / `err` use internally. To fail fast when an IDE URL is set but unreachable (rather than degrading silently), call `ensure_connected()` once at startup — it raises `FatalError` with distinct messages for "URL unset", "websockets missing", "all retries failed".

Delete the local WebSocket client module. In `pyproject.toml`, remove any `websocket-client` dep and add `esp-pylib[ide]` (pulls `websockets`).

Wire format is `{"type": "event", "event": "<name>", ...}`. If the previous client passed list-typed values for fields the new format expects as strings (e.g. `prog`), unpack to one string.

### Step 12: Convert CLI to rich-click

Step 12 has three parts — do all that apply during a tool migration:

1. **Framework conversion (required):** every consumer-tool *main* CLI must use `rich_click`, not `argparse`.
2. **Shared types (`esp_pylib.cli_types`):** replace tool-local `ParamType` copies with the shared exports where the tool has matching options.
3. **Shared option classes (`esp_pylib.cli_options`):** replace tool-local `MutuallyExclusiveOption` / `OptionEatAll` / `EspRichGroup` copies.

#### A) Convert `argparse` → `rich_click`

Convert every entry point built with `argparse.ArgumentParser`, `add_argument`, or `add_subparsers`. Entry points already on `rich_click` need no work — but audit the whole repo, since a tool that uses rich-click for its main CLI may still ship a secondary `argparse` script.

```python
# Before (argparse)
import argparse
parser = argparse.ArgumentParser(prog='mytool')
parser.add_argument('--port', '-p', default=os.environ.get('MYTOOL_PORT'))
parser.add_argument('--quiet', '-q', action='store_true')
sub = parser.add_subparsers(dest='command')
info = sub.add_parser('info')
info.add_argument('corefile')
args = parser.parse_args()

# After (rich-click)
import os
import rich_click as click
from esp_pylib.cli_types import SerialPortType

@click.group()
@click.option('--port', '-p', type=SerialPortType(), default=lambda: os.environ.get('MYTOOL_PORT'))
@click.option('--quiet', '-q', is_flag=True, default=False)
@click.pass_context
def cli(ctx, port, quiet):
    ctx.ensure_object(dict)
    ctx.obj['port'] = port
    ctx.obj['quiet'] = quiet

@cli.command('info')
@click.argument('corefile')
@click.pass_context
def info(ctx, corefile): ...
```

Mechanical mapping cheatsheet:

| argparse | rich-click |
|----------|------------|
| `ArgumentParser(prog=…)` | `@click.group()` or `@click.command()` + `context_settings=dict(help_option_names=['-h', '--help'])` |
| `add_subparsers()` / subcommand parsers | `@group.command()` on the group |
| `action='store_true'` | `is_flag=True` |
| `action='store_false'` (or paired `--foo` / `--no-foo`) | `@click.option('--foo/--no-foo', default=True)` (idiomatic boolean pair); fallback: `is_flag=True, default=True` + invert help text |
| `action='count'` (e.g. `-d` / `--debug`) | `count=True` on the option; map levels with `log.set_verbosity()` instead of ad-hoc `logging` level tables |
| `nargs='+'` on a positional | `nargs=-1` on the argument (semantics differ — verify in tests) |
| `nargs='*'` on an **option** (values until the next flag) | `cls=OptionEatAll` from `esp_pylib.cli_options` (see § C); plain `multiple=True` is not equivalent |
| `type=int` with `0x` / `0o` / `0b` literals | `type=AnyIntType()` from `esp_pylib.cli_types` (or `arg_auto_int` in non-Click code) |
| `type` accepting `4k` / `2M` / `all` sizes | `type=AutoSizeType()` (pass `allow_all=False` when `all` must be rejected) |
| `add_mutually_exclusive_group()` | `cls=MutuallyExclusiveOption` with reciprocal `exclusive_with=[…]` (see § C) |
| `choices=[…]` | `type=click.Choice([…], case_sensitive=False)` when case-insensitive matching is required |
| Runtime entry: `args = parser.parse_args(); main(args)` | `@click.pass_context` + `ctx.obj` to thread shared state through subcommands |
| Test entry: `parser.parse_args(argv)` | Invoke the Click command via `cli.main(argv, standalone_mode=False)` (re-raises exceptions instead of `SystemExit`) |
| `parser.error(msg)` | `raise click.UsageError(msg)` |

**Subcommands:** `add_subparsers()` becomes a Click group — `@click.group()` on the root, `@group.command()` per subcommand. Parent options shared across subcommands belong on the group (use `@click.pass_context` / `ctx.obj`), not duplicated on each subcommand.

**Keep plain `click` where required:** ESP-IDF extension entry points that integrate with `idf.py` (e.g. `idf_ext.py` using `idf_component_manager` patterns) stay on `click` — only convert the tool's standalone `argparse` main CLI to `rich_click`.

**Parsing pitfalls (treat as Medium/High in Step 16):** option `nargs='*'` vs Click `multiple=True` (use `OptionEatAll` when the tool consumed tokens until the next flag), the `--` separator, optional positional arity, and subcommand-default behaviour differ between argparse and Click. For `OptionEatAll` on a group with subcommands, use `@click.group(cls=EspRichGroup)` (or subclass `EspRichGroup` and call `super().parse_args`) so subcommand names are not swallowed as option values. Run (or add) CLI tests for every flag combination the tool documents; call out intentional behaviour changes in the migration PR.

**Remove `argparse` imports:** after converting to rich-click, drop `import argparse` from migrated modules. A common leftover is rebuilding `argparse.Namespace` in Click callbacks to call legacy `main(args)` — pass explicit parameters or `ctx.obj` instead (see [Common pitfalls](#leftover-argparse-imports-after-rich-click)).

**Dependencies:** add `esp-pylib[cli]` (pulls `rich-click` + `click` transitively). Keep a direct `rich-click` dependency when the tool imports `rich_click` (often aliased as `click`); keep a direct `click` dependency for entry points that import plain `click` (e.g. ESP-IDF `idf.py` extensions).

#### B) Adopt shared Click types (`esp_pylib.cli_types`)

Requires `esp-pylib[cli]`. Replace any tool-local `ParamType` / `arg_auto_int` copy with the matching export:

| Export | Typical use |
|--------|-------------|
| `SerialPortType` | `--port` / serial device path |
| `AnyIntType` | Addresses, offsets, register values (`0x`, `0o`, `0b` literals) |
| `AutoSizeType` | Flash/read sizes with `k` / `M` suffixes; optional literal `all` |
| `BaudRateType` | `--baud` with shell completion for common rates |
| `arg_auto_int` | Non-Click parsing of the same integer literal rules |

```python
import rich_click as click
from esp_pylib.cli_types import (
    AnyIntType,
    AutoSizeType,
    BaudRateType,
    SerialPortType,
)

@click.option('--port', '-p', type=SerialPortType(), help='Serial port device')
@click.option('--baud', type=BaudRateType(), default=115200)
@click.option('--offset', type=AnyIntType())
@click.option('--size', type=AutoSizeType())
def cmd(port, baud, offset, size): ...
```

`SerialPortType` is intentionally lenient: `convert()` returns the value unchanged (no parse-time existence check — validation belongs in the open-port path). `shell_complete()` provides device-path completion backed by `get_port_list()`; the import is lazy, so tools with `[cli]` but not `[serial]` still get a functional type (completion returns empty).

`AutoSizeType(allow_all=False)` rejects the literal `all` when the tool never supported whole-device sizing. For per-parameter semantics and edge cases, read the class docstrings in `esp_pylib/cli_types.py`.

#### C) Adopt shared Click option classes (`esp_pylib.cli_options`)

Requires `esp-pylib[cli]`. Replace tool-local copies of these classes; wire each option with `cls=…`.

**Mutually exclusive flags** — mirrors `argparse.add_mutually_exclusive_group()`. List peers by Click option `name` (underscore form: `no_compress` for `--no-compress`). Declare the constraint on **both** sides of each pair:

```python
import rich_click as click
from esp_pylib.cli_options import MutuallyExclusiveOption

@click.command()
@click.option(
    '--compress',
    is_flag=True,
    cls=MutuallyExclusiveOption,
    exclusive_with=['no_compress'],
)
@click.option(
    '--no-compress',
    '-u',
    is_flag=True,
    cls=MutuallyExclusiveOption,
    exclusive_with=['compress'],
)
def cmd(compress, no_compress): ...
```

**Option `nargs='*'`** — use `OptionEatAll` so the option consumes tokens until the next flag (or, on a group with subcommands, until a known command name). Combine with `multiple=True` when the tool allowed repeating the option (`--key a.pem --key b.pem`):

```python
from esp_pylib.cli_options import OptionEatAll

@click.option('--port-filter', multiple=True, type=str, cls=OptionEatAll)
@click.option('--verbose', is_flag=True)
def cmd(port_filter, verbose): ...
# mytool --port-filter vid=0x303A name=USB --verbose
# → port_filter == ('vid=0x303A', 'name=USB')  # with multiple=True
```

Without `multiple=True`, `OptionEatAll` passes the full eaten token list to `type.convert()` once. Use that only with a custom `ParamType` that accepts `list[str]` (esptool `AddrFilenamePairType` on `--encrypt-files`). Do not pair it with `str`, `click.File`, or other built-in types.

**Groups with subcommands:** use `EspRichGroup` from `esp_pylib.cli_options` — it sets `ctx._commands_list` before parsing so eat-all options stop at subcommand names (`mytool --port-filter a=b flash` does not treat `flash` as a filter value):

```python
import rich_click as click
from esp_pylib.cli_options import EspRichGroup, OptionEatAll

@click.group(cls=EspRichGroup)
@click.option('--port-filter', multiple=True, type=str, cls=OptionEatAll)
def cli(port_filter): ...

@cli.command()
def flash(): ...
```

If the tool already subclasses `click.RichGroup` for other `parse_args` work (deprecated-flag rewriting, shared `ctx` state, …), subclass `EspRichGroup` instead and call `super().parse_args(ctx, args)` so `_commands_list` is still set — see `esptool`'s `Group` in `cli_util.py`. A plain `@click.command()` with no subcommands does **not** need `EspRichGroup`.

### Step 13: Migrate sys.exit calls

```python
sys.exit(1)                   # → log.die(error_message)
sys.exit("Error message")     # → log.die("Error message")
raise SystemExit(1)           # → log.die(error_message) or raise FatalError(...) for callers to catch

# Keep as-is
sys.exit(0)                   # clean success
sys.exit(main())              # entry point
except SystemExit as e: ...   # exception catch
```

Bare `sys.exit(1)` usually follows a `print(...)` / `log.err(...)` of the actual diagnostic on the preceding line(s). Fold that message into the `log.die(...)` call rather than inventing a placeholder — `log.die` already emits the `ERROR:` line *and* exits with status `1`, so the preceding `print` / `log.err` becomes redundant.

Inside library code prefer `raise FatalError(...)` (or a tool-specific subclass) so callers can decide whether to exit or recover; reserve `log.die()` for CLI entry points.

### Step 14: Delete redundant files

| File pattern                                                     | Replaced by                                                             |
|------------------------------------------------------------------|-------------------------------------------------------------------------|
| Local raw-ANSI helpers (`output_helpers.py`, …)                  | Step 5 (keep byte-level ANSI byte constants if present)                 |
| Local Rich-based `log.py`                                        | Step 5                                                                  |
| Local hand-rolled progress-bar printers                          | Step 5 (override `progress_bar` if rendering doesn't match)             |
| Local `class FatalError(...)`                                    | Step 4                                                                  |
| Local INI config loader                                          | Step 7                                                                  |
| Local ROM ELF getter                                             | Step 8                                                                  |
| Local serial port enumeration / sorting                          | Step 9 (keep tool-specific selection heuristics)                        |
| Local DTR/RTS primitives + named reset sequences + custom parser | Step 10 (keep strategy-selection, retry orchestration, config plumbing) |
| Local WebSocket client module                                    | Step 11                                                                 |
| `argparse` CLI modules (`argument_parser.py`, `cli_ext.py`, …)   | Step 12 A (after tests pass on rich-click CLI)                          |
| Local Click `ParamType`s (`SerialPortType`, `AnyIntType`, …)     | Step 12 B                                                               |
| Local `MutuallyExclusiveOption` / `OptionEatAll`                 | Step 12 C                                                               |

### Step 15: Run tests and verify

1. Run `pre-commit run` (ruff, ruff-format, mypy, codespell). Run this **before** the test suite — `ruff-format` will rewrite files, and you want tests to exercise the final form.
2. Run the tool's full test suite. If log-output or progress-bar assertions fail only in CI or narrow terminals, pin a wide terminal width in `conftest.py` (see [Common pitfalls § Terminal width in tests](#terminal-width-in-tests)). When fixing log-output assertions, do not depend on `ERROR:` / `WARNING:` / `NOTE:` / `HINT:` prefixes — see [§ Logger prefixes in tests](#logger-prefixes-in-tests).
3. Verify no import errors; `--help` works for the root command and every subcommand.
4. If the tool had no CLI tests before Step 12, add minimal tests for representative flag combinations (especially subcommands and `nargs`/`multiple` options) before merging the argparse removal.
5. Verify no raw ANSI codes remain in diagnostic output.
6. Verify error / warning messages still go to stderr.
7. Verify no breaking changes to public APIs (see "Backward-compatibility patterns").

### Step 16: Write a migration report for the reviewer

Produce a short report (PR description, or a sibling note linked from it) that classifies every change made in Steps 3–14 by review risk, so the reviewer knows where to focus. Use these three buckets:

- **Easy / mechanical** — 1:1 substitutions with no behaviour change: constant imports (Step 3), `FatalError` swap (Step 4), straight `red_print` / `logging.*` → `log.*` rewrites (Step 5 A–D), dependency edits (Step 2), file deletions (Step 14). Listing these as a single line per file is fine.
- **Medium / needed a wrapper or small refactor** — anywhere a public-API shape was preserved by adapting the new return type, or a subclass was introduced: `ToolConfig` behind the old loader function (Step 7), `get_port_list` returning `ListPortInfo` vs. the old device-string list (Step 9), `parse_port_filters` tuple-vs-dict reshaping (Step 9), `progress_bar` overrides or `EspLog` subclasses (Step 5 E–F), WebSocket wire-format / field-shape adjustments (Step 11), `PortVidPidNotFoundError` local catch sites (Steps 4, 9, 10), argparse→rich-click conversions where only mechanical mapping was needed (Step 12 A), drop-in `cli_types` / `cli_options` imports when behaviour already matched the shared implementation (Steps 12 B–C).
- **High / needs human verification on real hardware or in-context review** — anything touching reset orchestration, runtime behaviour, or error/exit semantics: per-chip timing tables wired into shared reset sequences (Step 10), `flow_control` derivation from live VID/PID (Step 10), Windows fallback when `unix_tight_bootloader_reset` raises (Step 10), `install_exception_reporting()` placement relative to pre-existing `sys.excepthook` / `threading.excepthook` hooks (Step 6), `sys.exit` → `log.die` / `raise FatalError` conversions that change who decides to terminate (Step 13), any custom-reset-string handling that previously raised tool-specific errors (Step 10), argparse→rich-click changes that alter subcommand defaults, positional arity, or `nargs`/`multiple` behaviour (Step 12 A — exercise every documented CLI combination), first adoption of `OptionEatAll` on a group with subcommands (confirm `EspRichGroup` / `super().parse_args` and that documented flag combinations still parse).

For each Medium / High entry, name the file(s) touched and call out what the reviewer should verify by hand — e.g. "test reset on an ESP32-S3 behind a CP210x adapter (flow_control path)" or "confirm `sentry_excepthook` still runs after `install_exception_reporting()`". Skipped `[Planned]` steps and intentionally-kept-local code (see [§ What stays local](#what-stays-local)) should also be noted so the reviewer doesn't flag them as misses.

## Common pitfalls

### Terminal width in tests

After Step 5, Rich-based helpers (`log.note`, progress bars, tables) use the detected terminal width for layout such as progress bars. EspLog defaults to `soft_wrap=True`, so a single `log.print()` / `log.note()` string is **not** split across physical lines — the terminal wraps for display. That means most substring assertions on one log line stay reliable even when pytest captures stdout as a narrow pipe.

If a test still opts into wrapping (`log.set_console_options(soft_wrap=False)`) or asserts on progress-bar column layout, set a stable width once for the whole test session — the easiest fix is `conftest.py`:

```python
import os

os.environ.setdefault('COLUMNS', '120')
```

Pick a value comfortably wider than the longest expected log line. For a single test module, `monkeypatch.setenv('COLUMNS', '120')` works too. Alternatively, call `log.set_console_options(width=120)` in a session-scoped autouse fixture when the suite already configures the logger at startup.

### Pinned stdout vs TTY progress

`log.set_console_options(file=...)` pins stdout (and default progress/counters) to that deliverable. In-place `\r` progress still requires `isatty` on **that file**, not on the process `sys.stdout`. If a tool writes an `--output` report while attached to a terminal, progress is one newline-terminated line per update in the file — use `log.progress(..., file=sys.stderr)` when the bar should stay on the live TTY instead.

### Logger prefixes in tests

After Step 5, `log.err`, `log.warn`, `log.note`, `log.hint`, and related helpers prepend labels such as `ERROR:`, `WARNING:`, `NOTE:`, and `HINT:`. The exact prefix text, stream choice, and styling are owned by `esp_pylib.logger` and are **not** part of a consumer tool's public API — do not assert on them in the tool's test suite:

```python
# Avoid — prefix/format may change with esp-pylib updates
assert "HINT: some text" in captured.stdout
assert captured.stderr.startswith("WARNING:")

# Prefer — assert on the message body the tool controls
assert "some text" in captured.stdout
# Or mock/stub EspLog and assert log.hint was called with the expected message
```

When fixing tests broken by a prefix change during migration, drop the prefix from the assertion rather than locking in pylib's formatting. Golden files and snapshot tests should likewise match on user-visible message content, not logger decoration.

### Leftover `argparse` imports after rich-click

After Step 12 A, remove `import argparse`. A common half-migration rebuilds `argparse.Namespace` in Click callbacks to feed old `main(args)` code:

```python
# Avoid
main(argparse.Namespace(port=ctx.obj['port'], baud=ctx.obj['baud'], offset=offset, size=size))

# Prefer
flash(port=ctx.obj['port'], baud=ctx.obj['baud'], offset=offset, size=size)
```

Only keep a `Namespace` shim when an external API must stay byte-for-byte compatible (document it as Medium risk in Step 16).

### What counts as a breaking change

Migrations must not break consumers that import the tool as a library, shell scripts that pass documented flags, or tests that assert on stable contracts. **Public API** means symbols other packages, IDE extensions, or documented integrations import or call — typically names in `__all__`, re-exported from the package root, or called out in user-facing docs. Private helpers starting with underscore (`_helper`, argparse-only glue) may be renamed or inlined without a compat shim.

Use this split when reviewing a PR:

| Change | Breaking? | Notes |
|--------|-----------|-------|
| Log prefix / styling unified across tools (`Notice` → `NOTE:`, `WARNING:` on stderr, cyan `HINT:`) | No | Acceptable for consistent Espressif CLI output; update golden files / snapshots — but do not assert on prefixes in tool tests (see [§ Logger prefixes in tests](#logger-prefixes-in-tests)) |
| Progress bar or stage rendering on a TTY vs pipe | No | Behaviour already depends on terminal capabilities; pin `COLUMNS` in tests |
| Default `soft_wrap=True` (Rich does not insert newlines; the terminal wraps for display) | No | Visual wrapping only — one `log.print()` stays one logical line. Pass `soft_wrap=False` to restore Rich folding |
| Renamed / removed Python function, class, or module export | Yes, **only if it was public API** | Private symbols: rename freely; public symbols: wrap or keep a deprecated alias |
| Changed function signature, return type, or raised exception type | Yes, **only if it was public API** | Private helpers: update call sites; public callables: adapters required |
| Renamed CLI flag, changed default, or different positional arity | Yes | Treat as High in Step 16 unless documented as intentional |
| Different exit code for the same failure mode | Yes | Map to the old code or call out explicitly |
| `sys.exit` → `log.die` / `raise FatalError` that changes who catches the error | Yes | Medium/High — verify callers |

When in doubt, preserve the old public surface and note cosmetic log diffs in the migration report.

## Backward-compatibility patterns

The shared library returns canonical types (e.g. `list[ListPortInfo]`, `(ConfigParser, Path)`) that may differ from a tool's existing public API. Wrap the new return shape in the tool's existing function to avoid breaking external consumers (other tools, tests, IDE extensions).

```python
# Tool's public API kept unchanged — translates ListPortInfo → device-string.
from esp_pylib.serial_ports import get_port_list as _pylib_get_port_list
from esp_pylib.serial_ports import parse_port_filters as _pylib_parse_port_filters

def get_port_list(vids=None, pids=None, names=None, serials=None):
    return [p.device for p in _pylib_get_port_list(
        vids=vids, pids=pids, names=names, serials=serials,
    )]

def parse_port_filters(values):
    # Previous return shape was a 4-tuple; the shared helper returns a dict.
    f = _pylib_parse_port_filters(values)
    return f['vids'], f['pids'], f['names'], f['serials']

# Tool's public API kept unchanged — hides the ToolConfig instance behind the old function name.
from esp_pylib.config import ToolConfig

_CONFIG = ToolConfig(
    section_name='mytool',
    config_filenames=['mytool.cfg', 'setup.cfg', 'tox.ini'],
    env_var='MYTOOL_CFGFILE',
)

def load_config_file(verbose=False):
    return _CONFIG.load()  # (ConfigParser, Optional[Path]) — same shape as before
```

Generic pre-merge checks:

- `except Exception` still catches the new `FatalError` (`RuntimeError` → `Exception`).
- Any `log.warning()` / `log.error()` aliases used externally still resolve (provide them on tool subclasses if needed).
- `install_exception_reporting()` chains correctly; previous hooks still run.
- IDE WebSocket consumers accept the new `{"type": "event", ...}` envelope.
