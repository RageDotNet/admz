# LLM DMZ v2 image — Python base, packaged app, non-root (infra-v2.md).
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY migrations ./migrations
COPY skills ./skills
RUN pip install --no-cache-dir .

# Entrypoint enforces 0600 on the SQLite DB file (#16), then migrates, then serves.
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN useradd --system --create-home dmz && mkdir -p /var/lib/dmz && chown dmz:dmz /var/lib/dmz
USER dmz

ENV DMZ_DATABASE_URL=sqlite:////var/lib/dmz/dmz.db \
    DMZ_CONFIG=/etc/dmz/config.yaml

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
