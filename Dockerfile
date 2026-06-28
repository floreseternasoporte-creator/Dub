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

# ── Frontend build ───────────────────────────────────────────────────
RUN mkdir -p /app/frontend-src/src
COPY package.json   /app/frontend-src/package.json
COPY vite.config.js /app/frontend-src/vite.config.js
COPY index.html     /app/frontend-src/index.html
COPY App.jsx        /app/frontend-src/src/App.jsx
COPY main.jsx       /app/frontend-src/src/main.jsx

WORKDIR /app/frontend-src
RUN npm install --silent && npm run build

# ── Backend + static ─────────────────────────────────────────────────
WORKDIR /app
COPY main.py .
COPY pipeline.py .
COPY schemas.py .

RUN mv /app/frontend-src/dist ./static && \
    rm -rf /app/frontend-src && \
    mkdir -p uploads outputs temp

ENV MODELS_DIR=/models
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=30s --start-period=300s --retries=10 \
    CMD curl -f http://localhost:8000/health || exit 1

# Usar shell form para que $PORT se expanda correctamente en runtime
CMD python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
