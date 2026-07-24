"""
printers/base.py -- printer driver interface.

This is the extension point for supporting printers other than the
da Vinci 1.0 Pro. server.py never talks to minimover (or any other
printer-specific tool) directly -- it only calls methods on whatever
PrinterDriver is active. To add a new printer:

  1. Create printers/<your_id>.py with a class that subclasses
     PrinterDriver and implements convert(), print_file(), and status().
     See printers/davinci_1_0_pro.py for a complete example.
  2. Register it in printers/__init__.py's DRIVERS dict.
  3. Set DAVINCI_PRINTER=<your_id> in /etc/davinci/config.env.

Nothing in server.py, the browser UI, or the OctoPrint API shim needs
to change.
"""

from __future__ import annotations

import abc
import os
import subprocess
from pathlib import Path
from typing import Optional


class PrinterDriver(abc.ABC):
    """Base class for a printer backend.

    A driver's job: take a file the user uploaded (normally .gcode from
    a slicer), turn it into whatever the physical printer actually
    understands, send it over whatever connection the printer uses
    (USB serial, network, etc.), and report best-effort status.
    """

    #: short id used in config (DAVINCI_PRINTER=<id>) and logs.
    #: Must be unique across printers/__init__.py's DRIVERS registry.
    id: str = "base"

    #: human-readable name shown in the browser UI's title/status text
    display_name: str = "Unknown printer"

    #: extension the server should accept on upload (case-insensitive).
    #: This is what your slicer needs to export -- almost always .gcode.
    accepts_extension: str = ".gcode"

    #: native file extension this driver converts uploads into before
    #: printing (e.g. ".3w" for XYZprinting da Vinci machines), or None
    #: if the driver prints the accepted file directly with no
    #: conversion step.
    native_extension: Optional[str] = ".gcode"

    def __init__(self, device: str, **options):
        """`device` is the serial port / IP / whatever identifies this
        specific printer's connection. `options` is driver-specific
        (see each driver's from_env())."""
        self.device = device
        self.options = options

    @classmethod
    def from_env(cls) -> "PrinterDriver":
        """Build a driver instance from environment variables (as set
        by /etc/davinci/config.env). Override in subclasses that need
        config beyond DAVINCI_DEVICE -- see davinci_1_0_pro.py."""
        return cls(device=os.environ.get("DAVINCI_DEVICE", "/dev/davinci"))

    @abc.abstractmethod
    def convert(self, source_path: Path, dest_dir: Path) -> Path:
        """Convert an uploaded file into this printer's native format
        and return the path to the converted file (which should live
        inside dest_dir). If native_extension is None, it's fine to
        just return source_path unchanged -- no conversion needed."""

    @abc.abstractmethod
    def print_file(self, native_path: Path) -> subprocess.Popen:
        """Start printing `native_path` on the physical printer and
        return the running subprocess. The caller polls proc.poll()
        and reads proc.returncode when it finishes; a non-zero
        returncode is treated as a failed job."""

    @abc.abstractmethod
    def status(self) -> dict:
        """Best-effort status query, independent of any active job.
        Must return at least {"connected": bool}; anything else
        (e.g. "raw" diagnostic text) is driver-specific and shown
        as-is in the UI for troubleshooting."""

    def estimate_seconds(self, native_path: Path) -> int:
        """Rough duration estimate for the progress bar, used until a
        driver can report real telemetry. Default heuristic: ~2s of
        print time per KB of the native file. Override this in a
        driver once you have real prints to calibrate against."""
        kb = native_path.stat().st_size / 1024
        return max(60, int(kb * 2))
