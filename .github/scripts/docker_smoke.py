"""Exercise the Compose deployment using an already-built local image."""

import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
SERVICE = "tg-ws-proxy"
SECRET = "0123456789abcdef0123456789abcdef"  # Public CI fixture, never a VPS secret.
PUBLIC_HOST = "proxy.example.com"
PUBLIC_PORT = 24443
MASKING_DOMAIN = "mask.invalid"


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def run_scenario(fake_tls, directory):
    name = "fake-tls" if fake_tls else "plain"
    environ = dict(os.environ)
    environ.update({
        "TG_WS_PROXY_PUBLIC_HOST": PUBLIC_HOST,
        "TG_WS_PROXY_PUBLIC_PORT": str(PUBLIC_PORT),
        "TG_WS_PROXY_SECRET": SECRET,
        "TG_WS_PROXY_BIND_IP": "127.0.0.1",
        "TG_WS_PROXY_DC_IPS": "2:127.0.0.1 4:127.0.0.1",
        "TG_WS_PROXY_CF_WORKER": "",
        "TG_WS_PROXY_CF_PROXY_DOMAINS": "ci.invalid",
        "TG_WS_PROXY_NO_CF_PROXY": "true",
        "TG_WS_PROXY_NO_H2": "true",
        "TG_WS_PROXY_NO_SECURE": "true" if fake_tls else "false",
        "TG_WS_PROXY_FAKE_TLS_DOMAIN": MASKING_DOMAIN if fake_tls else "",
        "TG_WS_PROXY_PROXY_PROTOCOL": "false",
        "TG_WS_PROXY_FORCE_TEST_DC": "false",
        "TG_WS_PROXY_VERBOSE": "false",
        "TG_WS_PROXY_BUF_KB": "256",
        "TG_WS_PROXY_POOL_SIZE": "0",
    })
    override = directory / "compose-check.json"
    override.write_text(json.dumps({
        "services": {SERVICE: {
            "extra_hosts": {MASKING_DOMAIN: "127.0.0.1"},
            "healthcheck": {
                "interval": "1s", "timeout": "2s",
                "start_period": "1s", "retries": 30,
            },
        }},
    }), encoding="utf-8")
    compose_args = (
        "docker", "compose", "--env-file", os.devnull,
        "--project-name", "tg-ws-proxy-check-" + name,
        "-f", str(ROOT / "compose.yaml"), "-f", str(override),
    )

    def run(*args, timeout=120, required=True):
        result = subprocess.run(
            args, env=environ, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=timeout,
        )
        if required and result.returncode:
            raise RuntimeError(f"Command {args!r} failed:\n{result.stdout}")
        return result.stdout.strip()

    def compose(*args, **kwargs):
        return run(*compose_args, *args, **kwargs)

    def inspect(container):
        return json.loads(run("docker", "inspect", container))[0]

    secret = ("ee" + SECRET + MASKING_DOMAIN.encode("ascii").hex()
              if fake_tls else "dd" + SECRET)
    expected_link = (
        f"tg://proxy?server={PUBLIC_HOST}&port={PUBLIC_PORT}&secret={secret}"
    )

    def check_container():
        container = compose("ps", "-q", SERVICE)
        info = inspect(container)
        check(info["State"]["Health"]["Status"] == "healthy", "Not healthy")
        check(info["HostConfig"]["ReadonlyRootfs"], "Root filesystem is writable")
        uid = run("docker", "exec", container, "python", "-c",
                  "import os; print(os.getuid())")
        check(int(uid) != 0, "Proxy runs as root")
        bindings = info["NetworkSettings"]["Ports"]["1443/tcp"]
        check(any(binding["HostPort"] == str(PUBLIC_PORT) for binding in bindings),
              "Public port mapping was lost")
        with socket.create_connection(("127.0.0.1", PUBLIC_PORT), timeout=5):
            pass
        logs = compose("logs", "--no-color", SERVICE)
        links = re.findall(r"tg://proxy\?[^\s]+", logs)
        check(links and links[-1] == expected_link, "Incorrect public proxy link")
        check(("No secure:" in logs) == fake_tls, "Incorrect --no-secure setting")
        if fake_tls:
            check("Fake TLS profile unavailable" in logs, "Missing probe fallback")
        return container

    print(f"Checking Compose scenario: {name}", flush=True)
    try:
        compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "90")
        original = check_container()
        compose("up", "-d", "--no-build", "--force-recreate", "--wait",
                "--wait-timeout", "90")
        container = check_container()
        check(container != original, "Container was not recreated")
        started = time.monotonic()
        compose("stop", "--timeout", "20", timeout=25)
        elapsed = time.monotonic() - started
        state = inspect(container)["State"]
        check(not state["Running"] and state["ExitCode"] == 0,
              f"Unclean shutdown: {state}")
        check(elapsed < 20, f"Shutdown took {elapsed:.1f}s")
        check("Shutting down. Final stats:" in compose("logs", "--no-color", SERVICE),
              "Proxy did not complete its shutdown handler")
        print(f"Passed {name}; graceful shutdown in {elapsed:.1f}s", flush=True)
    except Exception:
        print(compose("logs", "--no-color", required=False), flush=True)
        raise
    finally:
        compose("down", "--remove-orphans", required=False)


def main():
    with tempfile.TemporaryDirectory(prefix="tg-ws-proxy-check-") as directory:
        for fake_tls in (False, True):
            run_scenario(fake_tls, Path(directory))


if __name__ == "__main__":
    main()
