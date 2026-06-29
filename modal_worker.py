"""
modal_worker.py — GPU Worker en Modal
Despliega: modal deploy modal_worker.py
URL resultante: https://<tu-usuario>--video-dubber-seamless-api-web.modal.run

Este servicio recibe audio WAV en base64, lo traduce con
SeamlessM4T v2 large en GPU, y devuelve el audio doblado en base64.

Railway llama a este endpoint — nunca carga el modelo en su propio proceso.
"""

import modal

# ── Imagen Docker con todas las dependencias ──────────────────────────
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libsndfile1", "ffmpeg")
    .pip_install(
        "transformers==4.40.2",
        "torch==2.3.0",
        "torchaudio==2.3.0",
        "soundfile==0.12.1",
        "numpy==1.26.4",
        "sentencepiece==0.2.0",
        "accelerate==0.30.1",
        "fastapi[standard]==0.111.0",
        "huggingface_hub==0.23.0",
    )
)

# Volumen persistente — el modelo se descarga UNA sola vez (~10 GB)
volume = modal.Volume.from_name("seamless-model-vol", create_if_missing=True)
MODEL_DIR = "/model"

app = modal.App("video-dubber-seamless")


@app.cls(
    image=image,
    gpu="A10G",           # 24 GB VRAM — suficiente para v2-large
    volumes={MODEL_DIR: volume},
    timeout=600,          # 10 min máximo por request
    scaledown_window=300, # mantener caliente 5 min tras el último request
    min_containers=0,     # escala a 0 cuando no hay tráfico (paga 0)
    max_containers=3,     # hasta 3 en paralelo si hay demanda
)
class SeamlessWorker:

    @modal.build()
    def build(self):
        """Descarga el modelo al volumen durante el build — solo una vez."""
        from huggingface_hub import snapshot_download
        import os
        model_path = os.path.join(MODEL_DIR, "seamless-m4t-v2-large")
        if not os.path.exists(os.path.join(model_path, "config.json")):
            print("[Build] Descargando facebook/seamless-m4t-v2-large ...")
            snapshot_download(
                "facebook/seamless-m4t-v2-large",
                local_dir=model_path,
                ignore_patterns=["*.msgpack", "flax_model*", "tf_model*"],
            )
            volume.commit()
            print("[Build] Descarga completa y guardada en volumen.")
        else:
            print("[Build] Modelo ya en volumen, omitiendo descarga.")

    @modal.enter()
    def enter(self):
        """Carga el modelo en GPU cuando el contenedor arranca (warm start)."""
        import torch
        from transformers import AutoProcessor, SeamlessM4Tv2ForSpeechToSpeech
        import os

        model_path = os.path.join(MODEL_DIR, "seamless-m4t-v2-large")
        print("[Enter] Cargando SeamlessM4T v2 large en GPU ...")
        self.processor = AutoProcessor.from_pretrained(model_path)
        self.model = SeamlessM4Tv2ForSpeechToSpeech.from_pretrained(
            model_path,
            torch_dtype=torch.float16,  # mitad de VRAM
            low_cpu_mem_usage=True,
        ).to("cuda")
        self.model.eval()
        print("[Enter] Modelo listo en GPU.")

    @modal.method()
    def translate(self, audio_b64: str, tgt_lang: str, speaker_id: int = 0) -> str:
        """
        Recibe audio WAV en base64, devuelve audio doblado en base64.
        tgt_lang: código SeamlessM4T (spa, eng, fra, deu, ita, por, jpn, kor, cmn…)
        """
        import base64
        import io
        import gc
        import torch
        import torchaudio
        import soundfile as sf
        import numpy as np

        # Decodificar audio de entrada
        wav_bytes = base64.b64decode(audio_b64)
        buf_in = io.BytesIO(wav_bytes)
        waveform, sr = torchaudio.load(buf_in)
        if sr != 16000:
            waveform = torchaudio.functional.resample(waveform, sr, 16000)

        # Procesar en chunks de 30s para audios largos
        chunk_size = 16000 * 30
        chunks = [waveform[:, i:i + chunk_size]
                  for i in range(0, waveform.shape[1], chunk_size)]

        output_chunks = []
        for chunk in chunks:
            inputs = self.processor(
                audios=chunk.numpy(), sampling_rate=16000, return_tensors="pt"
            )
            inputs = {k: v.to("cuda") for k, v in inputs.items()}

            with torch.no_grad():
                out = self.model.generate(
                    **inputs, tgt_lang=tgt_lang, speaker_id=speaker_id
                )
            output_chunks.append(out[0].cpu().float().numpy().squeeze())
            del out, inputs
            gc.collect()
            torch.cuda.empty_cache()

        audio_out = np.concatenate(output_chunks)

        # Codificar audio de salida en base64
        buf_out = io.BytesIO()
        sf.write(buf_out, audio_out, samplerate=16000, format="WAV")
        buf_out.seek(0)
        return base64.b64encode(buf_out.read()).decode()


# ── Web endpoint para llamadas HTTP desde Railway ─────────────────────
@app.function(image=image)
@modal.web_endpoint(method="POST", label="seamless-api")
async def web_translate(request_data: dict) -> dict:
    """
    Endpoint HTTP que Railway llama vía POST.

    Body JSON:
      { "audio_b64": "<base64 wav>", "tgt_lang": "spa", "speaker_id": 0 }

    Respuesta:
      { "audio_b64": "<base64 wav doblado>" }
      { "error": "mensaje" }   (en caso de fallo)
    """
    try:
        audio_b64  = request_data["audio_b64"]
        tgt_lang   = request_data.get("tgt_lang", "spa")
        speaker_id = int(request_data.get("speaker_id", 0))

        worker = SeamlessWorker()
        result = worker.translate.remote(audio_b64, tgt_lang, speaker_id)
        return {"audio_b64": result}

    except Exception as e:
        return {"error": str(e)}
