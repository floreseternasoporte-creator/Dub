# Guía de Despliegue — Video Dubber (Railway + Modal)

## Arquitectura

```
Usuario → Railway (FastAPI)
              ↓  ffmpeg + Whisper (CPU)
              ↓  HTTP POST con audio en base64
           Modal (GPU A10G)
              ↓  SeamlessM4T v2 large
              ↓  devuelve audio doblado en base64
         Railway ← mezcla video + audio → MP4 final
```

## Paso 1 — Desplegar el worker GPU en Modal (solo una vez)

```bash
# En tu máquina local:
pip install modal
modal setup          # abre navegador para autenticarse

modal deploy modal_worker.py
```

Al terminar verás algo como:
```
✓ Created web endpoint https://TU-USUARIO--video-dubber-seamless-api-web.modal.run
```

Copia esa URL — la necesitas en el Paso 2.

## Paso 2 — Configurar variable de entorno en Railway

En el dashboard de Railway → tu servicio → Variables:

```
MODAL_SEAMLESS_URL = https://TU-USUARIO--video-dubber-seamless-api-web.modal.run
```

## Paso 3 — Desplegar Railway (normal)

```bash
git add .
git push
```

Railway arranca en ~10 segundos (sin descargar modelos pesados).

## Costos estimados (Modal)

| GPU       | $/hora | Cold start | Uso típico               |
|-----------|--------|------------|--------------------------|
| A10G      | ~$0.90 | ~15 s      | Recomendado              |
| A100 40GB | ~$1.50 | ~20 s      | Para videos muy largos   |
| T4        | ~$0.40 | ~25 s      | Más barato, más lento    |

Modal escala a 0 cuando no hay tráfico → pagas 0 en horas sin uso.
Un doblaje de 3 minutos cuesta aprox. $0.05–0.15 en GPU.

## Primera llamada (cold start)

La primera vez que se procesa un job tras inactividad, Modal tarda
15–30 segundos en encender el contenedor GPU con el modelo cargado.
Las llamadas siguientes son inmediatas (warm container).

El frontend mostrará el paso "Doblando en GPU · Modal" — esto es normal.

## Variables de entorno Railway

| Variable            | Descripción                          | Requerida |
|---------------------|--------------------------------------|-----------|
| MODAL_SEAMLESS_URL  | URL del worker Modal                 | ✅ Sí     |
| MODELS_DIR          | Directorio Whisper (volumen Railway) | No        |
| PORT                | Puerto (Railway lo asigna solo)      | No        |
