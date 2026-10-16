"""Entrypoint for the TecnoHead HP Home Assistant App."""

from __future__ import annotations

import logging
import signal
import sys

from service import MonitorService
from web_api import serve


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    service = MonitorService()
    server = serve(service)
    service.start()

    def shutdown(_signum: int, _frame: object) -> None:
        server.shutdown()
        service.stop()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        service.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
