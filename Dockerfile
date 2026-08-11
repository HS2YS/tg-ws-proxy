# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

# python:3.12-slim уже содержит ca-certificates, netbase и tzdata, а его CPython
# слинкован с libssl/libcrypto — образу не нужны apt-пакеты вообще.
#
# ЗДЕСЬ НИЧЕГО НЕ КОМПИЛИРУЕТСЯ. cryptography 46.0.5 публикует abi3-колёса для
# manylinux x86_64/aarch64/ppc64le/armv7l и musllinux; её зависимость cffi — колёса
# для x86_64/aarch64/ppc64le/s390x/i686; certifi и pycparser — чистый Python.
# --only-binary=:all: закрепляет этот инвариант: отсутствие колеса даёт отказ за ~3 s
# вместо тихой многоминутной сборки из исходников на 2-vCPU VPS.
# НЕ возвращать build-essential/cargo/libffi-dev/libssl-dev.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    TG_WS_PROXY_HOST=0.0.0.0 \
    TG_WS_PROXY_PORT=1443 \
    TG_WS_PROXY_SECRET="" \
    TG_WS_PROXY_DC_IPS="2:149.154.167.220 4:149.154.167.220" \
    TG_WS_PROXY_CF_WORKER="" \
    TG_WS_PROXY_CF_PROXY_DOMAINS=""

RUN groupadd --system app \
    && useradd --system --gid app --create-home --home-dir /home/app app

# Держать ДО COPY исходников, иначе правка Python будет перезапускать pip.
# PIP_NO_CACHE_DIR намеренно не выставлен: cache mount и держит кеш pip вне слоя,
# и переиспользует его между пересборками. Если mount когда-нибудь уберут —
# вернуть PIP_NO_CACHE_DIR=1, иначе ~10 MB кеша уедут в образ.
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --only-binary=:all: cryptography==46.0.5 certifi

WORKDIR /app
COPY proxy ./proxy
COPY utils ./utils
COPY docs/README.md LICENSE ./
COPY --chmod=755 docker-entrypoint.py /usr/local/bin/docker-entrypoint.py
COPY --chmod=755 docker-healthcheck.py /usr/local/bin/docker-healthcheck.py

USER app

EXPOSE 1443/tcp

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "/usr/local/bin/docker-healthcheck.py"]

# НЕ менять на SIGTERM. docker-entrypoint.py делает execvp, поэтому прокси работает
# как PID 1, а ядро отбрасывает сигналы с диспозицией SIG_DFL, посланные в PID 1.
# CPython ставит собственный обработчик SIGINT (-> KeyboardInterrupt, ловится в
# proxy/tg_ws_proxy.py:815), но оставляет SIGTERM на SIG_DFL. С SIGTERM здесь
# `docker stop` висел бы весь stop_grace_period и заканчивался SIGKILL.
STOPSIGNAL SIGINT

# Без tini: прокси не порождает дочерних процессов (нечего реапить) и сам обрабатывает
# SIGINT. compose.yaml выставляет `init: true` — встроенный docker-init И ЕСТЬ tini —
# как страховку; вне compose эквивалент это `docker run --init`.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.py"]
CMD []
