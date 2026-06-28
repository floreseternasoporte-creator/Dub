FROM python:3.11-slim

# ── System deps ──────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 libgomp1 curl nodejs npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python deps ──────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Pre-descargar modelos en build (para que el arranque sea rápido) ──
RUN python -c "\
from transformers import AutoProcessor, SeamlessM4Tv2ForSpeechToSpeech; \
AutoProcessor.from_pretrained('facebook/seamless-m4t-v2-large'); \
SeamlessM4Tv2ForSpeechToSpeech.from_pretrained('facebook/seamless-m4t-v2-large'); \
print('SeamlessM4T descargado OK')"

RUN python -c "\
from faster_whisper import WhisperModel; \
WhisperModel('base', device='cpu', compute_type='int8'); \
print('Whisper descargado OK')"

# ── Frontend build ───────────────────────────────────────────────────
RUN mkdir -p /app/frontend-src
COPY package.json /app/frontend-src/package.json
WORKDIR /app/frontend-src
RUN npm install --silent

COPY index.html .
COPY vite.config.js .
COPY App.jsx ./src/App.jsx
COPY main.jsx ./src/main.jsx
RUN npm run build

# ── Backend ──────────────────────────────────────────────────────────
WORKDIR /app
COPY main.py .
COPY pipeline.py .
COPY schemas.py .

RUN mv /app/frontend-src/dist ./static && \
    rm -rf /app/frontend-src && \
    mkdir -p uploads outputs temp

EXPOSE 8000
ENV PORT=8000
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Start period largo porque los modelos cargan en RAM al primer request
HEALTHCHECK --interval=30s --timeout=30s --start-period=120s --retries=5 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
