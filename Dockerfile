FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.title="APS Server" \
      org.opencontainers.image.description="FastAPI runtime for canonical APS Vault content and official extensions" \
      org.opencontainers.image.source="https://github.com/Labb32/aps-server" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/git-auth \
    GIT_CONFIG_GLOBAL=/git-auth/gitconfig \
    GIT_TERMINAL_PROMPT=0 \
    GIT_SSH_COMMAND="ssh -o BatchMode=yes -o StrictHostKeyChecking=yes" \
    APS_VAULT_PATH=/vault \
    APS_DATA_PATH=/data \
    APS_VAULT_MODE=local \
    APS_VAULT_TEMPLATE_PATH=/opt/aps/vault-template \
    APS_EXTENSIONS_PATH=/data/extensions \
    APS_OFFICIAL_EXTENSIONS_PATH=/opt/aps/official-extensions \
    APS_HTTP_HOST=0.0.0.0 \
    APS_HTTP_PORT=8080

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git openssh-client tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 aps \
    && useradd --system --uid 10001 --gid aps --create-home --home-dir /git-auth --shell /usr/sbin/nologin aps

WORKDIR /app
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
COPY extensions /opt/aps/official-extensions
COPY vault-template /opt/aps/vault-template
RUN pip install --no-cache-dir . \
    && python3 -m pip uninstall --yes pip setuptools \
    && mkdir -p /vault /data/jobs /data/artifacts /data/work /data/extensions /config /git-auth/.ssh \
    && chown -R aps:aps /vault /data /config /git-auth \
    && chmod 700 /git-auth /git-auth/.ssh

USER aps
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python3", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('APS_HTTP_PORT', '8080') + '/health/live', timeout=3).close()"]
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python3", "-m", "aps_server.bootstrap"]
