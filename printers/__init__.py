"""
printers/__init__.py -- printer driver registry.

server.py picks a driver at startup based on DAVINCI_PRINTER (see
/etc/davinci/config.env) and calls get_driver_class() below. To add
support for a new printer:

  1. Write printers/<your_id>.py with a class implementing
     printers.base.PrinterDriver (see davinci_1_0_pro.py for a full
     example against minimover).
  2. Import that class and add it to DRIVERS below.
  3. Set DAVINCI_PRINTER=<your_id> in /etc/davinci/config.env and
     restart the service (sudo systemctl restart davinci-server).

That's the whole extension surface -- server.py, the browser UI, and
the OctoPrint API shim are all printer-agnostic.
"""

from .base import PrinterDriver
from .davinci_1_0_pro import DaVinci10ProDriver

DRIVERS = {
    DaVinci10ProDriver.id: DaVinci10ProDriver,
}


def get_driver_class(printer_id: str):
    try:
        return DRIVERS[printer_id]
    except KeyError:
        available = ", ".join(sorted(DRIVERS)) or "(none registered)"
        raise ValueError(
            f"Unknown DAVINCI_PRINTER '{printer_id}'. Available: {available}. "
            "Set DAVINCI_PRINTER in /etc/davinci/config.env to one of these."
        )


__all__ = ["PrinterDriver", "DRIVERS", "get_driver_class"]
