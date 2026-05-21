---
name: migrate-to-esp-pylib
description: Migrates Espressif Python tools to the shared esp-pylib library. Use when the user explicitly asks to migrate to esp-pylib, replace duplicated code (FatalError, logging, progress bars, IDE WebSocket, INI config, serial port discovery, DTR/RTS reset primitives, named reset sequences, Click serial-port types), convert argparse CLIs to rich-click, or remove dependencies superseded by an esp_pylib.* module.
---

# Migrate a Tool to esp-pylib

`esp-pylib` ships incrementally. The module status table below shows what is implemented today; skip steps marked `[Planned]` until they flip to `[Available]`. For per-parameter semantics, platform quirks, and edge cases, **read the relevant module's docstrings during migration** rather than relying on this skill — it intentionally stays at the workflow level.

## Module status

| Module                   | Status    | Replaces                                                                                                        |
|--------------------------|-----------|-----------------------------------------------------------------------------------------------------------------|
| `esp_pylib.constants`    | Available | Duplicated VID/PID, baud, port name patterns, macOS exclude list, hardware-flow-control adapter list            |
| `esp_pylib.errors`       | Available | Duplicated `FatalError` classes, plus the recoverable `PortVidPidNotFoundError`                                 |
| `esp_pylib.logger`       | Available | Raw ANSI helpers, local `log.py` modules, Python `logging` usage, ad-hoc progress-bar printers                  |
| `esp_pylib.ws`           | Available | Tool-local WebSocket clients + structured diagnostics                                                           |
| `esp_pylib.excepthook`   | Available | Uncaught-exception reporting (no prior equivalent)                                                              |
| `esp_pylib.config`       | Available | Duplicated INI config file loaders                                                                              |
| `esp_pylib.serial_ports` | Available | Duplicated port discovery / filtering / sorting + USB VID/PID lookup for a device path                          |
| `esp_pylib.serial_reset` | Available | Duplicated DTR/RTS primitives, named reset sequences, hardware-flow-control reset paths, custom-sequence parser |
| `esp_pylib.cli_types`    | Available | Duplicated Click `SerialPortType` (port arg + shell completion)                                                 |
| `esp_pylib.rom`          | Planned   | Duplicated ROM ELF resolution                                                                                   |
| `esp_pylib.cli_options`  | Planned   | Duplicated CLI option decorators                                                                                |

`esp_pylib.serial_reset` ships the low-level pin primitives, the four named reset sequences shared between `esptool` and `esp-idf-monitor` (each with an opt-in `flow_control=True` mode for hardware-flow-control adapters), and the custom-sequence parser/executor. The *strategy-selection* layer above the sequences (which sequence to run for a given chip + connection mode, retry orchestration, `--before` / `--after` plumbing) stays in each tool — see [Step 10](references/workflow.md#step-10-replace-reset-primitives--sequences).

## Migration workflow

One PR per consumer repo. Skip `[Planned]` steps.

Copy this checklist and track progress. After Step 1, open **[references/workflow.md](references/workflow.md)** and follow only the sections for steps marked `[Available]` or `[Partial]` above.

```text
Task Progress:
- [ ] Step 1: Audit — identify what to migrate
- [ ] Step 2: Add esp-pylib dependency
- [ ] Step 3: Replace constants                         [Available]
- [ ] Step 4: Replace error classes                     [Available]
- [ ] Step 5: Replace logging / output (incl. progress) [Available]
- [ ] Step 6: Wire up IDE WebSocket + exception hooks   [Available]
- [ ] Step 7: Replace config loader                     [Available]
- [ ] Step 8: Replace ROM ELF resolution                [Planned]
- [ ] Step 9: Replace serial port logic                 [Available]
- [ ] Step 10: Replace reset primitives + sequences     [Available]
- [ ] Step 11: Replace local WebSocket client           [Available]
- [ ] Step 12: Convert CLI to rich-click                [Partial — argparse→rich-click required; shared types partial]
- [ ] Step 13: Migrate sys.exit calls
- [ ] Step 14: Delete redundant files
- [ ] Step 15: Run tests and verify
- [ ] Step 16: Write a migration report for the reviewer
```

| Step | Detail |
|------|--------|
| 1 | [Audit](references/workflow.md#step-1-audit) |
| 2 | [Add dependency](references/workflow.md#step-2-add-dependency) |
| 3 | [Constants](references/workflow.md#step-3-replace-constants) |
| 4 | [Errors](references/workflow.md#step-4-replace-error-classes) |
| 5 | [Logging / output](references/workflow.md#step-5-replace-logging--output) |
| 6 | [IDE WebSocket + excepthook](references/workflow.md#step-6-wire-up-ide-websocket--exception-hooks) |
| 7 | [Config loader](references/workflow.md#step-7-replace-config-loader) |
| 8 | [ROM ELF — Planned](references/workflow.md#step-8-replace-rom-elf-resolution--planned) |
| 9 | [Serial ports](references/workflow.md#step-9-replace-serial-port-logic) |
| 10 | [Reset sequences](references/workflow.md#step-10-replace-reset-primitives--sequences) |
| 11 | [WebSocket client](references/workflow.md#step-11-replace-local-websocket-client) |
| 12 | [CLI — Partial](references/workflow.md#step-12-convert-cli-to-rich-click--partial) |
| 13 | [sys.exit](references/workflow.md#step-13-migrate-sysexit-calls) |
| 14 | [Delete redundant files](references/workflow.md#step-14-delete-redundant-files) |
| 15 | [Tests and verify](references/workflow.md#step-15-run-tests-and-verify) |
| 16 | [Migration report](references/workflow.md#step-16-write-a-migration-report-for-the-reviewer) |

Also in [workflow.md](references/workflow.md): [what stays local](references/workflow.md#what-stays-local), [backward-compatibility patterns](references/workflow.md#backward-compatibility-patterns).

## Critical rules

1. **No breaking changes** — preserve existing public APIs; wrap return shapes where types differ.
2. **Tool-specific code stays local** — see [what stays local](references/workflow.md#what-stays-local).
3. **`esp-pylib` never imports consumer tools** — the dependency graph flows one way.
4. **Skip [Planned] steps** — never invent imports for unshipped modules.
5. **Read module docstrings during migration** — this skill intentionally omits per-parameter semantics, platform quirks, and edge cases that live in the source.

## See also

- [`README.md`](../README.md) (repo root) — public-facing usage doc; keep aligned with this skill.
- [`references/workflow.md`](references/workflow.md) — detailed step instructions, code examples, and compatibility wrappers.
