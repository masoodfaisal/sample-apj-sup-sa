# ── Build stage ──
FROM python:3.13-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY gateway/ ./gateway/
COPY shared/ ./shared/
COPY migrations/ ./migrations/

RUN pip install --no-cache-dir --prefix=/install . pg8000

# ── Runtime stage ──
FROM python:3.13-slim

RUN addgroup --system app && adduser --system --no-create-home --ingroup app app

WORKDIR /app

COPY --from=builder /install /usr/local

COPY gateway/ ./gateway/
COPY shared/ ./shared/
COPY migrations/ ./migrations/
COPY scripts/migrate-entrypoint.sh ./scripts/migrate-entrypoint.sh
RUN chmod +x scripts/migrate-entrypoint.sh

USER app

EXPOSE 8000

CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
