# Builds the web page, then serves page and API from one Python process. No secrets, no outside services.
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
RUN pip install --no-cache-dir ".[api]"
COPY --from=web /web/dist web/dist
ENV PORT=8000
# the hosting service sets PORT; accounts live in /data (attach a disk there to keep them between restarts)
CMD ["sh", "-c", "mkdir -p /data && marketlab serve --host 0.0.0.0 --port ${PORT} --db /data/practice.db --web web/dist"]
