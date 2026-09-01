FROM node:22-bookworm-slim

ARG CODEX_VERSION=0.149.1

ENV PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    APS_VAULT_PATH=/vault \
    APS_DATA_PATH=/data \
    APS_VAULT_MODE=local \
    APS_VAULT_TEMPLATE_PATH=/opt/aps/vault-template \
    APS_EXTENSIONS_PATH=/data/extensions \
    APS_OFFICIAL_EXTENSIONS_PATH=/opt/aps/official-extensions \
    APS_HTTP_HOST=0.0.0.0 \
    APS_HTTP_PORT=8080 \
    CODEX_HOME=/codex-home

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git python3 python3-venv tini \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global "@openai/codex@${CODEX_VERSION}" \
    && python3 -m venv /opt/venv

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY extensions /opt/aps/official-extensions
COPY vault-template /opt/aps/vault-template
RUN pip install --no-cache-dir . \
    && mkdir -p /vault /data/jobs /data/artifacts /data/work /data/extensions /codex-home /config \
    && chown -R node:node /app /opt/aps /vault /data /codex-home /config

USER node
EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python3", "-m", "aps_server.bootstrap"]
