# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Reusable Click parameter types for Espressif tool CLIs."""

from __future__ import annotations

from typing import TYPE_CHECKING

# rich_click wraps click and re-exports its API, giving us consistent
# ``--help`` styling. Click is imported indirectly through rich_click —
# no separate ``import click`` needed.
import rich_click as click
from click.shell_completion import CompletionItem

if TYPE_CHECKING:
    from typing import Any

    from click import Context
    from click import Parameter

__all__ = ['SerialPortType']


class SerialPortType(click.ParamType):
    """Click parameter type for serial-port arguments with shell completion.

    The ``convert()`` method intentionally returns the raw value unchanged.
    Validating that the port actually exists at parse time would break common
    workflows (passing an unplugged device path, ``/dev/ttyACM0`` on a
    container without device passthrough, …); validation is the tool's job
    when it tries to open the port.

    Shell completion is best-effort: if pyserial is not installed we silently
    return an empty list so completion-time errors don't surface to users.
    """

    name = 'serial-port'

    def convert(
        self,
        value: str,
        param: Parameter | None,
        ctx: Context | None,
    ) -> str:
        return value

    @staticmethod
    def _format_port_completion_help(port: Any) -> str:
        """Build a shell-completion help string from a pyserial ``ListPortInfo``.

        The format matches the convention shared across Espressif tools::

            "Description: <text>, VID: 0xVVVV, PID: 0xPPPP"

        Missing fields (``None`` / empty string) are silently dropped, so a
        USB device that doesn't advertise a description still shows just its
        VID/PID, and a non-USB serial port (no VID/PID metadata) shows just
        its description — or returns an empty string if nothing is known.
        """
        parts: list[str] = []
        description = getattr(port, 'description', None)
        if description:
            parts.append(f'Description: {description}')
        vid = getattr(port, 'vid', None)
        if vid is not None:
            parts.append(f'VID: 0x{vid:04X}')
        pid = getattr(port, 'pid', None)
        if pid is not None:
            parts.append(f'PID: 0x{pid:04X}')
        return ', '.join(parts)

    def shell_complete(
        self,
        ctx: Context,
        param: Parameter,
        incomplete: str,
    ) -> list[CompletionItem]:
        try:
            # Imported lazily so that loading this module never triggers a pyserial
            # import — ``[cli]`` users without the ``[serial]`` extra still get a
            # functional ``SerialPortType`` (just without completion candidates).
            from esp_pylib.serial_ports import get_port_list
        except ImportError:
            return []

        try:
            ports = get_port_list()
        except Exception:
            # Completion runs in interactive shells; never surface errors here
            # (e.g. permission issues enumerating /dev) to the user.
            return []

        incomplete_lower = incomplete.lower()
        items = []
        for port in ports:
            device = str(port.device or '')
            if device.lower().startswith(incomplete_lower):
                items.append(CompletionItem(device, help=self._format_port_completion_help(port)))
        return items
