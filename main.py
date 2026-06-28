"""
Video Dubbing API - Backend Principal
Powered by XTTS2 + Whisper + FFmpeg
"""
import os
import uuid
import asyncio
import json
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from pipeline import DubbingPipeline
from schemas import (
    JobStatus, JobCreate, JobResponse, LanguageOption, VoiceProfile
)

app = FastAPI(
    title="Video Dubber API",
    description="Dubbing API powered by XTTS2",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store (Redis en prod)
jobs: Dict[str, Dict[str, Any]] = {}
pipeline = DubbingPipeline()

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/languages")
async def get_languages():
    """Idiomas soportados por XTTS2"""
    return {
        "languages": [
            {"code": "es", "name": "Spanish (MX)", "flag": "🇲🇽"},
            {"code": "es-es", "name": "Spanish (ES)", "flag": "🇪🇸"},
            {"code": "en", "name": "English", "flag": "🇺🇸"},
            {"code": "fr", "name": "French", "flag": "🇫🇷"},
            {"code": "de", "name": "German", "flag": "🇩🇪"},
            {"code": "it", "name": "Italian", "flag": "🇮🇹"},
            {"code": "pt", "name": "Portuguese (BR)", "flag": "🇧🇷"},
            {"code": "ja", "name": "Japanese", "flag": "🇯🇵"},
            {"code": "ko", "name": "Korean", "flag": "🇰🇷"},
            {"code": "zh", "name": "Chinese", "flag": "🇨🇳"},
            {"code": "ru", "name": "Russian", "flag": "🇷🇺"},
            {"code": "ar", "name": "Arabic", "flag": "🇸🇦"},
            {"code": "hi", "name": "Hindi", "flag": "🇮🇳"},
            {"code": "tr", "name": "Turkish", "flag": "🇹🇷"},
            {"code": "nl", "name": "Dutch", "flag": "🇳🇱"},
            {"code": "pl", "name": "Polish", "flag": "🇵🇱"},
        ]
    }


@app.post("/jobs/upload")
async def upload_video(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """Subir video e iniciar pipeline de doblaje"""
    job_id = str(uuid.uuid4())
    
    # Validar tipo de archivo
    allowed_types = ["video/mp4", "video/mpeg", "video/webm", "video/quicktime", "video/x-msvideo"]
    if file.content_type not in allowed_types:
        raise HTTPException(400, f"Tipo de archivo no soportado: {file.content_type}")
    
    # Guardar archivo
    file_path = UPLOAD_DIR / f"{job_id}_{file.filename}"
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # Inicializar job
    jobs[job_id] = {
        "id": job_id,
        "filename": file.filename,
        "status": "pending",
        "progress": 0,
        "current_step": None,
        "steps": {},
        "file_path": str(file_path),
        "output_path": None,
        "error": None,
        "created_at": asyncio.get_event_loop().time(),
    }
    
    return {"job_id": job_id, "filename": file.filename}


@app.post("/jobs/{job_id}/start")
async def start_job(
    job_id: str,
    target_languages: list[str],
    background_tasks: BackgroundTasks
):
    """Iniciar el pipeline de doblaje"""
    if job_id not in jobs:
        raise HTTPException(404, "Job no encontrado")
    
    job = jobs[job_id]
    job["target_languages"] = target_languages
    job["status"] = "processing"
    
    background_tasks.add_task(pipeline.run, job_id, jobs)
    
    return {"status": "started", "job_id": job_id}


@app.get("/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    """Estado actual del job"""
    if job_id not in jobs:
        raise HTTPException(404, "Job no encontrado")
    return jobs[job_id]


@app.get("/jobs/{job_id}/stream")
async def stream_job_status(job_id: str):
    """Server-Sent Events para progreso en tiempo real"""
    if job_id not in jobs:
        raise HTTPException(404, "Job no encontrado")
    
    async def event_generator():
        last_status = None
        while True:
            job = jobs.get(job_id, {})
            current_status = json.dumps(job, default=str)
            
            if current_status != last_status:
                yield f"data: {current_status}\n\n"
                last_status = current_status
            
            if job.get("status") in ["completed", "error"]:
                break
                
            await asyncio.sleep(0.5)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/jobs/{job_id}/download/{language}")
async def download_dubbed_video(job_id: str, language: str):
    """Descargar video doblado"""
    if job_id not in jobs:
        raise HTTPException(404, "Job no encontrado")
    
    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(400, "Job aún no completado")
    
    output_path = OUTPUT_DIR / f"{job_id}_{language}.mp4"
    if not output_path.exists():
        raise HTTPException(404, "Archivo de salida no encontrado")
    
    return FileResponse(
        str(output_path),
        media_type="video/mp4",
        filename=f"dubbed_{language}_{job['filename']}"
    )


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Eliminar job y archivos asociados"""
    if job_id not in jobs:
        raise HTTPException(404, "Job no encontrado")
    
    job = jobs[job_id]
    
    # Limpiar archivos
    for path_key in ["file_path", "output_path"]:
        if job.get(path_key):
            path = Path(job[path_key])
            if path.exists():
                path.unlink()
    
    del jobs[job_id]
    return {"status": "deleted"}


# ── Serve React frontend (must come AFTER all API routes) ──────────────
STATIC_DIR = Path("static")
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        """Catch-all: serve index.html for any non-API route (SPA routing)."""
        index = STATIC_DIR / "index.html"
        if index.exists():
            return HTMLResponse(index.read_text())
        return HTMLResponse("<h1>Frontend not built</h1>", status_code=404)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
