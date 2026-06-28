# 🎬 VideoDubber · XTTS2

> Dobla videos preservando la voz original con IA. Pipeline completo: separación de audio, transcripción Whisper, traducción y síntesis XTTS2.

## Stack

| Capa | Tecnología |
|------|-----------|
| Frontend | React + Vite (estilos Claude) |
| Backend | FastAPI + Python 3.11 |
| Voz a texto | faster-whisper (Whisper large-v3) |
| Separación vocal | Demucs (htdemucs_ft) |
| Síntesis | XTTS2 (Coqui TTS) — voice cloning |
| Video | FFmpeg |
| Deploy | Railway |

## Pipeline

```
Video entrada
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  IMPORTACIÓN                                        │
│  Separando audio y video ··················· ✓     │
│  Preparando medio ·························· ✓     │
│  Transcodificando medio ···················· ✓     │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  TRANSCRIPCIÓN                                      │
│  Separando voz del fondo (Demucs) ·········· ✓     │
│  Generando subtítulos fuente (Whisper) ······ ✓     │
│  Preparando voces separadas ················ ✓     │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  ANÁLISIS                                           │
│  Preparando voces para análisis ············ ✓     │
│  Analizando voces (embeddings XTTS2) ······· ✓     │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  TRADUCCIÓN (por cada idioma)                       │
│  Solicitando doblaje (Korean) ·············· ✓     │
│  Solicitando doblaje (Spanish MX) ·········· ✓     │
│  Traduciendo y doblando (Spanish MX) ······· ✓     │
└─────────────────────────────────────────────────────┘
    │
    ▼
Video doblado por idioma (descarga directa)
```

## Inicio rápido

### Desarrollo local

```bash
# Clonar repo
git clone <repo-url>
cd video-dubber

# Backend
cd backend
pip install -r requirements.txt
# Para producción, instalar los AI packages:
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install TTS faster-whisper demucs

uvicorn main:app --reload --port 8000

# Frontend (otra terminal)
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

### Con Docker

```bash
docker-compose up --build
# → http://localhost:3000
```

## Deploy en Railway

### 1. Requisitos Railway

- Plan Hobby o Pro (necesitas al menos 4GB RAM para XTTS2)
- Para velocidad óptima: instancia GPU (RTX 4000+)

### 2. Variables de entorno en Railway

```env
PORT=8000

# Opcional: traducción externa
DEEPL_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here    # Para traducción con GPT-4

# Límites
MAX_FILE_SIZE_MB=500
```

### 3. Deploy

```bash
# Instalar Railway CLI
npm install -g @railway/cli

# Login
railway login

# Iniciar proyecto
railway init

# Deploy
railway up

# Ver logs
railway logs
```

### 4. Configurar dominio personalizado

En el dashboard de Railway → Settings → Domains → Add Custom Domain.

## Activar IA real (producción)

En `backend/requirements.txt`, descomenta:

```txt
TTS==0.22.0
faster-whisper==1.0.1
demucs==4.0.1
torch>=2.1.0
torchaudio>=2.1.0
deepl==1.18.0
```

En `backend/services/pipeline.py`, reemplaza los métodos simulados:

### Separación de voz (Demucs)
```python
import subprocess
subprocess.run([
    "demucs", "--two-stems=vocals", 
    "--out", output_dir,
    input_path
])
```

### Transcripción (faster-whisper)
```python
from faster_whisper import WhisperModel
model = WhisperModel("large-v3", device="cuda", compute_type="float16")
segments, info = model.transcribe(audio_path, beam_size=5)
```

### Síntesis XTTS2
```python
from TTS.api import TTS
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
tts.tts_to_file(
    text=translated_text,
    speaker_wav=voice_sample_path,    # voz original para clonar
    language=target_language,
    file_path=output_path
)
```

### Traducción (DeepL)
```python
import deepl
translator = deepl.Translator(os.getenv("DEEPL_API_KEY"))
result = translator.translate_text(text, target_lang=lang)
```

## Idiomas soportados por XTTS2

`en · es · fr · de · it · pt · pl · tr · ru · nl · cs · ar · zh · ja · ko · hu`

## Arquitectura de archivos

```
video-dubber/
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # UI completa con pipeline visual
│   │   └── main.jsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── backend/
│   ├── main.py              # FastAPI app + endpoints
│   ├── services/
│   │   └── pipeline.py      # Pipeline de doblaje completo
│   ├── models/
│   │   └── schemas.py       # Pydantic schemas
│   └── requirements.txt
├── Dockerfile               # Multi-stage build
├── docker-compose.yml       # Dev local
├── railway.toml             # Railway config
└── README.md
```

## Consideraciones de rendimiento

| Video | CPU (8 cores) | GPU (RTX 4000) |
|-------|--------------|----------------|
| 1 min | ~8 min | ~45 seg |
| 5 min | ~35 min | ~3.5 min |
| 30 min | ~3.5 hrs | ~20 min |

> XTTS2 es costoso computacionalmente. Se recomienda GPU para producción.
