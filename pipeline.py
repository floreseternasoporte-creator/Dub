"""
Pipeline de Doblaje Completo
Fases: Import → Transcribe → Translate (SeamlessM4T v2 large) → Dub
Los modelos se descargan en /models (volumen persistente de Railway) al primer arranque.
"""
import asyncio
import subprocess
import json
import os
import time
import numpy as np
import soundfile as sf
from pathlib import Path
from typing import Dict, Any, List

# ── Rutas de modelos (volumen persistente Railway montado en /models) ──
MODELS_DIR = Path(os.getenv("MODELS_DIR", "/models"))
WHISPER_DIR      = MODELS_DIR / "whisper-base"
SEAMLESS_DIR     = MODELS_DIR / "seamless-m4t-v2-large"

STEP_GROUPS = {
    "import": {
        "label": "Importación",
        "steps": [
            {"key": "separate_av",     "label": "Separando audio y video"},
            {"key": "normalize_audio", "label": "Normalizando audio"},
        ]
    },
    "transcription": {
        "label": "Transcripción",
        "steps": [
            {"key": "load_whisper", "label": "Cargando Whisper"},
            {"key": "transcribe",   "label": "Transcribiendo audio"},
        ]
    },
    "translation": {
        "label": "Traducción y Doblaje",
        "steps": []  # Dinámico por idioma
    }
}

# Singletons — se cargan una sola vez por proceso
_whisper_model       = None
_seamless_processor  = None
_seamless_model      = None


def _ensure_models_dir():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    WHISPER_DIR.mkdir(parents=True, exist_ok=True)
    SEAMLESS_DIR.mkdir(parents=True, exist_ok=True)


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _ensure_models_dir()
        # Descarga a /models/whisper-base si no existe todavía
        _whisper_model = WhisperModel(
            "base",
            device="cpu",
            compute_type="int8",
            download_root=str(WHISPER_DIR),
        )
    return _whisper_model


def _get_seamless():
    global _seamless_processor, _seamless_model
    if _seamless_model is None:
        import torch
        from transformers import AutoProcessor, SeamlessM4Tv2ForSpeechToSpeech
        _ensure_models_dir()

        model_id = "facebook/seamless-m4t-v2-large"

        # Si ya está en el volumen, carga local; si no, descarga ahí
        if (SEAMLESS_DIR / "config.json").exists():
            print(f"[SeamlessM4T] Cargando desde volumen: {SEAMLESS_DIR}")
            _seamless_processor = AutoProcessor.from_pretrained(str(SEAMLESS_DIR))
            _seamless_model = SeamlessM4Tv2ForSpeechToSpeech.from_pretrained(
                str(SEAMLESS_DIR), torch_dtype=torch.float32
            )
        else:
            print(f"[SeamlessM4T] Primera vez — descargando {model_id} en {SEAMLESS_DIR} ...")
            _seamless_processor = AutoProcessor.from_pretrained(
                model_id, cache_dir=str(SEAMLESS_DIR)
            )
            _seamless_model = SeamlessM4Tv2ForSpeechToSpeech.from_pretrained(
                model_id, cache_dir=str(SEAMLESS_DIR), torch_dtype=torch.float32
            )
            # Guardar en formato local para carga rápida en reinicios
            _seamless_processor.save_pretrained(str(SEAMLESS_DIR))
            _seamless_model.save_pretrained(str(SEAMLESS_DIR))
            print(f"[SeamlessM4T] Guardado en volumen OK")

        _seamless_model.eval()
    return _seamless_processor, _seamless_model


# Mapeo de códigos de idioma → códigos SeamlessM4T
SEAMLESS_LANG_MAP = {
    "es":    "spa",
    "es-es": "spa",
    "en":    "eng",
    "fr":    "fra",
    "de":    "deu",
    "it":    "ita",
    "pt":    "por",
    "ja":    "jpn",
    "ko":    "kor",
    "zh":    "cmn",
    "ru":    "rus",
    "ar":    "arb",
    "hi":    "hin",
    "tr":    "tur",
    "nl":    "nld",
    "pl":    "pol",
}


class DubbingPipeline:

    def __init__(self):
        self.output_dir = Path("outputs")
        self.upload_dir = Path("uploads")
        self.temp_dir   = Path("temp")
        self.temp_dir.mkdir(exist_ok=True)

    async def run(self, job_id: str, jobs: Dict[str, Any]):
        job = jobs[job_id]
        try:
            self._init_steps(job)
            await self._run_import_phase(job_id, job)
            await self._run_transcription_phase(job_id, job)
            target_langs = job.get("target_languages", ["es"])
            await self._run_translation_phase(job_id, job, target_langs)
            job["status"]   = "completed"
            job["progress"] = 100
        except Exception as e:
            job["status"] = "error"
            job["error"]  = str(e)
            raise

    def _init_steps(self, job: Dict):
        job["steps"]  = {}
        job["groups"] = {}
        for group_key, group in STEP_GROUPS.items():
            job["groups"][group_key] = {"label": group["label"], "status": "pending"}
            for step in group["steps"]:
                job["steps"][step["key"]] = {
                    "label":        step["label"],
                    "status":       "pending",
                    "group":        group_key,
                    "started_at":   None,
                    "completed_at": None,
                }

    async def _set_step(self, job: Dict, step_key: str, status: str):
        if step_key not in job["steps"]:
            job["steps"][step_key] = {}
        job["steps"][step_key]["status"] = status
        job["current_step"] = step_key
        if status == "running":
            job["steps"][step_key]["started_at"]   = time.time()
        elif status in ("complete", "error"):
            job["steps"][step_key]["completed_at"] = time.time()
        total = len(job["steps"])
        done  = sum(1 for s in job["steps"].values() if s.get("status") == "complete")
        job["progress"] = int((done / max(total, 1)) * 95)

    # ── FASE 1: IMPORTACIÓN ──────────────────────────────────────────

    async def _run_import_phase(self, job_id: str, job: Dict):
        job["groups"]["import"]["status"] = "running"
        file_path = Path(job["file_path"])
        temp_base = self.temp_dir / job_id
        temp_base.mkdir(exist_ok=True)

        # 1.1 Separar audio y video
        await self._set_step(job, "separate_av", "running")
        audio_path = temp_base / "audio_raw.wav"
        video_path = temp_base / "video_no_audio.mp4"
        await self._run_cmd([
            "ffmpeg", "-i", str(file_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(audio_path), "-y"
        ])
        await self._run_cmd([
            "ffmpeg", "-i", str(file_path),
            "-an", "-vcodec", "copy",
            str(video_path), "-y"
        ])
        job["temp_paths"] = {
            "audio_raw":      str(audio_path),
            "video_no_audio": str(video_path),
        }
        await self._set_step(job, "separate_av", "complete")

        # 1.2 Normalizar audio
        await self._set_step(job, "normalize_audio", "running")
        normalized = temp_base / "audio_normalized.wav"
        await self._run_cmd([
            "ffmpeg", "-i", str(audio_path),
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            str(normalized), "-y"
        ])
        job["temp_paths"]["audio_normalized"] = str(normalized)
        await self._set_step(job, "normalize_audio", "complete")

        job["groups"]["import"]["status"] = "complete"

    # ── FASE 2: TRANSCRIPCIÓN CON WHISPER ────────────────────────────

    async def _run_transcription_phase(self, job_id: str, job: Dict):
        job["groups"]["transcription"]["status"] = "running"
        loop = asyncio.get_event_loop()

        await self._set_step(job, "load_whisper", "running")
        await loop.run_in_executor(None, _get_whisper)
        await self._set_step(job, "load_whisper", "complete")

        await self._set_step(job, "transcribe", "running")
        transcript = await loop.run_in_executor(
            None, self._transcribe_sync, job["temp_paths"]["audio_normalized"]
        )
        job["transcript"] = transcript
        await self._set_step(job, "transcribe", "complete")

        job["groups"]["transcription"]["status"] = "complete"

    def _transcribe_sync(self, audio_path: str) -> Dict:
        model = _get_whisper()
        segs_gen, info = model.transcribe(audio_path, beam_size=5)
        segments, full_text = [], []
        for seg in segs_gen:
            segments.append({"id": seg.id, "start": seg.start,
                              "end": seg.end, "text": seg.text.strip()})
            full_text.append(seg.text.strip())
        return {"language": info.language, "text": " ".join(full_text), "segments": segments}

    # ── FASE 3: TRADUCCIÓN + DOBLAJE CON SEAMLESSM4T V2 LARGE ────────

    async def _run_translation_phase(self, job_id: str, job: Dict, target_langs: List[str]):
        job["groups"]["translation"]["status"] = "running"
        loop      = asyncio.get_event_loop()
        temp_base = self.temp_dir / job_id
        audio_path = job["temp_paths"]["audio_normalized"]

        for lang in target_langs:
            lang_name     = self._get_lang_name(lang)
            seamless_lang = SEAMLESS_LANG_MAP.get(lang, "spa")

            load_key = f"load_seamless_{lang}"
            dub_key  = f"dub_{lang}"

            job["steps"][load_key] = {
                "label": f"Cargando SeamlessM4T v2 large ({lang_name})",
                "status": "pending", "group": "translation"
            }
            job["steps"][dub_key] = {
                "label": f"Traduciendo y doblando ({lang_name})",
                "status": "pending", "group": "translation"
            }

            # Cargar modelo (descarga automática al volumen si es la 1ª vez)
            await self._set_step(job, load_key, "running")
            await loop.run_in_executor(None, _get_seamless)
            await self._set_step(job, load_key, "complete")

            # Traducir speech→speech
            await self._set_step(job, dub_key, "running")
            dubbed_wav = temp_base / f"dubbed_{lang}.wav"
            await loop.run_in_executor(
                None, self._translate_audio_sync,
                audio_path, str(dubbed_wav), seamless_lang
            )

            # Mezclar video sin audio + audio doblado
            output_path = self.output_dir / f"{job_id}_{lang}.mp4"
            await self._run_cmd([
                "ffmpeg",
                "-i", str(temp_base / "video_no_audio.mp4"),
                "-i", str(dubbed_wav),
                "-c:v", "copy", "-c:a", "aac",
                "-map", "0:v:0", "-map", "1:a:0",
                "-shortest", str(output_path), "-y"
            ])

            job["output_path"] = str(output_path)
            job.setdefault("outputs", {})[lang] = str(output_path)
            await self._set_step(job, dub_key, "complete")

        job["groups"]["translation"]["status"] = "complete"

    def _translate_audio_sync(self, audio_path: str, output_path: str, tgt_lang: str):
        """Speech-to-speech con SeamlessM4T v2 large. Procesa en chunks de 30s."""
        import torch
        import torchaudio

        processor, model = _get_seamless()

        waveform, sr = torchaudio.load(audio_path)
        if sr != 16000:
            waveform = torchaudio.functional.resample(waveform, sr, 16000)

        chunk_size = 16000 * 30  # 30 segundos por chunk
        chunks     = [waveform[:, i:i + chunk_size]
                      for i in range(0, waveform.shape[1], chunk_size)]

        output_chunks = []
        for chunk in chunks:
            inputs = processor(audios=chunk, sampling_rate=16000, return_tensors="pt")
            with torch.no_grad():
                out = model.generate(**inputs, tgt_lang=tgt_lang, speaker_id=0)
            output_chunks.append(out[0].cpu().numpy().squeeze())

        sf.write(output_path, np.concatenate(output_chunks), samplerate=16000)

    # ── UTILS ─────────────────────────────────────────────────────────

    async def _run_cmd(self, cmd: list):
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"Comando falló: {' '.join(cmd)}\n{stderr.decode()}")
        except FileNotFoundError:
            await asyncio.sleep(0.3)  # Dev sin ffmpeg

    def _get_lang_name(self, code: str) -> str:
        names = {
            "es": "Spanish (MX)", "es-es": "Spanish (ES)", "en": "English",
            "fr": "French",       "de": "German",           "it": "Italian",
            "pt": "Portuguese",   "ja": "Japanese",         "ko": "Korean",
            "zh": "Chinese",      "ru": "Russian",           "ar": "Arabic",
            "hi": "Hindi",        "tr": "Turkish",           "nl": "Dutch",
            "pl": "Polish",
        }
        return names.get(code, code.upper())
