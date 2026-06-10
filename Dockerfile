# ── Build stage ────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install deps into a prefix that we'll copy to the final image
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ───────────────────────────────────────────────────────────────
# Use the same slim base; copy only what we need — no build tools in prod
FROM python:3.12-slim AS runtime

# Security hardening
#   - Run as non-root user (principle of least privilege)
#   - No shell for the app user
RUN groupadd --gid 1001 appgroup \
 && useradd --uid 1001 --gid appgroup --no-create-home --shell /sbin/nologin appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY app/ ./app/

# Drop to non-root before the final CMD
USER appuser

EXPOSE 8000

# Use exec-form so signals propagate correctly (allows graceful shutdown)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
