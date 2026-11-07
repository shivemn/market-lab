# Builds the web page, then serves page and API from one Python process. No secrets baked in.
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/
RUN pip install --no-cache-dir ".[api,postgres]"
COPY --from=web /web/dist web/dist
ENV PORT=8000
# The hosting service sets PORT. If it also sets DATABASE_URL (a postgresql:// address) accounts live in that
# PostgreSQL database and survive restarts. Otherwise they live in a file in /data (attach a disk there to keep them).
# For several worker processes use "marketlab cluster --workers N" instead of "marketlab serve" (needs DATABASE_URL).
CMD ["sh", "-c", "mkdir -p /data && marketlab serve --host 0.0.0.0 --port ${PORT} --db \"${DATABASE_URL:-/data/practice.db}\" --web web/dist --behind-proxy"]
