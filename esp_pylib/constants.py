# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os

__all__ = [
    'USB_JTAG_SERIAL_PID',
    'ESPRESSIF_VID',
    'ESP_ROM_BAUD',
    'MACOS_PORT_EXCLUDE_LIST',
    'LINUX_DEVICE_PATTERNS',
    'MACOS_DEVICE_PATTERNS',
]

# --- Hardware identifiers ---
ESPRESSIF_VID = 0x303A
"""Espressif USB Vendor ID"""

USB_JTAG_SERIAL_PID = 0x1001
"""Known Espressif Product ID for JTAG serial ports"""

ESP_ROM_BAUD = 115200
"""Default serial baud rate for ROM bootloader communication"""

# --- Serial port & reset ---
MACOS_PORT_EXCLUDE_LIST = ('Bluetooth-Incoming-Port', 'wlan-debug', 'cu.debug-console')
"""macOS virtual ports to exclude (not real serial devices)"""

LINUX_DEVICE_PATTERNS = ('ttyUSB', 'ttyACM')
"""Linux device name patterns (used for sorting priority)"""

MACOS_DEVICE_PATTERNS = ('usbserial', 'usbmodem')
"""macOS device name patterns (used for sorting priority)"""

# Unix-only IOCTL constants for simultaneous DTR+RTS setting
# (needed because pyserial can't set both pins atomically)
# Set to None if not available to avoid import errors (e.g. Windows)
TIOCMSET = None
TIOCMGET = None
TIOCM_DTR = None
TIOCM_RTS = None
if os.name != 'nt':
    try:
        import termios

        TIOCMSET = termios.TIOCMSET
        TIOCMGET = termios.TIOCMGET
        TIOCM_DTR = termios.TIOCM_DTR
        TIOCM_RTS = termios.TIOCM_RTS
    except (ImportError, AttributeError):
        pass
