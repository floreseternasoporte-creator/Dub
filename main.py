"""
Video Dubbing API — Backend Principal
Powered by SeamlessM4T v2 large (Meta AI) + Whisper + FFmpeg
"""
import os
import uuid
import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from pipeline import DubbingPipeline
from schemas import JobStatus, JobCreate, JobResponse, LanguageOption

app = FastAPI(
    title="Video Dubber API",
    description="Dubbing API powered by SeamlessM4T v2 large (Meta AI) + Whisper",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

jobs: Dict[str, Dict[str, Any]] = {}
pipeline = DubbingPipeline()

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
STATIC_DIR = Path("static")

for d in [UPLOAD_DIR, OUTPUT_DIR, Path("temp")]:
    d.mkdir(exist_ok=True)


# ── Health ────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


# ── Languages ─────────────────────────────────────────────────────────
@app.get("/languages")
async def get_languages():
    return {
        "languages": [
            {"code": "es",    "name": "Spanish (MX)",    "flag": "🇲🇽"},
            {"code": "es-es", "name": "Spanish (ES)",    "flag": "🇪🇸"},
            {"code": "en",    "name": "English",         "flag": "🇺🇸"},
            {"code": "fr",    "name": "French",          "flag": "🇫🇷"},
            {"code": "de",    "name": "German",          "flag": "🇩🇪"},
            {"code": "it",    "name": "Italian",         "flag": "🇮🇹"},
            {"code": "pt",    "name": "Portuguese (BR)", "flag": "🇧🇷"},
            {"code": "ja",    "name": "Japanese",        "flag": "🇯🇵"},
            {"code": "ko",    "name": "Korean",          "flag": "🇰🇷"},
            {"code": "zh",    "name": "Chinese",         "flag": "🇨🇳"},
            {"code": "ru",    "name": "Russian",         "flag": "🇷🇺"},
            {"code": "ar",    "name": "Arabic",          "flag": "🇸🇦"},
            {"code": "hi",    "name": "Hindi",           "flag": "🇮🇳"},
            {"code": "tr",    "name": "Turkish",         "flag": "🇹🇷"},
            {"code": "nl",    "name": "Dutch",           "flag": "🇳🇱"},
            {"code": "pl",    "name": "Polish",          "flag": "🇵🇱"},
        ]
    }


# ── Jobs ──────────────────────────────────────────────────────────────
@app.post("/jobs/upload")
async def upload_video(file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    allowed = {"video/mp4", "video/mpeg", "video/webm", "video/quicktime", "video/x-msvideo"}
    if file.content_type not in allowed:
        raise HTTPException(400, f"Tipo no soportado: {file.content_type}")
    file_path = UPLOAD_DIR / f"{job_id}_{file.filename}"
    with open(file_path, "wb") as f:
        f.write(await file.read())
    jobs[job_id] = {
        "id": job_id, "filename": file.filename,
        "status": "pending", "progress": 0,
        "current_step": None, "steps": {}, "groups": {},
        "file_path": str(file_path), "output_path": None,
        "outputs": {}, "error": None,
        "created_at": asyncio.get_event_loop().time(),
    }
    return {"job_id": job_id, "filename": file.filename}


@app.post("/jobs/{job_id}/start")
async def start_job(job_id: str, target_languages: List[str], background_tasks: BackgroundTasks):
    if job_id not in jobs:
        raise HTTPException(404, "Job no encontrado")
    job = jobs[job_id]
    job["target_languages"] = target_languages
    job["status"] = "processing"
    background_tasks.add_task(pipeline.run, job_id, jobs)
    return {"status": "started", "job_id": job_id}


@app.get("/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job no encontrado")
    return jobs[job_id]


@app.get("/jobs/{job_id}/stream")
async def stream_job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job no encontrado")
    async def event_generator():
        last_hash = None
        while True:
            job = jobs.get(job_id, {})
            payload = json.dumps(job, default=str)
            if payload != last_hash:
                yield f"data: {payload}\n\n"
                last_hash = payload
            if job.get("status") in ("completed", "error"):
                break
            await asyncio.sleep(0.5)
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/jobs/{job_id}/download/{language}")
async def download_dubbed_video(job_id: str, language: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job no encontrado")
    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(400, "Job aún no completado")
    output_path = OUTPUT_DIR / f"{job_id}_{language}.mp4"
    if not output_path.exists():
        raise HTTPException(404, "Archivo no encontrado")
    return FileResponse(str(output_path), media_type="video/mp4",
                        filename=f"dubbed_{language}_{job['filename']}")


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job no encontrado")
    job = jobs.pop(job_id)
    for key in ("file_path", "output_path"):
        p = Path(job.get(key) or "")
        if p.exists():
            p.unlink(missing_ok=True)
    return {"status": "deleted"}


# ── Serve HTML frontend ───────────────────────────────────────────────
# index.html se sirve para cualquier ruta que no sea API
@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    api_prefixes = ("health", "languages", "jobs", "docs", "openapi", "redoc")
    if any(full_path.startswith(p) for p in api_prefixes):
        raise HTTPException(404)
    index = STATIC_DIR / "index.html"
    if index.exists():
        return HTMLResponse(
            content=index.read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-cache"},
        )
    return HTMLResponse("<h1>App cargando...</h1>", status_code=200)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
