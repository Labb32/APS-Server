FROM node:22-bookworm-slim

ARG CODEX_VERSION=0.149.1

ENV PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    APS_VAULT_PATH=/vault \
    APS_DATA_PATH=/data \
    CODEX_HOME=/codex-home

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git python3 python3-venv tini \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global "@openai/codex@${CODEX_VERSION}" \
    && python3 -m venv /opt/venv

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && mkdir -p /data/jobs /data/artifacts /data/work /codex-home \
    && chown -R node:node /app /data /codex-home

USER node
EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "aps_server.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
