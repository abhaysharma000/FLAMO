# ==============================================================================
# FLAMO Production Multi-Stage Dockerfile
# Stage 1: Build the React / TypeScript / Vite Control Center UI
# Stage 2: Hardened, non-root Python 3.12 runtime with FastAPI & LangGraph
# ==============================================================================

# --- Stage 1: Frontend Build ---
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Install package dependencies
COPY frontend/package*.json ./
RUN npm ci || npm install

# Copy frontend source and compile production bundle
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Production Python Runtime ---
FROM python:3.12-slim AS runtime

# System configurations
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WORKSPACE_DIR=/app/workspace \
    DATABASE_URL=sqlite:////app/data/flamo.db \
    CHROMA_PERSIST_DIRECTORY=/app/data/chroma_db \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PORT=8000 \
    HOST=0.0.0.0

WORKDIR /app

# Install minimal OS dependencies for network health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root user and persistent directory structure
RUN groupadd -g 1000 flamo && \
    useradd -u 1000 -g flamo -s /bin/bash -m flamo && \
    mkdir -p /app/data /app/workspace /app/backups /app/frontend/dist && \
    chown -R flamo:flamo /app

# Install Python dependencies
COPY requirements-prod.txt requirements-browser.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install --timeout=300 --retries=10 -r requirements-prod.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install --timeout=300 --retries=10 -r requirements-browser.txt

# Install Playwright browser dependencies and chromium binary for sandboxed browser automation
RUN mkdir -p /ms-playwright && \
    playwright install --with-deps chromium && \
    chown -R flamo:flamo /ms-playwright && \
    chmod -R 755 /ms-playwright

# Copy backend application and operational scripts
COPY app/ ./app/
COPY scripts/ ./scripts/

# Copy compiled frontend distribution from builder stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Ensure permissions across all application files
RUN chown -R flamo:flamo /app

# Switch to non-root execution
USER flamo

# Expose web service port
EXPOSE 8000

# Health check using lightweight liveness endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health/live || exit 1

# Start Uvicorn ASGI server with graceful shutdown handling
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
