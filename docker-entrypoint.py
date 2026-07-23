#!/usr/bin/env python3
"""Translate container environment variables into proxy CLI arguments."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import List, Mapping, Sequence


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"", "0", "false", "no", "off"}
_PORT_FILE = Path("/tmp/tg-ws-proxy-port")


def _is_enabled(environ: Mapping[str, str], name: str) -> bool:
    value = environ.get(name, "false").strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    print(f"Invalid boolean value for {name}: {value}", file=sys.stderr)
    raise SystemExit(2)


def _split_list(value: str) -> List[str]:
    return [
        item for item in re.split(r"[\s,;]+", value.strip())
        if item
    ]


def _last_option_value(
    arguments: Sequence[str],
    option: str,
    default: str,
) -> str:
    result = default
    for index, argument in enumerate(arguments):
        if argument == option and index + 1 < len(arguments):
            result = arguments[index + 1]
        elif argument.startswith(f"{option}="):
            result = argument.split("=", 1)[1]
    return result


def build_proxy_command(
    extra_args: Sequence[str],
    environ: Mapping[str, str],
) -> List[str]:
    command = [
        sys.executable,
        "-u",
        "-m",
        "proxy.tg_ws_proxy",
        "--host",
        environ.get("TG_WS_PROXY_HOST", "0.0.0.0"),
        "--port",
        environ.get("TG_WS_PROXY_PORT", "1443"),
        "--buf-kb",
        environ.get("TG_WS_PROXY_BUF_KB", "256"),
        "--pool-size",
        environ.get("TG_WS_PROXY_POOL_SIZE", "4"),
    ]

    scalar_options = (
        ("TG_WS_PROXY_PUBLIC_HOST", "--public-host"),
        ("TG_WS_PROXY_PUBLIC_PORT", "--public-port"),
        ("TG_WS_PROXY_SECRET", "--secret"),
        ("TG_WS_PROXY_FAKE_TLS_DOMAIN", "--fake-tls-domain"),
    )
    for env_name, option in scalar_options:
        value = environ.get(env_name, "")
        if value:
            command.extend((option, value))

    list_options = (
        (
            "TG_WS_PROXY_DC_IPS",
            "--dc-ip",
            "2:149.154.167.220 4:149.154.167.220",
        ),
        ("TG_WS_PROXY_CF_WORKER", "--cfproxy-worker-domain", ""),
        ("TG_WS_PROXY_CF_PROXY_DOMAINS", "--cfproxy-domain", ""),
    )
    for env_name, option, default in list_options:
        for value in _split_list(environ.get(env_name, default)):
            command.extend((option, value))

    boolean_options = (
        ("TG_WS_PROXY_NO_CF_PROXY", "--no-cfproxy"),
        ("TG_WS_PROXY_PROXY_PROTOCOL", "--proxy-protocol"),
        ("TG_WS_PROXY_FORCE_TEST_DC", "--force-test-dc"),
        ("TG_WS_PROXY_VERBOSE", "--verbose"),
    )
    for env_name, option in boolean_options:
        if _is_enabled(environ, env_name):
            command.append(option)

    # Explicit scalar options take precedence; repeatable options extend lists.
    command.extend(extra_args)
    return command


def main() -> None:
    extra_args = sys.argv[1:]
    if extra_args and not extra_args[0].startswith("-"):
        os.execvp(extra_args[0], extra_args)

    command = build_proxy_command(extra_args, os.environ)
    listen_port = _last_option_value(
        command, "--port", os.environ.get("TG_WS_PROXY_PORT", "1443")
    )
    try:
        _PORT_FILE.write_text(listen_port, encoding="ascii")
    except OSError:
        # The proxy can still run in a manually hardened container without /tmp.
        pass
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
