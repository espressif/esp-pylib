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

Optional **serial port** helpers (port discovery, DTR/RTS reset primitives — pulls in `pyserial`):

```bash
pip install esp-pylib[serial]
```

Optional **CLI** helpers (Click parameter types — pulls in `rich-click` and `click`):

```bash
pip install esp-pylib[cli]
```

## Modules

- **`esp_pylib.constants`** — Cross-tool values shared by multiple modules: Espressif USB VID/PID, default ROM baud rate, and serial port name / exclude patterns used by port discovery.
- **`esp_pylib.errors`** — A small exception hierarchy (`FatalError` and common subclasses such as `NoSerialPortFoundError`, `ConfigError`) for consistent error handling across tools.
- **`esp_pylib.logger`** — Shared logging for Espressif Python tools: verbosity levels (`Verbosity`), the default Rich-based singleton (`log` / `EspLog`), and `EspLogBase` so you can plug in a custom implementation via `EspLog.set_logger()`. Helpers: `log.err` / `log.warn` (stderr, IDE-forwarded), `log.note` / `log.hint` (stdout; cyan `HINT:` distinct from warnings for color-vision deficiency), `log.debug` (verbose only). Also provides a progress-bar API (`log.progress(...)` context manager, the `ProgressTask` it yields, and the lower-level `log.progress_bar(...)` rendering hook).
- **`esp_pylib.config`** — `ToolConfig` finds, parses, and caches a per-tool INI config file. Search order: env-var override → cwd → OS user-config dir (`~/.config/<tool>/` on POSIX, `~/AppData/Local/<tool>/` on Windows) → home. Files that don't contain the tool's section are silently skipped during search so candidates like `setup.cfg` / `tox.ini` are safe to list. `load()` returns `(ConfigParser, Optional[Path])`; `get(key, fallback)` is a convenience for single-value lookups. Both are cached after the first call; call `reload()` to re-scan. Pure stdlib — no extras required.
- **`esp_pylib.rom`** — ROM ELF path resolution for `esp-idf-monitor` and `esp-coredump`. Reads `IDF_PATH` and `ESP_ROM_ELF_DIR` from the environment, looks up chip revision entries in `roms.json` (current and legacy ESP-IDF locations), and returns `{target}_rev{chip_rev}_rom.elf` under `ESP_ROM_ELF_DIR`. Pure stdlib — no extras required.
- **`esp_pylib.ws`** — WebSocket client for IDE integration: sends structured JSON when an IDE sets the environment variable below. Requires `pip install esp-pylib[ide]` (pulls in `websockets`; effectively a no-op on Python 3.7 — see Installation note above). The connection is created lazily on first use; if no URL is set, log helpers no-op.
- **`esp_pylib.excepthook`** — Hooks (`sys.excepthook` and `threading.excepthook`, Python 3.8+) to report uncaught exceptions to the IDE over the same WebSocket channel, then chain to the previous hooks so normal stderr behavior is unchanged. Use together with `esp-pylib[ide]`.
- **`esp_pylib.serial_ports`** — Serial port discovery, filtering, and sorting. Wraps pyserial's `comports()` with Espressif-aware priority. Exposes `get_port_list`, `get_port_names`, `detect_port`, `get_port_vid_pid`, and `parse_port_filters` (for `key=value` CLI flags like `vid=0x303A`). Requires `pip install esp-pylib[serial]`.
- **`esp_pylib.serial_reset`** — DTR/RTS primitives and named reset sequences shared between `esptool` and `esp-idf-monitor`. Primitives: `set_dtr`, `set_rts`, `set_dtr_rts`. Sequences: `classic_bootloader_reset`, `unix_tight_bootloader_reset`, `usb_jtag_bootloader_reset`, `hard_reset` — each takes `flow_control=True` for adapters with always-on hardware flow control (e.g. the SiLabs CP2102C). `uses_hardware_flow_control((vid, pid))` decides that flag against the shared `HARDWARE_FLOW_CONTROL_VID_PIDS` list in `esp_pylib.constants`. Also includes a parser/executor for custom reset sequences in the `D0|R1|U1,0|W0.1` format. Requires `pip install esp-pylib[serial]`.
- **`esp_pylib.cli_types`** — Reusable Click `ParamType`s: `SerialPortType`, `AnyIntType`, `AutoSizeType`, `BaudRateType`, and `arg_auto_int()`. Requires `pip install esp-pylib[cli]`.
- **`esp_pylib.cli_options`** — Reusable Click pieces: `EspRichGroup` (root group for subcommand CLIs using `OptionEatAll`), `MutuallyExclusiveOption` (argparse-style exclusive groups), and `OptionEatAll` (consume values until the next flag or subcommand). Requires `pip install esp-pylib[cli]`.

### IDE integration (WebSocket)

Espressif IDEs can launch tools with a WebSocket URL so errors, warnings, and exceptions carry **file**, **line**, and optional **suggestion** text (e.g. full tracebacks) for click-to-navigate in the UI. CLI usage is unchanged when no URL is set: there is no connection and no overhead beyond reading the environment once.

#### Environment variables

| Variable | Purpose |
| -------- | ------- |
| `ESP_IDE_WS` | WebSocket URL (e.g. `ws://127.0.0.1:12345`). Set by the IDE, not by end users. |

**`esp_pylib.ws` API**

- `send_log_message(typ, message, suggestion, file, line)` — Fire-and-forget. `typ` is one of `warning`, `error`, or `exception`. Failures are ignored so a broken IDE connection cannot crash the tool.
- `send_event(event, **kwargs)` — Debug coordination (e.g. GDB stub / coredump). Sends `{"type": "event", "event": "<name>", ...}`. Raises `FatalError` if the URL is unset, `websockets` is missing, the connection cannot be established, or the send fails (each case carries a distinct message). The reserved `type` envelope key always wins over an identically-named `**kwargs` entry.
- `wait_for_event(event, retries=3)` — Blocks until a JSON message with matching `event` is received (e.g. `debug_finished` from the IDE). Raises `FatalError` if the URL is unset, `websockets` is missing, the connection cannot be established, or no matching message arrives within `retries` reconnects.
- `set_ws_url(url)` — Programmatic override for tools that expose their own flag (e.g. esp-idf-monitor's `--ws`). Pass `None` to clear the override and fall back to `ESP_IDE_WS` on next use. Closes any existing connection.
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

This reports uncaught exceptions to the IDE when `ESP_IDE_WS` is set (or `set_ws_url()` has been called). `SystemExit` and `KeyboardInterrupt` are not sent. The previous `sys.excepthook` / `threading.excepthook` handlers are always invoked afterward.

### Progress bars

Use the `log.progress(...)` context manager for in-place progress output. It yields a `ProgressTask`; call `update(advance, description=...)` to advance it. The bar overwrites itself on a TTY, falls back to one full line per update on non-TTYs / verbose mode, and is suppressed entirely under `Verbosity.SILENT`.

```python
from esp_pylib.logger import log

with log.progress(total=len(packages), description='Resolving') as bar:
    for pkg in packages:
        do_work(pkg)
        bar.update(1, description=f'Resolving {pkg.name}')
```

Optional keyword arguments:

- `file=sys.stderr` — render the bar on stderr (e.g. when stdout must stay clean for machine-readable output like SPDX).
- `disable=True` — turn the bar into a no-op (e.g. when a tool's `--no-progress` flag is set).

If the body of the `with` block raises, the bar is **not** auto-completed to 100% — you see the last real update before the traceback.

The bar is always rendered at a fixed `bar_length` so the suffix (percent, M/N, elapsed time, …) stays in the same column on every redraw. When the active console can render colors, the unfilled portion uses a dim background bar; when colors are unavailable (`NO_COLOR`, piped output, no detected color system) the unfilled portion is rendered as plain spaces and gets replaced with `━` as progress advances.

For full control over rendering, override `EspLogBase.progress_bar(cur_iter, total_iters, prefix, suffix, bar_length)` in a custom logger. `progress_bar` is **abstract**: every `EspLogBase` subclass must implement it (a no-op body is fine if the logger doesn't render bars).

### Collapsible stages

On an interactive terminal at normal verbosity, wrap noisy steps with `log.stage()` / `log.stage(finish=True)` (ported from esptool). Ordinary `log.print()` output inside the stage is erased on successful finish; `log.note()` and `log.warn()` are buffered and shown afterward. Verbose mode and non-TTY stdout disable collapsing (output is kept as printed).

```python
from esp_pylib.logger import log

log.stage()
log.print('Connecting...')
# ...
log.stage(finish=True)
```

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
        print(f"NOTE: {message}")

    def hint(self, message):
        print(f"HINT: {message}")

    def debug(self, message):
        if self._verbosity == Verbosity.VERBOSE:
            print(message)

    def set_verbosity(self, mode):
        if isinstance(mode, str):
            mode = Verbosity[mode.upper()]
        self._verbosity = mode

    def progress_bar(self, cur_iter, total_iters, prefix='', suffix='', bar_length=30):
        # Render however you like (file, GUI, ...); a no-op is fine if you
        # don't render progress.
        pass


EspLog.set_logger(MyLogger())
```

## Migration Skill for AI Coding Agents

This repository ships a tool-agnostic Agent Skill under [`./migrate-to-esp-pylib/`](./migrate-to-esp-pylib/) that walks an AI coding agent through replacing duplicated code in any Espressif Python tool (constants, `FatalError` classes, raw ANSI logging, Python `logging` calls, IDE WebSocket clients, exception hooks, INI config loaders, ROM ELF resolution, port discovery, reset sequences, argparse CLIs) with the matching `esp-pylib` module. Each step is tagged `[Available]` (perform now) or `[Planned]` (skip until the upstream module ships), so the same skill stays useful as `esp-pylib` grows.

The skill is split for progressive disclosure:

- [`migrate-to-esp-pylib/SKILL.md`](./migrate-to-esp-pylib/SKILL.md) — concise entry point: module status table, task checklist, critical rules, and links into the references.
- [`migrate-to-esp-pylib/references/workflow.md`](./migrate-to-esp-pylib/references/workflow.md) — full per-step instructions, code examples, and backward-compatibility patterns.

### Use it from Cursor

The skill is meant for **consumer-tool repos**, not for day-to-day work in this repository. Two ways to apply it:

- **Reference on demand (simplest):** in the tool repo you are migrating, `@`-mention or attach `migrate-to-esp-pylib/SKILL.md` from a local clone of esp-pylib, a submodule, or a copied `migrate-to-esp-pylib/` directory. Plain prompts that point at the file path work too.
- **Install once for global auto-invocation:** symlink the skill directory from your esp-pylib checkout into your personal skills folder so Cursor/Claude picks it up across repos and stays in sync when you pull esp-pylib (preferred over copying). Replace `<path-to-esp-pylib>` with the **absolute** path to your clone (relative targets break easily):

  ```bash
  ln -sfn <path-to-esp-pylib>/migrate-to-esp-pylib ~/.cursor/skills/migrate-to-esp-pylib
  ln -sfn <path-to-esp-pylib>/migrate-to-esp-pylib ~/.claude/skills/migrate-to-esp-pylib
  ```

  Example: `ln -sfn ~/Documents/esp-pylib/migrate-to-esp-pylib ~/.cursor/skills/migrate-to-esp-pylib`

  If the symlink is not picked up by Cursor, `@`-mentioning the skill file is the reliable fallback.

### Use it from Other AI Coding Agents

The skill is plain Markdown with YAML frontmatter in `SKILL.md`, so any coding agent that can read repository files works:

- **GitHub Copilot Chat / VS Code:** open `migrate-to-esp-pylib/SKILL.md` (or attach it to the chat) and ask the agent to follow it for the migration; the agent will pull in `references/workflow.md` as it works through the steps.
- **Claude Code and other agents:** point at `migrate-to-esp-pylib/SKILL.md` (global symlink, submodule, or copy). The root [`AGENTS.md`](./AGENTS.md) here is only for **esp-pylib contributors** keeping the skill in sync — not for running migrations in other repos.
- **Plain prompt:** paste the contents of `migrate-to-esp-pylib/SKILL.md` into the system prompt or initial message, and provide `references/workflow.md` when the agent reaches the per-step work.

### Keeping the Skill in Sync with New Features

> Required for any public-API change in `esp-pylib`. Failing to update the skill in lockstep with code is a review blocker, because stale `[Planned]` / `[Available]` markers cause agents to either skip shipped features or invent imports for unshipped ones.

When you change anything user-facing in `esp_pylib/`, update these in order — in the same PR as the code change:

1. **Code** — implement and test the change.
2. **`README.md`** — update the module summary and any code examples affected by the change.
3. **`migrate-to-esp-pylib/SKILL.md`**:
   - Flip the affected row in the **Module status** table from `Planned` to `Available` (or vice versa for a removal / deprecation).
   - Update the matching `[Planned]` / `[Available]` marker on the per-step checklist.
   - Add new exported names to the frontmatter `description` trigger keywords so the skill router still picks the file up.
4. **`migrate-to-esp-pylib/references/workflow.md`**:
   - Replace the placeholder example in the matching workflow step with a concrete, working example. Mirror the layout of the already-`Available` steps (short prose, before/after code, gotchas).
   - Bump the install pin in **Step 2** if a new minimum is required.
   - Add backward-compatibility wrapper guidance under "Backward-compatibility patterns" if the new API returns a type that differs from common consumer expectations.
5. **`CHANGELOG.md`** — do not hand-edit; `cz bump` handles it via the conventional commit message.

What counts as a "public-API change":

| Change                                                                            | Triggers skill update? |
|-----------------------------------------------------------------------------------|------------------------|
| New module, function, class, or constant exported via `__all__` or top-level      | Yes                    |
| Signature change of any exported callable                                         | Yes                    |
| Behaviour change visible to consumers (default values, error type, output stream) | Yes                    |
| New optional dependency or extras group                                           | Yes                    |
| New environment variable read by the library                                      | Yes                    |
| Internal refactor with identical public surface                                   | No                     |
| Test-only change                                                                  | No                     |
| Typo fix in docstring                                                             | No                     |

When in doubt, update the skill — the cost is small and the cost of stale agent guidance is large.

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

When adding a new feature, also update the skill at [`./migrate-to-esp-pylib/`](./migrate-to-esp-pylib/) following the checklist in [Keeping the skill in sync with new features](#keeping-the-skill-in-sync-with-new-features) above. AI coding agents should pick this up from [`AGENTS.md`](./AGENTS.md) in the repo root.

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
