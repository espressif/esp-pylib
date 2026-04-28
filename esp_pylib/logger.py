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

import sys
from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING
from typing import Optional
from typing import Tuple
from typing import Union

from rich.console import Console
from rich.markup import escape

from esp_pylib.ws import is_enabled as _ws_is_enabled
from esp_pylib.ws import send_log_message

if TYPE_CHECKING:
    from types import FrameType

__all__ = [
    'log',
    'EspLogBase',
    'EspLog',
    'Verbosity',
]


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
    def err(self, message: str, suggestion: Optional[str] = None) -> None:
        """Error message to stderr."""
        pass

    @abstractmethod
    def warn(self, message: str, suggestion: Optional[str] = None) -> None:
        """Warning message to stderr."""
        pass

    @abstractmethod
    def note(self, message: str) -> None:
        """Informational note to stdout."""
        pass

    @abstractmethod
    def debug(self, message: str) -> None:
        """Debug message (shown only in verbose mode)."""
        pass

    def die(self, message: str, exit_code: int = 1, suggestion: Optional[str] = None) -> None:
        """Print error and exit."""
        self.err(message, suggestion)
        sys.exit(exit_code)

    @abstractmethod
    def set_verbosity(self, mode: Union[int, str]) -> None:
        """Set verbosity to Verbosity or convert string to Verbosity."""
        pass


class EspLog(EspLogBase):
    """
    Singleton logger for Espressif tools.

    Subclassing note: tools such as esptool extend ``EspLog`` with extra helpers
    while keeping ``EspLogBase`` compatibility. Inherited class attributes are
    shared: if ``__new__`` used ``cls.instance is None``, a subclass would read
    the parent's ``instance`` (already set by ``EspLog()`` / ``log = EspLog()``)
    and return a base ``EspLog`` instead of constructing the subclass. We therefore
    test ``cls.__dict__.get('instance')`` so each class only reuses an instance
    stored on that exact class—subclasses get their own singleton.
    """

    instance: Optional[EspLogBase] = None
    _verbosity: int = Verbosity.NORMAL
    _initialized: bool = False
    _stdout: Console
    _stderr: Console

    def __new__(cls):
        if cls.__dict__.get('instance') is None:
            cls.instance = super().__new__(cls)
        return cls.instance

    def __init__(self, no_color: Optional[bool] = None):
        if not self._initialized:
            self.no_color = no_color
            # Setting emoji to False to avoid interpreting e.g. mac addresses as emojis (":CD:" -> 💿)
            # Unicode characters can be used as emojis, e.g. ✅
            self._stderr = Console(file=sys.stderr, no_color=no_color, highlight=False, emoji=False)
            self._stdout = Console(file=sys.stdout, no_color=no_color, highlight=False, emoji=False)
            self._initialized = True

    @classmethod
    def _reset(cls) -> None:
        """Reset singleton to default EspLog (for testing)."""
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

    def _get_call_site(self) -> Tuple[str, int]:
        """Return (file, line) of the first caller outside this logger module.

        Walking the stack (rather than using a fixed index) keeps the reported
        location correct when err/warn are reached via internal helpers such as
        ``die()`` — or any future wrapper — that would otherwise appear as the
        immediate caller.
        """
        this_file = __file__
        if this_file.endswith(('.pyc', '.pyo')):
            this_file = this_file[:-1]
        frame: Optional[FrameType] = sys._getframe(1)
        while frame is not None:
            if frame.f_code.co_filename != this_file:
                return (frame.f_code.co_filename, frame.f_lineno)
            frame = frame.f_back
        return ('<unknown>', 0)

    def set_verbosity(self, mode: Union[int, str]) -> None:
        if isinstance(mode, str):
            try:
                mode = Verbosity[mode.upper()]
            except KeyError:
                raise ValueError(f'Invalid verbosity level: {mode}')
        self._verbosity = mode

    def print(self, *args, **kwargs) -> None:
        """Plain output. Uses file= if provided (resolved at call time); else stdout. Suppressed when silent."""
        file = kwargs.pop('file', None)
        if self._verbosity == Verbosity.SILENT and file is None:
            return
        if file is None:
            console = self._stdout
        elif file == sys.stderr:
            console = self._stderr
        else:
            console = Console(file=file, no_color=self.no_color, highlight=True, emoji=False)
        console.print(*args, **kwargs)

    def debug(self, message: str) -> None:
        """Debug message. Only shown in verbose mode."""
        if self._verbosity == Verbosity.VERBOSE:
            self.print(f'[dim]{escape(message)}[/dim]')

    def note(self, message: str) -> None:
        """Informational note (blue) to STDOUT with 'Note: ' prefix."""
        if self._verbosity != Verbosity.SILENT:
            self.print(f'[#0077BB]Note:[/#0077BB] {message}')

    def warn(self, message: str, suggestion: Optional[str] = None) -> None:
        """Warning message (yellow) to STDERR.

        Suggestions are only passed to websocket clients, not to the console.
        """
        if self._verbosity != Verbosity.SILENT:
            self.print(f'[bold yellow]WARNING:[/bold yellow] {message}', file=sys.stderr)
        # Skip stack walking in plain CLI usage where send_log_message would no-op anyway.
        if _ws_is_enabled():
            file, line = self._get_call_site()
            send_log_message('warning', message, suggestion, file, line)

    def err(self, message: str, suggestion: Optional[str] = None) -> None:
        """Error message (red, bold) to STDERR.

        Suggestions are only passed to websocket clients, not to the console.
        """
        self.print(f'[bold #CC3311]ERROR:[/bold #CC3311] {message}', file=sys.stderr)
        if _ws_is_enabled():
            file, line = self._get_call_site()
            send_log_message('error', message, suggestion, file, line)


class _LogProxy:
    """Proxy that always delegates to the current EspLog singleton."""

    def __getattr__(self, name):
        return getattr(EspLog.instance, name)


log: EspLogBase = _LogProxy()  # type: ignore
