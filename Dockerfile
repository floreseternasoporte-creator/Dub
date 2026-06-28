FROM python:3.11-slim

# ── System deps ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 libgomp1 curl nodejs npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python deps ───────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Frontend build ────────────────────────────────────────────────────
# Vite necesita que index.html y src/ estén juntos en la misma carpeta
RUN mkdir -p /build/src
COPY package.json   /build/package.json
COPY vite.config.js /build/vite.config.js
COPY index.html     /build/index.html
COPY App.jsx        /build/src/App.jsx
COPY main.jsx       /build/src/main.jsx

WORKDIR /build
RUN npm install --silent && npm run build
# Resultado en /build/dist

# ── Backend ───────────────────────────────────────────────────────────
WORKDIR /app
COPY main.py     .
COPY pipeline.py .
COPY schemas.py  .

# Copiar el build del frontend como static/
RUN cp -r /build/dist ./static && \
    rm -rf /build && \
    mkdir -p uploads outputs temp

ENV MODELS_DIR=/models
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

# JSON array form para manejar señales OS correctamente
CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
