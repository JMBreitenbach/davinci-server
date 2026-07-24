"""
printers/davinci_1_0_pro.py -- driver for the XYZprinting da Vinci 1.0 Pro.

Talks to the printer via the `minimover` command-line utility
(https://github.com/reality-boy/miniMover), which reverse-engineers
XYZprinting's USB serial protocol.

The da Vinci 1.0 Pro is one of the models minimover supports over its
newer "v3" serial protocol (unlike the plain da Vinci 1.0, which
minimover can only convert files for, not print directly -- see the
miniMover README's printer list if adapting this driver for a
different da Vinci model).

This driver does the conversion and the print as two explicit steps
-- `minimover -c` to produce a .3w file, then `minimover -p` to stream
it to the printer -- rather than relying on minimover's single-shot
"-p some.gcode" (which converts internally without writing the .3w to
disk). Two steps means the .3w file is kept in the upload directory's
.converted/ folder, so it can be inspected or reprinted without
re-converting.

--------------------------------------------------------------------
CAVEAT: minimover's exact output location/filename for `-c` isn't
documented beyond "convert file". This driver assumes it writes
<source-stem>.3w next to the source file (the common convention for
CLI converters) and moves it into dest_dir. If you find minimover
actually does something else on your build, fix _locate_converted()
below -- run `minimover -c test.gcode` by hand from an empty directory
and see where the .3w lands.

Similarly, minimover's `-s` status output format for this printer
isn't confirmed to be machine-parseable, so status() only reports
whether the command succeeded plus the raw text -- shown in the UI for
troubleshooting, not parsed into structured fields. If you confirm the
format (run `minimover -d /dev/davinci -s` while idle and while
printing, compare output), tighten status() to parse it properly.
--------------------------------------------------------------------
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .base import PrinterDriver


class DaVinci10ProDriver(PrinterDriver):
    id = "davinci_1_0_pro"
    display_name = "da Vinci 1.0 Pro"
    accepts_extension = ".gcode"
    native_extension = ".3w"

    def __init__(self, device: str, minimover_bin: str = "/usr/local/bin/minimover", **options):
        super().__init__(device, **options)
        self.minimover_bin = minimover_bin

    @classmethod
    def from_env(cls) -> "DaVinci10ProDriver":
        return cls(
            device=os.environ.get("DAVINCI_DEVICE", "/dev/davinci"),
            minimover_bin=os.environ.get("DAVINCI_MINIMOVER_BIN", "/usr/local/bin/minimover"),
        )

    def _locate_converted(self, source_path: Path, cwd: Path) -> Path:
        """Find the .3w minimover just produced. See the CAVEAT above --
        this checks the two most likely spots before giving up."""
        candidates = [
            source_path.with_suffix(".3w"),          # next to the source
            cwd / (source_path.stem + ".3w"),          # in the working dir
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise RuntimeError(
            "minimover reported success but no .3w file was found at any "
            f"expected location ({', '.join(str(c) for c in candidates)}). "
            "See the CAVEAT in printers/davinci_1_0_pro.py -- minimover's "
            "actual output path needs to be confirmed on this build."
        )

    def convert(self, source_path: Path, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / (source_path.stem + ".3w")

        result = subprocess.run(
            [self.minimover_bin, "-c", str(source_path)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            cwd=str(dest_dir),
        )
        if result.returncode != 0:
            raise RuntimeError(f"minimover convert failed:\n{result.stdout}")

        produced = self._locate_converted(source_path, dest_dir)
        if produced != dest:
            produced.replace(dest)
        return dest

    def print_file(self, native_path: Path) -> subprocess.Popen:
        return subprocess.Popen(
            [self.minimover_bin, "-d", self.device, "-p", str(native_path)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )

    def status(self) -> dict:
        try:
            result = subprocess.run(
                [self.minimover_bin, "-d", self.device, "-s"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=10,
            )
            return {"connected": result.returncode == 0, "raw": result.stdout.strip()}
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"connected": False, "raw": str(exc)}
