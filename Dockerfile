FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.title="APS Server" \
      org.opencontainers.image.description="FastAPI runtime for canonical APS Vault content and official extensions" \
      org.opencontainers.image.source="https://github.com/Labb32/aps-server" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV PYTHONUNBUFFERED=1 \
    APS_VAULT_PATH=/vault \
    APS_DATA_PATH=/data \
    APS_VAULT_MODE=local \
    APS_VAULT_TEMPLATE_PATH=/opt/aps/vault-template \
    APS_EXTENSIONS_PATH=/data/extensions \
    APS_OFFICIAL_EXTENSIONS_PATH=/opt/aps/official-extensions \
    APS_HTTP_HOST=0.0.0.0 \
    APS_HTTP_PORT=8080

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system aps \
    && useradd --system --gid aps --home-dir /nonexistent --shell /usr/sbin/nologin aps

WORKDIR /app
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
COPY extensions /opt/aps/official-extensions
COPY vault-template /opt/aps/vault-template
RUN pip install --no-cache-dir . \
    && mkdir -p /vault /data/jobs /data/artifacts /data/work /data/extensions /config \
    && chown -R aps:aps /app /opt/aps /vault /data /config

USER aps
EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python3", "-m", "aps_server.bootstrap"]
