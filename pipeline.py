"""
Pipeline de Doblaje Completo
Fases: Import → Transcribe → Analyze → Translate → Dub
"""
import asyncio
import subprocess
import json
import os
import time
from pathlib import Path
from typing import Dict, Any, List


STEP_GROUPS = {
    "import": {
        "label": "Importación",
        "steps": [
            {"key": "separate_av", "label": "Separando audio y video"},
            {"key": "prepare_media", "label": "Preparando medio"},
            {"key": "transcode", "label": "Transcodificando medio"},
        ]
    },
    "transcription": {
        "label": "Transcripción",
        "steps": [
            {"key": "separate_voice", "label": "Separando voz del fondo"},
            {"key": "generate_subs", "label": "Generando subtítulos fuente"},
            {"key": "prepare_voices", "label": "Preparando voces separadas"},
        ]
    },
    "analysis": {
        "label": "Análisis",
        "steps": [
            {"key": "prepare_analysis", "label": "Preparando voces para análisis"},
            {"key": "analyze_voices", "label": "Analizando voces"},
        ]
    },
    "translation": {
        "label": "Traducción",
        "steps": []  # Dynamic per language
    }
}


class DubbingPipeline:
    
    def __init__(self):
        self.output_dir = Path("outputs")
        self.upload_dir = Path("uploads")
        self.temp_dir = Path("temp")
        self.temp_dir.mkdir(exist_ok=True)
    
    async def run(self, job_id: str, jobs: Dict[str, Any]):
        """Ejecutar pipeline completo"""
        job = jobs[job_id]
        
        try:
            # Inicializar estructura de pasos
            self._init_steps(job)
            
            # === FASE 1: IMPORTACIÓN ===
            await self._run_import_phase(job_id, job)
            
            # === FASE 2: TRANSCRIPCIÓN ===
            await self._run_transcription_phase(job_id, job)
            
            # === FASE 3: ANÁLISIS ===
            await self._run_analysis_phase(job_id, job)
            
            # === FASE 4: TRADUCCIÓN Y DOBLAJE ===
            target_langs = job.get("target_languages", ["es"])
            await self._run_translation_phase(job_id, job, target_langs)
            
            job["status"] = "completed"
            job["progress"] = 100
            
        except Exception as e:
            job["status"] = "error"
            job["error"] = str(e)
            raise
    
    def _init_steps(self, job: Dict):
        """Inicializar todos los pasos como 'pending'"""
        job["steps"] = {}
        job["groups"] = {}
        
        for group_key, group in STEP_GROUPS.items():
            job["groups"][group_key] = {
                "label": group["label"],
                "status": "pending"
            }
            for step in group["steps"]:
                job["steps"][step["key"]] = {
                    "label": step["label"],
                    "status": "pending",
                    "group": group_key,
                    "started_at": None,
                    "completed_at": None,
                }
    
    async def _set_step(self, job: Dict, step_key: str, status: str):
        """Actualizar estado de un paso"""
        if step_key not in job["steps"]:
            job["steps"][step_key] = {}
        
        job["steps"][step_key]["status"] = status
        job["current_step"] = step_key
        
        if status == "running":
            job["steps"][step_key]["started_at"] = time.time()
        elif status in ("complete", "error"):
            job["steps"][step_key]["completed_at"] = time.time()
        
        # Actualizar progreso global
        total_steps = len(job["steps"])
        completed = sum(1 for s in job["steps"].values() if s.get("status") == "complete")
        job["progress"] = int((completed / max(total_steps, 1)) * 95)
    
    async def _run_import_phase(self, job_id: str, job: Dict):
        """Fase 1: Separar AV, preparar, transcodificar"""
        job["groups"]["import"]["status"] = "running"
        file_path = Path(job["file_path"])
        temp_base = self.temp_dir / job_id
        temp_base.mkdir(exist_ok=True)
        
        # Paso 1.1: Separar audio y video
        await self._set_step(job, "separate_av", "running")
        audio_path = temp_base / "audio_raw.wav"
        video_path = temp_base / "video_no_audio.mp4"
        
        await self._ffmpeg_cmd([
            "ffmpeg", "-i", str(file_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(audio_path), "-y"
        ])
        await self._ffmpeg_cmd([
            "ffmpeg", "-i", str(file_path),
            "-an", "-vcodec", "copy",
            str(video_path), "-y"
        ])
        job["temp_paths"] = {"audio_raw": str(audio_path), "video_no_audio": str(video_path)}
        await self._set_step(job, "separate_av", "complete")
        
        # Paso 1.2: Preparar medio
        await self._set_step(job, "prepare_media", "running")
        await asyncio.sleep(0.8)  # Análisis de metadatos
        job["media_info"] = await self._get_media_info(file_path)
        await self._set_step(job, "prepare_media", "complete")
        
        # Paso 1.3: Transcodificar
        await self._set_step(job, "transcode", "running")
        normalized_audio = temp_base / "audio_normalized.wav"
        await self._ffmpeg_cmd([
            "ffmpeg", "-i", str(audio_path),
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            str(normalized_audio), "-y"
        ])
        job["temp_paths"]["audio_normalized"] = str(normalized_audio)
        await self._set_step(job, "transcode", "complete")
        
        job["groups"]["import"]["status"] = "complete"
    
    async def _run_transcription_phase(self, job_id: str, job: Dict):
        """Fase 2: Separar voz, generar subtítulos, preparar voces"""
        job["groups"]["transcription"]["status"] = "running"
        temp_base = self.temp_dir / job_id
        
        # Paso 2.1: Separar voz del fondo (Demucs/Spleeter)
        await self._set_step(job, "separate_voice", "running")
        voice_path = temp_base / "voice.wav"
        bg_path = temp_base / "background.wav"
        await self._simulate_separation(
            job["temp_paths"]["audio_normalized"],
            str(voice_path), str(bg_path)
        )
        job["temp_paths"]["voice"] = str(voice_path)
        job["temp_paths"]["background"] = str(bg_path)
        await self._set_step(job, "separate_voice", "complete")
        
        # Paso 2.2: Generar subtítulos (Whisper)
        await self._set_step(job, "generate_subs", "running")
        transcript = await self._run_whisper(str(voice_path))
        job["transcript"] = transcript
        await self._set_step(job, "generate_subs", "complete")
        
        # Paso 2.3: Preparar voces separadas por segmento
        await self._set_step(job, "prepare_voices", "running")
        segments_dir = temp_base / "segments"
        segments_dir.mkdir(exist_ok=True)
        job["voice_segments"] = await self._segment_voice(
            str(voice_path), transcript, str(segments_dir)
        )
        job["temp_paths"]["segments_dir"] = str(segments_dir)
        await self._set_step(job, "prepare_voices", "complete")
        
        job["groups"]["transcription"]["status"] = "complete"
    
    async def _run_analysis_phase(self, job_id: str, job: Dict):
        """Fase 3: Analizar características de voz"""
        job["groups"]["analysis"]["status"] = "running"
        
        # Paso 3.1: Preparar para análisis
        await self._set_step(job, "prepare_analysis", "running")
        await asyncio.sleep(1.0)
        await self._set_step(job, "prepare_analysis", "complete")
        
        # Paso 3.2: Analizar voces (extracción de embeddings XTTS2)
        await self._set_step(job, "analyze_voices", "running")
        voice_profile = await self._extract_voice_profile(
            job["temp_paths"]["voice"]
        )
        job["voice_profile"] = voice_profile
        await self._set_step(job, "analyze_voices", "complete")
        
        job["groups"]["analysis"]["status"] = "complete"
    
    async def _run_translation_phase(self, job_id: str, job: Dict, target_langs: List[str]):
        """Fase 4: Traducir y doblar en cada idioma"""
        job["groups"]["translation"]["status"] = "running"
        temp_base = self.temp_dir / job_id
        
        for lang in target_langs:
            lang_name = self._get_lang_name(lang)
            
            # Agregar pasos dinámicos para este idioma
            request_key = f"request_dub_{lang}"
            translate_key = f"translate_dub_{lang}"
            
            job["steps"][request_key] = {
                "label": f"Solicitando doblaje ({lang_name})",
                "status": "pending",
                "group": "translation"
            }
            job["steps"][translate_key] = {
                "label": f"Traduciendo y doblando ({lang_name})",
                "status": "pending", 
                "group": "translation"
            }
            
            # Solicitar doblaje
            await self._set_step(job, request_key, "running")
            translated_segments = await self._translate_segments(
                job["transcript"]["segments"], lang
            )
            await self._set_step(job, request_key, "complete")
            
            # Sintetizar con XTTS2
            await self._set_step(job, translate_key, "running")
            dubbed_audio = await self._synthesize_xtts2(
                translated_segments,
                job["voice_profile"],
                lang,
                str(temp_base)
            )
            
            # Mezclar con video
            output_path = self.output_dir / f"{job_id}_{lang}.mp4"
            await self._merge_dubbed_video(
                job["temp_paths"]["video_no_audio"],
                dubbed_audio,
                job["temp_paths"]["background"],
                str(output_path)
            )
            
            job["output_path"] = str(output_path)
            job.setdefault("outputs", {})[lang] = str(output_path)
            await self._set_step(job, translate_key, "complete")
        
        job["groups"]["translation"]["status"] = "complete"
    
    # =================== HELPERS ===================
    
    async def _ffmpeg_cmd(self, cmd: list):
        """Ejecutar comando FFmpeg"""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                # Si FFmpeg no está, simular el resultado
                await asyncio.sleep(0.5)
        except FileNotFoundError:
            # FFmpeg no disponible en dev, simular
            await asyncio.sleep(0.8)
    
    async def _get_media_info(self, file_path: Path) -> Dict:
        """Obtener metadatos del video"""
        try:
            result = subprocess.run([
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", str(file_path)
            ], capture_output=True, text=True)
            return json.loads(result.stdout) if result.returncode == 0 else {}
        except:
            return {"duration": "unknown", "format": "mp4"}
    
    async def _simulate_separation(self, input_path: str, voice_out: str, bg_out: str):
        """
        Separación de voz con Demucs o Spleeter.
        En producción: TorchAudio o demucs CLI
        """
        await asyncio.sleep(2.0)  # Simular tiempo de procesamiento
        # En prod: subprocess.run(["demucs", "--two-stems=vocals", input_path])
    
    async def _run_whisper(self, audio_path: str) -> Dict:
        """
        Transcripción con Whisper.
        En prod: faster-whisper o openai-whisper
        """
        await asyncio.sleep(3.0)
        # Transcript mock para desarrollo
        return {
            "language": "en",
            "text": "Sample transcription for development",
            "segments": [
                {"id": 0, "start": 0.0, "end": 2.5, "text": "Hello, welcome to this video."},
                {"id": 1, "start": 2.5, "end": 5.0, "text": "Today we'll talk about something amazing."},
            ]
        }
    
    async def _segment_voice(self, voice_path: str, transcript: Dict, output_dir: str) -> List[Dict]:
        """Segmentar audio por tiempos del transcript"""
        await asyncio.sleep(1.0)
        return transcript.get("segments", [])
    
    async def _extract_voice_profile(self, voice_path: str) -> Dict:
        """
        Extraer embeddings de voz para XTTS2 voice cloning.
        En prod: TTS().compute_embeddings(voice_path)
        """
        await asyncio.sleep(2.0)
        return {
            "embeddings": "voice_embedding_placeholder",
            "gpt_cond_latent": None,
            "speaker_embedding": None,
        }
    
    async def _translate_segments(self, segments: List[Dict], target_lang: str) -> List[Dict]:
        """
        Traducir segmentos. En prod: DeepL, Google Translate, o LLM.
        """
        await asyncio.sleep(1.5)
        translations = {
            "es": {
                "Hello, welcome to this video.": "Hola, bienvenidos a este video.",
                "Today we'll talk about something amazing.": "Hoy hablaremos de algo increíble.",
            },
            "ko": {
                "Hello, welcome to this video.": "안녕하세요, 이 영상에 오신 걸 환영합니다.",
                "Today we'll talk about something amazing.": "오늘은 놀라운 것에 대해 이야기하겠습니다.",
            }
        }
        
        lang_map = translations.get(target_lang, {})
        return [
            {**seg, "translated_text": lang_map.get(seg["text"], seg["text"])}
            for seg in segments
        ]
    
    async def _synthesize_xtts2(
        self, segments: List[Dict], voice_profile: Dict, 
        lang: str, temp_dir: str
    ) -> str:
        """
        Síntesis con XTTS2 (voice cloning).
        En prod:
            from TTS.api import TTS
            tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
            tts.tts_to_file(text, speaker_wav=voice_wav, language=lang, file_path=out)
        """
        await asyncio.sleep(3.0)
        output_path = os.path.join(temp_dir, f"dubbed_{lang}.wav")
        return output_path
    
    async def _merge_dubbed_video(
        self, video_path: str, dubbed_audio: str, 
        background_audio: str, output_path: str
    ):
        """Mezclar video con audio doblado y música de fondo"""
        await asyncio.sleep(1.5)
        # En prod:
        # ffmpeg -i video.mp4 -i dubbed.wav -i background.wav
        #   -filter_complex "[1:a][2:a]amix=inputs=2:weights=1 0.3[a]"
        #   -map 0:v -map "[a]" output.mp4
    
    def _get_lang_name(self, lang_code: str) -> str:
        names = {
            "es": "Spanish (MX)", "es-es": "Spanish (ES)", "en": "English",
            "fr": "French", "de": "German", "it": "Italian",
            "pt": "Portuguese (BR)", "ja": "Japanese", "ko": "Korean",
            "zh": "Chinese", "ru": "Russian", "ar": "Arabic",
            "hi": "Hindi", "tr": "Turkish",
        }
        return names.get(lang_code, lang_code.upper())
