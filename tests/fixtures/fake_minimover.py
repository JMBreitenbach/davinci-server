#!/usr/bin/env python3
"""
fake_minimover.py -- stand-in for the real `minimover` CLI, used only by
tests (see tests/conftest.py). Understands just enough of the three
subcommands printers/davinci_1_0_pro.py actually calls to exercise the
full convert -> print -> status pipeline without real printer hardware:

    minimover -c <source.gcode>            convert
    minimover -d <device> -p <native.3w>   print
    minimover -d <device> -s               status

Set FAKE_MINIMOVER_FAIL=1 in the environment to make every call fail,
for testing error handling.
"""
import os
import sys
from pathlib import Path


def main(argv):
    if os.environ.get("FAKE_MINIMOVER_FAIL"):
        print("fake_minimover: simulated failure (FAKE_MINIMOVER_FAIL set)")
        return 1

    if "-c" in argv:
        source = Path(argv[argv.index("-c") + 1])
        # Mirrors the real driver's expectation (see _locate_converted in
        # printers/davinci_1_0_pro.py): write the .3w into the current
        # working directory, which convert() sets to dest_dir.
        out = Path.cwd() / (source.stem + ".3w")
        out.write_bytes(b"FAKE-3W-DATA")
        print(f"fake_minimover: converted {source} -> {out}")
        return 0

    if "-p" in argv:
        native_path = Path(argv[argv.index("-p") + 1])
        print(f"fake_minimover: printing {native_path}")
        return 0

    if "-s" in argv:
        print("fake_minimover: STATUS idle")
        return 0

    print(f"fake_minimover: unrecognized arguments: {argv}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
