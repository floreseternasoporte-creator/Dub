# ════════════════════════════════════════════════
# Stage 1: Build Frontend
# ════════════════════════════════════════════════
FROM node:20-slim AS frontend-build

WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci --silent

COPY frontend/ .
# Build to /app/dist inside this stage
RUN npm run build

# ════════════════════════════════════════════════
# Stage 2: Python Backend
# ════════════════════════════════════════════════
FROM python:3.11-slim AS backend

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Copy frontend build → static/ (served by FastAPI)
COPY --from=frontend-build /app/dist ./static

RUN mkdir -p uploads outputs temp

EXPOSE 8000
ENV PORT=8000
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
