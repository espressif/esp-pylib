# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Unified logging for all Espressif tools.
Uses rich.console.Console — no raw ANSI codes needed.
Rich automatically handles NO_COLOR, non-TTY, and Windows support.

Architecture:
  EspLogBase (ABC) — defines the interface all loggers must implement.
  EspLog     — default Rich-based implementation (singleton).
  EspLog.set_logger()  — replaces the singleton with any EspLogBase subclass.

Any consumer tool (esptool, esp-coredump, ...) or integrator can provide
a custom logger class by subclassing EspLogBase and calling set_logger().
"""

from __future__ import annotations

import contextvars
import sys
import time
from abc import ABC
from abc import abstractmethod
from contextlib import contextmanager
from typing import TYPE_CHECKING
from typing import Any
from typing import Iterator

from rich.console import Console
from rich.control import Control
from rich.control import ControlType
from rich.progress_bar import ProgressBar

from esp_pylib.ws import is_enabled as _ws_is_enabled
from esp_pylib.ws import send_log_message

if TYPE_CHECKING:
    from types import FrameType

__all__ = [
    'log',
    'EspLogBase',
    'EspLog',
    'ProgressTask',
    'Verbosity',
]

# Current progress output stream for progress_bar() / Rich (None = default stdout).
_progress_output: contextvars.ContextVar[Any | None] = contextvars.ContextVar(
    '_progress_output',
    default=None,
)

UNICODE_PROGRESS_CHAR = '━'
UNICODE_HALF_PROGRESS_CHAR = '╸'
# ASCII fallback for consoles whose encoding cannot represent the Unicode bar
# (e.g. Windows cp1252). Matches the pre-esp-pylib esptool progress bar style.
ASCII_PROGRESS_CHAR = '='
ASCII_HALF_PROGRESS_CHAR = '>'


def _progress_bar_use_ascii(console: Console) -> bool:
    """Whether to use ASCII bar glyphs — matches `ProgressBar`."""
    options = console.options
    return bool(options.legacy_windows or options.ascii_only)


def _progress_bar_chars(console: Console) -> tuple[str, str]:
    """Bar glyphs for the padded plain renderer on *console*."""
    if _progress_bar_use_ascii(console):
        return ASCII_PROGRESS_CHAR, ASCII_HALF_PROGRESS_CHAR
    return UNICODE_PROGRESS_CHAR, UNICODE_HALF_PROGRESS_CHAR


def _format_elapsed(seconds: float) -> str:
    if seconds < 60.0:
        return f'{int(seconds)}s'
    mins, secs = divmod(int(seconds), 60)
    return f'{mins}:{secs:02d}'


class ProgressTask:
    """
    Stateful progress tracker used by `EspLogBase.progress`.
    Each `update` computes a uniform prefix/suffix and calls
    `EspLogBase.progress_bar` so subclasses can override rendering.
    """

    __slots__ = ('_bar_length', '_current', '_description', '_disabled', '_logger', '_start', '_total')

    def __init__(
        self,
        logger: EspLogBase,
        total: int,
        description: str,
        bar_length: int,
        disabled: bool,
    ) -> None:
        self._logger = logger
        self._total = total
        self._current = 0
        self._description = description
        self._bar_length = bar_length
        self._disabled = disabled
        self._start = time.monotonic()

    def update(self, advance: int = 1, description: str | None = None) -> None:
        if self._disabled:
            return
        if self._total <= 0:
            return
        if description is not None:
            self._description = description
        # Clamp to [0, total]: callers may pass negative ``advance`` to rewind,
        # but the bar should never go past either bound.
        self._current = max(0, min(self._current + advance, self._total))
        # Skip the redraw when nothing observable changed (advance == 0 and no
        # new description) to avoid pointless terminal flicker.
        if advance != 0 or description is not None:
            self._emit()

    def _emit_initial(self) -> None:
        """Render the bar immediately on context entry.

        Mirrors ``rich.Progress.start()`` + ``add_task()`` which draws the bar
        before any work is done. Important when ``total == 0``: without this,
        an empty work loop would never call `update` and the bar would
        never appear.
        """
        if self._disabled:
            return
        self._emit()

    def _emit(self) -> None:
        elapsed = time.monotonic() - self._start
        time_str = _format_elapsed(elapsed)
        prefix = f'{self._description} ' if self._description else ''
        # Keep the M/N format consistent with the non-zero case ("0/0" when total == 0).
        suffix = f' {self._current}/{self._total} [{time_str}]'
        self._logger.progress_bar(
            self._current,
            self._total,
            prefix=prefix,
            suffix=suffix,
            bar_length=self._bar_length,
        )

    def _ensure_complete(self) -> None:
        if self._disabled or self._total <= 0:
            return
        if self._current < self._total:
            self._current = self._total
            self._emit()


class VerbosityMeta(type):
    """Metaclass so Verbosity['NAME'] returns the level (e.g. Verbosity['SILENT'] -> 0)."""

    def __getitem__(cls, key: str) -> int:
        try:
            return getattr(cls, key)  # type: ignore
        except AttributeError:
            raise KeyError(key) from None

    def __contains__(cls, key: str) -> bool:
        return hasattr(cls, key) and not key.startswith('_')


class Verbosity(metaclass=VerbosityMeta):
    """Verbosity levels. Levels up to 5 are reserved for future use."""

    SILENT = 0
    NORMAL = 1
    VERBOSE = 2


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
        pass

    @abstractmethod
    def err(self, message: str, suggestion: str | None = None) -> None:
        """Error message to stderr."""
        pass

    @abstractmethod
    def warn(self, message: str, suggestion: str | None = None) -> None:
        """Warning message to stderr."""
        pass

    @abstractmethod
    def note(self, message: str) -> None:
        """Informational note to stdout."""
        pass

    @abstractmethod
    def hint(self, message: str) -> None:
        """Actionable hint to stdout (e.g. how to fix a failed dependency solve)."""
        pass

    @abstractmethod
    def debug(self, message: str) -> None:
        """Debug message (shown only in verbose mode)."""
        pass

    def die(self, message: str, exit_code: int = 1, suggestion: str | None = None) -> None:
        """Print error and exit."""
        self.err(message, suggestion)
        sys.exit(exit_code)

    def stage(self, finish: bool = False) -> None:
        """Start or finish a collapsible output stage (no-op on `EspLogBase`)."""
        pass

    @abstractmethod
    def set_verbosity(self, mode: int | str) -> None:
        """Set verbosity to Verbosity or convert string to Verbosity."""
        pass

    @abstractmethod
    def progress_bar(
        self,
        cur_iter: int,
        total_iters: int,
        prefix: str = '',
        suffix: str = '',
        bar_length: int = 30,
    ) -> None:
        """Print a progress bar that overwrites itself in place."""
        pass

    @contextmanager
    def progress(
        self,
        total: int,
        description: str = '',
        bar_length: int = 30,
        *,
        file: Any = None,
        disable: bool = False,
    ) -> Iterator[ProgressTask]:
        """
        Context manager that yields a `ProgressTask`.

        Each `ProgressTask.update` builds a uniform prefix/suffix (including
        elapsed time and M/N) and calls `progress_bar` so tool-specific
        subclasses keep a single rendering hook.

        :param file: Output stream for the bar (default: stdout). Use ``sys.stderr``
            when stdout must stay clean (e.g. SPDX on stdout).
        :param disable: If True, `ProgressTask.update` is a no-op (e.g. ``--no-progress``).
        """
        task = ProgressTask(self, total, description, bar_length, disabled=disable)
        token = _progress_output.set(file)
        try:
            # When ``total == 0`` the body's loop won't iterate, so `update`
            # would never run and the user would see no bar at all. Render the
            # initial state here so the "0/0" state is still visible — this
            # matches the behaviour of ``rich.Progress`` which draws on
            # ``add_task()``. For ``total > 0`` we leave it to the first
            # ``update()`` call to keep the existing render cadence intact.
            if total <= 0:
                task._emit_initial()
            yield task
            # Only finalize the bar to 100% on a clean exit; otherwise an
            # exception in the body would jump the bar to "done" right before
            # the traceback, which is misleading.
            task._ensure_complete()
        finally:
            _progress_output.reset(token)


class EspLog(EspLogBase):
    """
    Singleton logger for Espressif tools.

    Rich markup: the output methods (``print``, ``debug``, ``note``, ``hint``,
    ``warn``, ``err``) render the message as Rich markup and do **not** escape
    it, so callers can style parts of the text (e.g.
    ``log.note('Wrote [bold]flash[/bold]')``). Callers passing dynamic/untrusted
    text that may contain ``[`` / ``]`` (paths, identifiers, regexes) must escape
    it themselves via `rich.markup.escape`.

    Subclassing note: tools such as esptool extend ``EspLog`` with extra helpers
    while keeping ``EspLogBase`` compatibility. Inherited class attributes are
    shared: if ``__new__`` used ``cls.instance is None``, a subclass would read
    the parent's ``instance`` (already set by ``EspLog()`` / ``log = EspLog()``)
    and return a base ``EspLog`` instead of constructing the subclass. We therefore
    test ``cls.__dict__.get('instance')`` so each class only reuses an instance
    stored on that exact class—subclasses get their own singleton.
    """

    instance: EspLogBase | None = None
    _verbosity: int = Verbosity.NORMAL
    _initialized: bool = False
    _stdout: Console
    _stderr: Console
    _stage_active: bool = False
    _stage_newline_count: int = 0
    _stage_kept_lines: list[tuple[Any | None, str]]
    # In-progress `progress_bar` redraws on stdout without a trailing
    # newline; `_stage_erase_stdout` clears that line separately.
    _stage_progress_visible: bool = False

    def __new__(cls, *args, **kwargs):
        if cls.__dict__.get('instance') is None:
            cls.instance = super().__new__(cls)
        return cls.instance

    def __init__(self, no_color: bool | None = None):
        if not self._initialized:
            self.no_color = no_color
            # Setting emoji to False to avoid interpreting e.g. mac addresses as emojis (":CD:" -> 💿)
            # Unicode characters can be used as emojis, e.g. ✅
            self._stderr = Console(file=sys.stderr, no_color=no_color, highlight=False, emoji=False)
            self._stdout = Console(file=sys.stdout, no_color=no_color, highlight=False, emoji=False)
            self._stage_active = False
            self._stage_newline_count = 0
            self._stage_kept_lines = []
            self._stage_progress_visible = False
            self._initialized = True

    @property
    def stdout(self) -> Console:
        """Return the Console bound to the live sys.stdout."""
        return self._live_console(self._stdout, sys.stdout)

    @property
    def stderr(self) -> Console:
        """Return the Console bound to the live sys.stderr."""
        return self._live_console(self._stderr, sys.stderr)

    def _stage_reset(self) -> None:
        self._stage_active = False
        self._stage_newline_count = 0
        self._stage_kept_lines.clear()
        self._stage_progress_visible = False

    def _stage_can_collapse(self) -> bool:
        """Stages are collapsible only when verbosity is NORMAL and stdout is an interactive terminal."""
        return self._verbosity == Verbosity.NORMAL and self.stdout.is_terminal

    def _stage_track_newlines(self, *args: Any, **kwargs: Any) -> None:
        # Counts only the newlines we emit ourselves. If the terminal soft-wraps
        # a long line onto multiple rows, the wrapped rows are not counted;
        # fixing it would require querying the live terminal width
        # on every print, which is more complexity than the use case warrants.
        if not self._stage_active:
            return
        message = ''.join(str(a) for a in args)
        self._stage_newline_count += message.count('\n')
        if kwargs.get('end', '\n') == '\n':
            self._stage_newline_count += 1

    def _stage_erase_stdout(self) -> None:
        if self._stage_progress_visible:
            # The cursor sits at the end of the bar text on the *current* row
            # (the bar was redrawn with ``\r`` + erase and no trailing ``\n``).
            # Rewind to column 0 and wipe the row in place; ``CURSOR_UP`` would
            # walk one line above the stage and corrupt unrelated output.
            self.stdout.print(
                Control(ControlType.CARRIAGE_RETURN),
                Control((ControlType.ERASE_IN_LINE, 2)),
                end='',
                markup=False,
                highlight=False,
            )
            self._stage_progress_visible = False
        if self._stage_newline_count <= 0:
            return
        controls: list[Control] = []
        for _ in range(self._stage_newline_count):
            controls.append(Control((ControlType.CURSOR_UP, 1)))
            controls.append(Control((ControlType.ERASE_IN_LINE, 2)))
        self.stdout.print(*controls, end='', markup=False, highlight=False)
        self.stdout.file.flush()

    def stage(self, finish: bool = False) -> None:
        """Start or finish a collapsible output stage.

        While a stage is active, ordinary `print` output on stdout is
        discarded when the stage finishes successfully (TTY + normal verbosity).
        `note` and `warn` are buffered and re-printed after collapse.
        In verbose mode, or on non-interactive stdout, stages are inert markers
        (output is never removed). Matches esptool's ``log.stage()`` behaviour.
        """
        if finish:
            if not self._stage_active:
                return
            self._stage_active = False
            if self._stage_can_collapse():
                self._stage_erase_stdout()
                for file, line in self._stage_kept_lines:
                    self.print(line, file=file)
            self._stage_newline_count = 0
            self._stage_kept_lines.clear()
            self._stage_progress_visible = False
        else:
            # Defensive reset: stage() should always start from a clean slate
            # so a restart-without-finish (or stray state from before any
            # stage existed) cannot bleed into this stage's erase count.
            # Any notes/warns buffered by the previous (unfinished) stage are
            # intentionally discarded
            self._stage_newline_count = 0
            self._stage_kept_lines.clear()
            self._stage_progress_visible = False
            self._stage_active = True

    @classmethod
    def _reset(cls) -> None:
        """Reset singleton to default EspLog (for testing)."""
        if cls.instance is not None and isinstance(cls.instance, EspLog):
            cls.instance._stage_reset()
        cls.instance = None
        cls._initialized = False

    @classmethod
    def set_logger(cls, instance: EspLogBase) -> None:
        """
        Replace the global logger singleton with a custom implementation.

        The instance must be an EspLogBase subclass. This allows consumer
        tools and integrators to redirect all logging output — e.g. to a
        GUI widget, log file, network sink, or test capture.

        Call _reset() to restore the default Rich-based logger.
        """
        if not isinstance(instance, EspLogBase):
            raise TypeError(f'Logger must implement the EspLogBase interface, got {type(instance).__name__!r}')
        cls.instance = instance

    def _get_call_site(self) -> tuple[str, int]:
        """Return (file, line) of the first caller outside this logger module.

        Walking the stack (rather than using a fixed index) keeps the reported
        location correct when err/warn are reached via internal helpers such as
        ``die()`` — or any future wrapper — that would otherwise appear as the
        immediate caller.
        """
        this_file = __file__
        if this_file.endswith(('.pyc', '.pyo')):
            this_file = this_file[:-1]
        frame: FrameType | None = sys._getframe(1)
        while frame is not None:
            if frame.f_code.co_filename != this_file:
                return (frame.f_code.co_filename, frame.f_lineno)
            frame = frame.f_back
        return ('<unknown>', 0)

    def set_verbosity(self, mode: int | str) -> None:
        if isinstance(mode, str):
            try:
                mode = Verbosity[mode.upper()]
            except KeyError:
                raise ValueError(f'Invalid verbosity level: {mode}')
        self._verbosity = mode

    def _live_console(self, cached: Console, stream: Any) -> Console:
        """Console for ``stream``, following reassignment of the live stream.

        ``Console`` binds its target stream once, at construction, whereas the
        builtin ``print`` resolves ``sys.stdout``/``sys.stderr`` lazily on every
        call. Return the cached console unless ``stream`` has been reassigned
        since construction (e.g. by ``contextlib.redirect_stdout`` /
        ``redirect_stderr``), in which case route through a fresh Console bound
        to the live stream so output is not captured by the stale one.
        """
        if cached.file is stream:
            return cached
        # Mirror the cached stdout/stderr consoles (highlight=False, emoji=False)
        # so redirected output renders identically to direct output.
        return Console(file=stream, no_color=self.no_color, highlight=False, emoji=False)

    def print(self, *args, **kwargs) -> None:
        """Plain output. Uses file= if provided (resolved at call time); else stdout. Suppressed when silent.
        All output using rich is flushed to the console (even without a newline).
        """
        file = kwargs.pop('file', None)
        if file is None or file is sys.stdout:
            self._stage_track_newlines(*args, **kwargs)
        if self._verbosity == Verbosity.SILENT and file is None:
            return
        if file is None or file is sys.stdout:
            console = self.stdout
        elif file is sys.stderr:
            console = self.stderr
        else:
            console = Console(file=file, no_color=self.no_color, highlight=True, emoji=False)
        console.print(*args, **kwargs)

    def debug(self, message: str) -> None:
        """Debug message (dim) to STDOUT. Only shown in verbose mode."""
        if self._verbosity == Verbosity.VERBOSE:
            self.print(f'[dim]{message}[/dim]')

    def note(self, message: str) -> None:
        """Informational note (blue) to STDOUT with 'NOTE: ' prefix."""
        if self._verbosity == Verbosity.SILENT:
            return
        formatted = f'[#0077BB]NOTE:[/#0077BB] {message}'
        if self._stage_active and self._stage_can_collapse():
            self._stage_kept_lines.append((None, formatted))
            return
        self.print(formatted)

    def hint(self, message: str) -> None:
        """Actionable hint (cyan) to STDOUT with 'HINT: ' prefix."""
        if self._verbosity != Verbosity.SILENT:
            self.print(f'[#00A0A0]HINT:[/#00A0A0] {message}')

    def warn(self, message: str, suggestion: str | None = None) -> None:
        """Warning message (yellow) to STDERR.

        Suggestions are only passed to websocket clients, not to the console.
        """
        if self._verbosity != Verbosity.SILENT:
            formatted = f'[bold yellow]WARNING:[/bold yellow] {message}'
            if self._stage_active and self._stage_can_collapse():
                self._stage_kept_lines.append((sys.stderr, formatted))
            else:
                self.print(formatted, file=sys.stderr)
        # Skip stack walking in plain CLI usage where send_log_message would no-op anyway.
        if _ws_is_enabled():
            file, line = self._get_call_site()
            send_log_message('warning', message, suggestion, file, line)

    def err(self, message: str, suggestion: str | None = None) -> None:
        """Error message (red, bold) to STDERR.

        Suggestions are only passed to websocket clients, not to the console.
        """
        self.print(f'[bold #CC3311]ERROR:[/bold #CC3311] {message}', file=sys.stderr)
        if _ws_is_enabled():
            file, line = self._get_call_site()
            send_log_message('error', message, suggestion, file, line)

    def _get_interactive_console(self) -> Console | None:
        """Return a Console for in-place overwrite, or None for non-interactive output."""
        pf = _progress_output.get()
        if pf is sys.stderr:
            if self.stderr.is_terminal:
                return self.stderr
            return None
        if pf is not None and pf is not sys.stdout:
            try:
                if hasattr(pf, 'isatty') and pf.isatty():
                    return Console(file=pf, no_color=self.no_color, highlight=False, emoji=False)
            except (AttributeError, ValueError, OSError):
                # ``isatty()`` raises ValueError on closed streams, AttributeError
                # on non-stream objects, OSError on detached fds. Treat all as
                # "not a TTY" rather than letting them crash logging.
                pass
            return None
        if self.stdout.is_terminal:
            return self.stdout
        return None

    def _get_progress_print_file(self) -> Any:
        """Stream used for progress when not using ``_stdout`` / ``_stderr`` Consoles."""
        pf = _progress_output.get()
        return sys.stdout if pf is None else pf

    def _progress_console_for_stream(self, file: Any) -> Console:
        """Console for rendering `ProgressBar` on an arbitrary stream."""
        return Console(file=file, no_color=self.no_color, highlight=False, emoji=False)

    @staticmethod
    def _render_plain_bar(
        completed: int,
        total: int,
        width: int,
        *,
        filled_char: str = UNICODE_PROGRESS_CHAR,
        half_char: str = UNICODE_HALF_PROGRESS_CHAR,
    ) -> str:
        """Render a fixed-width progress bar using *filled_char* / *half_char* and spaces.

        Used when the active console can't render a dim background bar
        (``no_color=True`` or no ``color_system``). Rich's
        `ProgressBar` only emits characters for the
        completed portion in that case, which makes the bar grow from 0 to
        ``width`` characters and shifts the suffix between redraws. Padding
        the trailing portion with spaces keeps the suffix in the same column
        on every update so only the bar fills in.
        """
        if width <= 0:
            return ''
        if total <= 0 or completed >= total:
            return filled_char * width
        completed = max(0, completed)
        # Match Rich's half-step behaviour (*half_char*) so the bar advances smoothly.
        complete_halves = int(width * 2 * completed / total)
        bar_count, half_bar_count = divmod(complete_halves, 2)
        bar_str = filled_char * bar_count + (half_char if half_bar_count else '')
        return bar_str + ' ' * (width - bar_count - half_bar_count)

    def progress_bar(
        self,
        cur_iter: int,
        total_iters: int,
        prefix: str = '',
        suffix: str = '',
        bar_length: int = 30,
    ) -> None:
        """Print progress using Rich `ProgressBar`.

        When the active console can't render a dim background bar (``no_color``
        or no ``color_system``), the bar is rendered as a fixed-width plain
        string so the suffix stays in the same column across redraws. Glyph
        selection uses the same Rich ``ascii_only`` / ``legacy_windows`` rules
        as `ProgressBar` (``=``/``>`` vs ``━``/``╸``).
        When color is available, Rich's `ProgressBar`
        handles encoding and legacy Windows rendering.
        """
        if self._verbosity == Verbosity.SILENT:
            return
        if total_iters < 0:
            return

        if total_iters == 0:
            # 0/0 means "nothing to do, already complete". Render a full bar at
            # 100% — matches ``rich.Progress``.
            percent = '100.0'
            is_complete = True
        else:
            # Defensive clamp so direct callers (bypassing ProgressTask) can't
            # render >100% or miss the final newline due to overshoot.
            cur_iter = max(0, min(cur_iter, total_iters))
            percent = f'{100 * cur_iter / total_iters:.1f}'
            is_complete = cur_iter == total_iters

        suffix_part = f' {percent:>5}%{suffix} '

        out = self._get_progress_print_file()
        interactive = self._get_interactive_console()
        # In-place redraw on an interactive console; otherwise one full line per update on ``out``.
        if interactive is not None:
            c = interactive
        else:
            c = self._progress_console_for_stream(out)

        # Pick the bar renderable: Rich's ProgressBar when the console can
        # shade the trailing portion (so the bar stays at constant width via
        # the dim background style), otherwise our fixed-width plain renderer.
        # Glyph choice for the plain path follows Rich's ``ascii_only`` /
        # ``legacy_windows`` flags (same as `ProgressBar`).
        bar_renderable: Any
        if c.no_color or c.color_system is None:
            filled_char, half_char = _progress_bar_chars(c)
            bar_renderable = self._render_plain_bar(
                cur_iter,
                total_iters,
                bar_length,
                filled_char=filled_char,
                half_char=half_char,
            )
        elif total_iters == 0:
            bar_renderable = ProgressBar(total=1.0, completed=1.0, width=bar_length)
        else:
            bar_renderable = ProgressBar(
                total=float(total_iters),
                completed=float(cur_iter),
                width=bar_length,
            )

        if interactive is not None:
            end = '\n' if is_complete or self._verbosity == Verbosity.VERBOSE else ''
            if self._verbosity != Verbosity.VERBOSE:
                c.print(
                    Control(ControlType.CARRIAGE_RETURN),
                    Control((ControlType.ERASE_IN_LINE, 2)),
                    end='',
                )
        else:
            end = '\n'

        if prefix:
            c.print(prefix, end='', markup=False, highlight=False)
        c.print(bar_renderable, suffix_part, sep='', end=end, markup=False, highlight=False)
        if not end:
            c.file.flush()
            if self._stage_active and self._stage_can_collapse() and interactive is not None and c is self.stdout:
                self._stage_progress_visible = True
        elif end == '\n' and c is self.stdout and self._stage_active:
            # Mirror `_stage_track_newlines`: only count rows while a
            # stage is active, otherwise the counter leaks across stages and
            # the next ``stage(finish=True)`` over-erases.
            self._stage_newline_count += 1
            if self._stage_can_collapse():
                self._stage_progress_visible = False


class _LogProxy:
    """Proxy that always delegates to the current EspLog singleton."""

    def __getattr__(self, name):
        return getattr(EspLog.instance, name)


log: EspLogBase = _LogProxy()  # type: ignore
