# 🎬 Video Dubber — Guía de Despliegue SIN Computadora

Todo se hace desde el navegador. No necesitas instalar nada en tu computadora.

---

## Arquitectura

```
Tu video
   ↓
Railway (gratis)          ← recibe el video, maneja el trabajo
   ↓ envía audio
Modal GPU (gratis $30/mes) ← SeamlessM4T v2 large en GPU A10G
   ↓ devuelve audio doblado
Railway                   ← mezcla video + audio → MP4 final
   ↓
Video doblado ✅
```

---

## PASO 1 — Crear cuenta en Modal (gratis, $30/mes incluidos)

1. Ve a **https://modal.com** → click **"Get started"**
2. Regístrate con GitHub o Google
3. Verás el dashboard de Modal → **ya tienes $30 de crédito gratis cada mes**

---

## PASO 2 — Obtener token de Modal (desde el navegador)

1. En Modal, click en tu avatar (arriba a la derecha) → **"Settings"**
2. En el menú izquierdo → **"API tokens"**
3. Click **"New token"**
4. Dale un nombre: `github-deploy`
5. Copia los dos valores que aparecen:
   - `Token ID` → algo como `ak-abc123...`
   - `Token Secret` → algo como `as-xyz789...`
   - ⚠️ Guárdalos, solo se muestran una vez

---

## PASO 3 — Subir el código a GitHub

1. Ve a **https://github.com** → regístrate si no tienes cuenta
2. Click **"New repository"** → nombre: `video-dubber` → **Create repository**
3. En la pantalla del repo vacío, busca el botón **"uploading an existing file"**
4. Arrastra y suelta TODOS los archivos del zip que descargaste
5. Click **"Commit changes"**

---

## PASO 4 — Añadir los secrets de Modal en GitHub

1. En tu repo de GitHub → pestaña **"Settings"**
2. En el menú izquierdo → **"Secrets and variables"** → **"Actions"**
3. Click **"New repository secret"** y añade estos dos:

   | Name                | Secret (el valor)            |
   |---------------------|------------------------------|
   | `MODAL_TOKEN_ID`    | el Token ID que copiaste     |
   | `MODAL_TOKEN_SECRET`| el Token Secret que copiaste |

---

## PASO 5 — Desplegar el worker GPU en Modal (un click)

1. En tu repo de GitHub → pestaña **"Actions"**
2. En el menú izquierdo verás **"Deploy Modal GPU Worker"**
3. Click en él → click **"Run workflow"** → click el botón verde **"Run workflow"**
4. Espera ~3 minutos mientras se construye la imagen Docker con el modelo
5. Cuando termine (✅ verde), click en el job → busca en los logs una línea como:
   ```
   ✓ Created web endpoint https://TU-USUARIO--video-dubber-seamless-api-web.modal.run
   ```
6. **Copia esa URL completa**

---

## PASO 6 — Añadir la URL en Railway

1. Ve a tu proyecto en **https://railway.app**
2. Click en tu servicio → pestaña **"Variables"**
3. Añade esta variable:
   ```
   MODAL_SEAMLESS_URL = https://TU-USUARIO--video-dubber-seamless-api-web.modal.run
   ```
   (pega la URL que copiaste en el paso anterior)
4. Railway reinicia automáticamente → en ~30 segundos ya funciona

---

## ✅ Listo — tu plataforma profesional de doblaje está activa

- Railway arranca en **segundos** (ya no descarga el modelo de 10 GB)
- La primera vez que alguien dobla un video, Modal tarda ~20s en encender la GPU
- Las siguientes llamadas son inmediatas (la GPU se mantiene caliente 5 minutos)
- Cuando no hay trabajo, Modal escala a 0 → **pagas $0** en horas sin uso

---

## 💰 Costo estimado

| Servicio | Costo       | Notas                                    |
|----------|-------------|------------------------------------------|
| Railway  | Gratis      | Plan Hobby incluye suficiente            |
| Modal    | $0/mes      | $30 de crédito cubre ~200 doblajes/mes   |
| GitHub   | Gratis      | Actions gratuito para repos públicos     |

**Un doblaje de 3 minutos ≈ $0.10–0.15** en GPU.
Con $30/mes tienes 200–300 doblajes profesionales gratis.

---

## ❓ Preguntas frecuentes

**¿Qué pasa si se acaban los $30?**
Modal pide tarjeta para continuar. Mientras no la añadas, simplemente no procesa jobs GPU. El resto de la app (Railway) sigue funcionando.

**¿El modelo es bueno para producción profesional?**
Sí. SeamlessM4T v2 large es el estado del arte en speech-to-speech, el mismo que usa Meta internamente. Corre en GPU A10G (24 GB VRAM).

**¿Tengo que hacer algo cada mes?**
No. El $30 de crédito de Modal se renueva automáticamente cada mes.
