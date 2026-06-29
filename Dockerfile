FROM python:3.11-slim

# ── System deps ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python deps (SIN torch — el modelo está en Modal) ─────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── App files ─────────────────────────────────────────────────────────
COPY main.py .
COPY pipeline.py .
COPY schemas.py .

# ── Frontend ──────────────────────────────────────────────────────────
RUN mkdir -p static
COPY index.html static/index.html

# ── Directorios runtime ───────────────────────────────────────────────
RUN mkdir -p uploads outputs temp

ENV MODELS_DIR=/models
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV TOKENIZERS_PARALLELISM=false

EXPOSE 8000

# Healthcheck normal — arranque rápido porque NO descarga modelos grandes
HEALTHCHECK --interval=20s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
