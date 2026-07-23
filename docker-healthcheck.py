#!/usr/bin/env python3
"""Check that the proxy has a listening TCP socket without connecting to it."""

from __future__ import annotations

import os
from pathlib import Path


_PORT_FILE = Path("/tmp/tg-ws-proxy-port")


def has_listening_socket(port: int) -> bool:
    expected_port = f"{port:04X}"

    for table in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        try:
            lines = table.read_text(encoding="ascii").splitlines()[1:]
        except OSError:
            continue

        for line in lines:
            fields = line.split()
            if len(fields) < 4:
                continue
            local_address = fields[1]
            state = fields[3]
            if local_address.endswith(f":{expected_port}") and state == "0A":
                return True

    return False


if __name__ == "__main__":
    try:
        port_value = _PORT_FILE.read_text(encoding="ascii").strip()
    except OSError:
        port_value = os.environ.get("TG_WS_PROXY_PORT", "1443")
    listen_port = int(port_value)
    raise SystemExit(0 if has_listening_socket(listen_port) else 1)
