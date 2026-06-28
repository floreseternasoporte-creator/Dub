# ════════════════════════════════════════════════
# Stage 1: Build Frontend
# ════════════════════════════════════════════════
FROM node:20-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --silent

COPY frontend/ .
RUN npm run build

# ════════════════════════════════════════════════
# Stage 2: Python Backend (CPU)
# Para GPU: usar pytorch/pytorch:2.2.0-cuda11.8-cudnn8-runtime
# ════════════════════════════════════════════════
FROM python:3.11-slim AS backend

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install heavy AI deps (uncomment for production)
# RUN pip install --no-cache-dir \
#     torch==2.2.0 torchaudio==2.2.0 --index-url https://download.pytorch.org/whl/cpu && \
#     pip install --no-cache-dir TTS==0.22.0 faster-whisper==1.0.1 demucs==4.0.1

# Copy backend
COPY backend/ .

# Copy built frontend → static
COPY --from=frontend-build /app/frontend/../backend/static ./static

# Create dirs
RUN mkdir -p uploads outputs temp

# Serve static files from FastAPI
RUN echo "from fastapi.staticfiles import StaticFiles\nimport os" >> /tmp/patch.py

EXPOSE 8000

ENV PORT=8000
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
