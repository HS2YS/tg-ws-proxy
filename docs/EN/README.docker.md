# TG WS Proxy with Docker Compose

This option is intended for running permanently on a VPS. The container
restarts automatically after a crash and after the server reboots.

## Initial Setup

Docker Engine and the Docker Compose plugin must be installed on the VPS.
Replace `YOUR_FORK_URL` with the HTTPS or SSH URL of your fork.

```bash
git clone YOUR_FORK_URL
cd tg-ws-proxy
cp .env.example .env
openssl rand -hex 16
nano .env
chmod 600 .env
```

Paste the output of `openssl rand -hex 16` into `TG_WS_PROXY_SECRET` without the
`dd` or `ee` prefix, and set `TG_WS_PROXY_PUBLIC_HOST` to the public IPv4 address
or DNS name of the VPS, without `http://` or `https://`.

After this one-time setup, a single command starts everything:

```bash
docker compose up -d --build
```

The `restart: unless-stopped` policy brings the container back up after a crash
or a VPS reboot. If Docker is not enabled at boot on your system, enable it
separately.

The image installs only prebuilt wheels and compiles nothing, so the build takes
about half a minute. `linux/amd64` and `linux/arm64` are supported. On 32-bit
ARM (`linux/arm/v7`) the build fails immediately: `cffi`, which `cryptography`
depends on, does not publish an `armv7l` wheel. For that platform, add the
`build-essential libffi-dev` packages back to the `Dockerfile` and remove the
`--only-binary=:all:` flag.

## Getting the Link

```bash
docker compose logs tg-ws-proxy 2>&1 | grep 'tg://proxy' | tail -1
```

The link already contains the public address, the external port and the secret
from `.env`:

```text
tg://proxy?server=203.0.113.10&port=1443&secret=dd0123456789abcdef...
```

The logs contain the secret. Do not publish them in full and do not add `.env`
to Git.

## Main `.env` Settings

| Variable | Purpose | Default |
|---|---|---|
| `TG_WS_PROXY_PUBLIC_HOST` | Public IPv4 address or DNS name of the VPS; required | — |
| `TG_WS_PROXY_PUBLIC_PORT` | TCP port on the VPS and in the connection link | `1443` |
| `TG_WS_PROXY_SECRET` | Persistent key: exactly 32 hex characters; required | — |
| `TG_WS_PROXY_BIND_IP` | VPS interface the port is published on | `0.0.0.0` |
| `TG_WS_PROXY_DC_IPS` | `DC_number:IP` pairs separated by spaces | `2:149.154.167.220 4:149.154.167.220` |
| `TG_WS_PROXY_CF_WORKER` | One or more Cloudflare Worker domains | empty |

Inside the container the proxy always listens on `0.0.0.0:1443`. So, for
example, `TG_WS_PROXY_PUBLIC_PORT=443` publishes port `443` on the VPS without
running the process in the container as root.

Additional settings (`Fake TLS`, custom CF domains, pool size, debug logs and
others) are described in comments in `.env.example`.

After changing `.env`, recreate the container:

```bash
docker compose up -d
```

`--build` is not needed here: values from `.env` are applied when the container
is created, not baked into the image. `docker compose restart` does not pick up
changed variables.

## Checks and Maintenance

```bash
# Status and healthcheck
docker compose ps

# Live logs
docker compose logs -f tg-ws-proxy

# Stop
docker compose down
```

Docker keeps local logs in three files of 10 MB each. The healthcheck verifies
that a local TCP listener exists without making a test connection through the
proxy; an `unhealthy` status does not trigger a restart by itself, but the
built-in watchdog restores the listener, and Docker restarts the process if it
exits.

Remember to allow incoming TCP connections to `TG_WS_PROXY_PUBLIC_PORT` in the
VPS firewall and in your provider's firewall/security group.

## Configuring Telegram

Open the generated `tg://proxy` link or add the proxy manually:

1. Telegram → **Settings** → **Advanced** → **Connection type** → **Proxy**.
2. Choose the **MTProto** type.
3. Enter `TG_WS_PROXY_PUBLIC_HOST`, `TG_WS_PROXY_PUBLIC_PORT` and the full
   secret from the generated link (with the `dd` prefix, or `ee` for Fake TLS).
