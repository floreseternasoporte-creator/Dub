"""
modal_worker.py — GPU Worker en Modal
Despliega automáticamente via GitHub Actions (ver .github/workflows/deploy-modal.yml)

Este servicio corre SeamlessM4T v2 large en GPU A10G.
Railway llama a este endpoint HTTP — nunca toca el modelo localmente.
"""

import modal

# ── Imagen con todas las dependencias GPU ────────────────────────────
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
        "huggingface_hub==0.23.0",
        "fastapi[standard]==0.111.0",
    )
)

# Volumen persistente: el modelo se descarga UNA sola vez (~10 GB)
# y queda guardado para siempre → reinicios son instantáneos
volume   = modal.Volume.from_name("seamless-model-vol", create_if_missing=True)
MODEL_DIR = "/model"

app = modal.App("video-dubber-seamless")


@app.cls(
    image=image,
    gpu="A10G",            # 24 GB VRAM — suficiente para v2-large en float16
    volumes={MODEL_DIR: volume},
    timeout=600,           # 10 min por request (videos largos)
    scaledown_window=300,  # mantener GPU caliente 5 min tras último request
    min_containers=0,      # escala a 0 → pagas $0 sin tráfico
    max_containers=3,      # hasta 3 doblajes en paralelo
)
class SeamlessWorker:

    @modal.build()
    def download_model(self):
        """Se ejecuta UNA vez al hacer deploy — descarga el modelo al volumen."""
        import os
        from huggingface_hub import snapshot_download

        dest = os.path.join(MODEL_DIR, "seamless-m4t-v2-large")
        if not os.path.exists(os.path.join(dest, "config.json")):
            print("[Build] Descargando facebook/seamless-m4t-v2-large (~10 GB) ...")
            snapshot_download(
                "facebook/seamless-m4t-v2-large",
                local_dir=dest,
                # Ignorar pesos de otros frameworks para ahorrar espacio
                ignore_patterns=["*.msgpack", "flax_model*", "tf_model*", "rust_model*"],
            )
            volume.commit()
            print("[Build] Descarga guardada en volumen persistente.")
        else:
            print("[Build] Modelo ya en volumen — omitiendo descarga.")

    @modal.enter()
    def load_model(self):
        """Se ejecuta cuando el contenedor GPU arranca — carga el modelo en VRAM."""
        import os
        import torch
        from transformers import AutoProcessor, SeamlessM4Tv2ForSpeechToSpeech

        path = os.path.join(MODEL_DIR, "seamless-m4t-v2-large")
        print("[Enter] Cargando modelo en GPU ...")
        self.processor = AutoProcessor.from_pretrained(path)
        self.model = SeamlessM4Tv2ForSpeechToSpeech.from_pretrained(
            path,
            torch_dtype=torch.float16,   # mitad de VRAM sin pérdida notable de calidad
            low_cpu_mem_usage=True,
        ).to("cuda")
        self.model.eval()
        print("[Enter] Modelo listo en VRAM.")

    @modal.method()
    def translate(self, audio_b64: str, tgt_lang: str, speaker_id: int = 0) -> str:
        """
        Recibe audio WAV en base64 → devuelve audio doblado en base64.
        tgt_lang: código SeamlessM4T (spa, eng, fra, deu, ita, por, jpn, kor, cmn…)
        """
        import base64, io, gc
        import torch, torchaudio
        import soundfile as sf
        import numpy as np

        wav_bytes = base64.b64decode(audio_b64)
        waveform, sr = torchaudio.load(io.BytesIO(wav_bytes))
        if sr != 16000:
            waveform = torchaudio.functional.resample(waveform, sr, 16000)

        # Procesar en chunks de 30 s para audios largos
        chunk_size = 16000 * 30
        chunks = [waveform[:, i:i+chunk_size]
                  for i in range(0, waveform.shape[1], chunk_size)]

        output_chunks = []
        for chunk in chunks:
            inputs = self.processor(
                audios=chunk.numpy(), sampling_rate=16000, return_tensors="pt"
            )
            inputs = {k: v.to("cuda") for k, v in inputs.items()}
            with torch.no_grad():
                out = self.model.generate(**inputs, tgt_lang=tgt_lang, speaker_id=speaker_id)
            output_chunks.append(out[0].cpu().float().numpy().squeeze())
            del out, inputs
            gc.collect()
            torch.cuda.empty_cache()

        audio_out = np.concatenate(output_chunks)
        buf = io.BytesIO()
        sf.write(buf, audio_out, samplerate=16000, format="WAV")
        buf.seek(0)
        return base64.b64encode(buf.read()).decode()


# ── Endpoint HTTP que Railway llama ──────────────────────────────────
@app.function(image=image)
@modal.fastapi_endpoint(method="POST", label="seamless-api")
async def web_translate(request_data: dict) -> dict:
    """
    POST body: { "audio_b64": "...", "tgt_lang": "spa", "speaker_id": 0 }
    Response:  { "audio_b64": "..." }  |  { "error": "..." }
    """
    try:
        audio_b64  = request_data["audio_b64"]
        tgt_lang   = request_data.get("tgt_lang", "spa")
        speaker_id = int(request_data.get("speaker_id", 0))

        result = SeamlessWorker().translate.remote(audio_b64, tgt_lang, speaker_id)
        return {"audio_b64": result}
    except Exception as e:
        return {"error": str(e)}
