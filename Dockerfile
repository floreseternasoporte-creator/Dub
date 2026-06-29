FROM python:3.11-slim

# ── System deps ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python deps ───────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── App files ─────────────────────────────────────────────────────────
COPY main.py .
COPY pipeline.py .
COPY schemas.py .

# ── Frontend (HTML puro — sin build) ──────────────────────────────────
RUN mkdir -p static
COPY index.html static/index.html

# ── Directorios runtime ───────────────────────────────────────────────
RUN mkdir -p uploads outputs temp

ENV MODELS_DIR=/models
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Suprimir FutureWarning de huggingface_hub (resume_download deprecado)
ENV HF_HUB_DISABLE_IMPLICIT_TOKEN=1
ENV TRANSFORMERS_NO_ADVISORY_WARNINGS=1

EXPOSE 8000

# start-period alto porque la primera vez descarga ~10 GB del modelo
HEALTHCHECK --interval=30s --timeout=10s --start-period=300s --retries=10 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
