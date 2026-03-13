# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
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
