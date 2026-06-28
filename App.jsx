import { useState, useEffect, useRef, useCallback } from "react";

// ═══════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════
const STEP_GROUPS = {
  import: {
    label: "Importación",
    steps: ["separate_av", "prepare_media", "transcode"],
  },
  transcription: {
    label: "Transcripción",
    steps: ["separate_voice", "generate_subs", "prepare_voices"],
  },
  analysis: {
    label: "Análisis",
    steps: ["prepare_analysis", "analyze_voices"],
  },
  translation: {
    label: "Traducción",
    steps: [], // dynamic
  },
};

const STEP_LABELS = {
  separate_av: "Separando audio y video",
  prepare_media: "Preparando medio",
  transcode: "Transcodificando medio",
  separate_voice: "Separando voz del fondo",
  generate_subs: "Generando subtítulos fuente",
  prepare_voices: "Preparando voces separadas",
  prepare_analysis: "Preparando voces para análisis",
  analyze_voices: "Analizando voces",
};

const LANGUAGES = [
  { code: "es", name: "Spanish (MX)", flag: "🇲🇽" },
  { code: "en", name: "English", flag: "🇺🇸" },
  { code: "pt", name: "Portuguese (BR)", flag: "🇧🇷" },
  { code: "fr", name: "French", flag: "🇫🇷" },
  { code: "de", name: "German", flag: "🇩🇪" },
  { code: "ja", name: "Japanese", flag: "🇯🇵" },
  { code: "ko", name: "Korean", flag: "🇰🇷" },
  { code: "zh", name: "Chinese", flag: "🇨🇳" },
  { code: "it", name: "Italian", flag: "🇮🇹" },
  { code: "ru", name: "Russian", flag: "🇷🇺" },
  { code: "ar", name: "Arabic", flag: "🇸🇦" },
  { code: "hi", name: "Hindi", flag: "🇮🇳" },
];

// ═══════════════════════════════════════════════════════════════════════
// MOCK PIPELINE SIMULATOR (dev mode when no backend)
// ═══════════════════════════════════════════════════════════════════════
function createMockJob(filename, targetLangs) {
  const allSteps = [
    { key: "separate_av", group: "import", label: "Separando audio y video" },
    { key: "prepare_media", group: "import", label: "Preparando medio" },
    { key: "transcode", group: "import", label: "Transcodificando medio" },
    { key: "separate_voice", group: "transcription", label: "Separando voz del fondo" },
    { key: "generate_subs", group: "transcription", label: "Generando subtítulos fuente" },
    { key: "prepare_voices", group: "transcription", label: "Preparando voces separadas" },
    { key: "prepare_analysis", group: "analysis", label: "Preparando voces para análisis" },
    { key: "analyze_voices", group: "analysis", label: "Analizando voces" },
    ...targetLangs.flatMap(lang => {
      const l = LANGUAGES.find(l => l.code === lang);
      const name = l ? l.name : lang;
      return [
        { key: `request_dub_${lang}`, group: "translation", label: `Solicitando doblaje (${name})` },
        { key: `translate_dub_${lang}`, group: "translation", label: `Traduciendo y doblando (${name})` },
      ];
    }),
  ];

  const steps = {};
  allSteps.forEach(s => {
    steps[s.key] = { label: s.label, status: "pending", group: s.group };
  });

  return {
    id: "mock-" + Date.now(),
    filename,
    status: "processing",
    progress: 0,
    current_step: null,
    steps,
    groups: {
      import: { label: "Importación", status: "pending" },
      transcription: { label: "Transcripción", status: "pending" },
      analysis: { label: "Análisis", status: "pending" },
      translation: { label: "Traducción", status: "pending" },
    },
    allStepKeys: allSteps.map(s => s.key),
    target_languages: targetLangs,
  };
}

async function* simulatePipeline(job) {
  const { allStepKeys } = job;
  const stepDurations = {
    separate_av: 1200, prepare_media: 800, transcode: 1500,
    separate_voice: 2500, generate_subs: 3000, prepare_voices: 1200,
    prepare_analysis: 1000, analyze_voices: 2000,
  };

  let currentJob = { ...job, steps: { ...job.steps }, groups: { ...job.groups } };
  
  // Group tracking
  const groupForStep = {};
  Object.values(currentJob.steps).forEach(s => {
    groupForStep[s.label] = s.group;
  });

  for (let i = 0; i < allStepKeys.length; i++) {
    const key = allStepKeys[i];
    const step = currentJob.steps[key];
    if (!step) continue;

    const group = step.group;
    const duration = stepDurations[key] || 1800;

    // Mark group running
    currentJob = {
      ...currentJob,
      steps: { ...currentJob.steps, [key]: { ...step, status: "running" } },
      groups: {
        ...currentJob.groups,
        [group]: { ...currentJob.groups[group], status: "running" }
      },
      current_step: key,
    };
    yield { ...currentJob };
    await new Promise(r => setTimeout(r, duration));

    // Mark step complete
    const completed = i + 1;
    const total = allStepKeys.length;
    currentJob = {
      ...currentJob,
      steps: { ...currentJob.steps, [key]: { ...step, status: "complete" } },
      progress: Math.round((completed / total) * 95),
    };

    // Check if group is done
    const groupSteps = allStepKeys.filter(k => currentJob.steps[k]?.group === group);
    const groupDone = groupSteps.every(k => currentJob.steps[k]?.status === "complete" || k === key);
    if (groupDone) {
      currentJob = {
        ...currentJob,
        groups: {
          ...currentJob.groups,
          [group]: { ...currentJob.groups[group], status: "complete" }
        }
      };
    }
    yield { ...currentJob };
  }

  yield {
    ...currentJob,
    status: "completed",
    progress: 100,
    outputs: Object.fromEntries(
      (job.target_languages || ["es"]).map(l => [l, `mock_output_${l}.mp4`])
    )
  };
}

// ═══════════════════════════════════════════════════════════════════════
// ICONS
// ═══════════════════════════════════════════════════════════════════════
const CheckIcon = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <path d="M2.5 7L5.5 10L11.5 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

const SpinnerIcon = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="spin">
    <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.5" strokeOpacity="0.25"/>
    <path d="M12.5 7A5.5 5.5 0 0 1 7 12.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
);

const UploadIcon = () => (
  <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
    <path d="M16 4L16 20M16 4L10 10M16 4L22 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M6 24H26" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
    <path d="M4 28H28" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeOpacity="0.4"/>
  </svg>
);

const VideoIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
    <rect x="1" y="3" width="12" height="14" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M13 8L19 5V15L13 12" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
  </svg>
);

const ClaudeIcon = () => (
  <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
    <circle cx="11" cy="11" r="10" fill="currentColor" fillOpacity="0.12"/>
    <path d="M6 14.5C7.5 12 9.5 9 11 7C12.5 9 14.5 12 16 14.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M7.5 12H14.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
);

// ═══════════════════════════════════════════════════════════════════════
// STEP ROW COMPONENT
// ═══════════════════════════════════════════════════════════════════════
function StepRow({ label, status }) {
  return (
    <div className={`step-row step-${status}`}>
      <div className="step-indicator">
        {status === "complete" && <CheckIcon />}
        {status === "running" && <SpinnerIcon />}
        {status === "pending" && <div className="step-dot" />}
      </div>
      <span className="step-label">{label}</span>
      {status === "complete" && <span className="step-badge">complete</span>}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// GROUP PANEL COMPONENT
// ═══════════════════════════════════════════════════════════════════════
function GroupPanel({ groupKey, groupInfo, steps, allSteps }) {
  const groupSteps = Object.entries(allSteps)
    .filter(([_, s]) => s.group === groupKey)
    .map(([key, s]) => ({ key, ...s }));

  if (groupSteps.length === 0) return null;

  const isActive = groupInfo.status === "running" || 
    groupSteps.some(s => s.status === "running" || s.status === "complete");

  return (
    <div className={`group-panel ${groupInfo.status === "complete" ? "group-done" : ""} ${isActive ? "group-active" : ""}`}>
      <div className="group-header">
        <span className="group-label">{groupInfo.label}</span>
        <div className="group-status-row">
          {groupSteps.map(step => (
            <div
              key={step.key}
              className={`group-dot ${step.status}`}
              title={step.label}
            />
          ))}
        </div>
      </div>
      <div className="group-steps">
        {groupSteps.map(step => (
          <StepRow key={step.key} label={step.label} status={step.status} />
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// LANGUAGE SELECTOR
// ═══════════════════════════════════════════════════════════════════════
function LanguageSelector({ selected, onChange }) {
  return (
    <div className="lang-grid">
      {LANGUAGES.map(lang => (
        <button
          key={lang.code}
          className={`lang-chip ${selected.includes(lang.code) ? "lang-selected" : ""}`}
          onClick={() => {
            if (selected.includes(lang.code)) {
              onChange(selected.filter(c => c !== lang.code));
            } else {
              onChange([...selected, lang.code]);
            }
          }}
        >
          <span className="lang-flag">{lang.flag}</span>
          <span className="lang-name">{lang.name}</span>
          {selected.includes(lang.code) && (
            <span className="lang-check"><CheckIcon /></span>
          )}
        </button>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// PROGRESS BAR
// ═══════════════════════════════════════════════════════════════════════
function ProgressBar({ progress, status }) {
  return (
    <div className="progress-track">
      <div
        className={`progress-fill ${status === "completed" ? "progress-done" : ""}`}
        style={{ width: `${progress}%` }}
      />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// MAIN APP
// ═══════════════════════════════════════════════════════════════════════
export default function App() {
  const [phase, setPhase] = useState("upload"); // upload | config | processing | done
  const [file, setFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [selectedLangs, setSelectedLangs] = useState(["es"]);
  const [jobState, setJobState] = useState(null);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);
  const apiBase = import.meta.env.VITE_API_URL || "";

  const handleFile = useCallback((f) => {
    if (!f) return;
    const valid = ["video/mp4", "video/mpeg", "video/webm", "video/quicktime"];
    if (!valid.includes(f.type) && !f.name.match(/\.(mp4|mov|avi|webm|mkv)$/i)) {
      setError("Formato no soportado. Usa MP4, MOV, AVI o WebM.");
      return;
    }
    setFile(f);
    setError(null);
    setPhase("config");
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    handleFile(f);
  }, [handleFile]);

  const startProcessing = async () => {
    if (!file || selectedLangs.length === 0) return;
    setPhase("processing");
    setError(null);

    const mockJob = createMockJob(file.name, selectedLangs);
    setJobState(mockJob);

    // Try real API first, fall back to mock
    try {
      if (apiBase) {
        // Real API path
        const fd = new FormData();
        fd.append("file", file);
        const uploadRes = await fetch(`${apiBase}/jobs/upload`, { method: "POST", body: fd });
        if (!uploadRes.ok) throw new Error("Upload failed");
        const { job_id } = await uploadRes.json();

        await fetch(`${apiBase}/jobs/${job_id}/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(selectedLangs),
        });

        // SSE stream
        const sse = new EventSource(`${apiBase}/jobs/${job_id}/stream`);
        sse.onmessage = (e) => {
          const data = JSON.parse(e.data);
          setJobState(data);
          if (data.status === "completed" || data.status === "error") {
            sse.close();
            if (data.status === "completed") setPhase("done");
            if (data.status === "error") setError(data.error);
          }
        };
        return;
      }
    } catch (e) {
      // Fall through to mock
    }

    // Mock simulation
    for await (const state of simulatePipeline(mockJob)) {
      setJobState({ ...state });
      if (state.status === "completed") {
        setPhase("done");
        break;
      }
    }
  };

  const reset = () => {
    setFile(null);
    setJobState(null);
    setSelectedLangs(["es"]);
    setError(null);
    setPhase("upload");
  };

  // Group order
  const groupOrder = ["import", "transcription", "analysis", "translation"];

  return (
    <>
      <style>{CSS}</style>
      <div className="app">
        {/* Header */}
        <header className="header">
          <div className="header-inner">
            <div className="logo">
              <ClaudeIcon />
              <span className="logo-text">VideoDubber</span>
              <span className="logo-badge">XTTS2</span>
            </div>
            <nav className="nav">
              <a href="#" className="nav-link">Docs</a>
              <a href="https://github.com" className="nav-link">GitHub</a>
            </nav>
          </div>
        </header>

        <main className="main">
          {/* ── UPLOAD PHASE ── */}
          {phase === "upload" && (
            <div className="center-layout">
              <div className="hero">
                <h1 className="hero-title">
                  Dobla videos con IA,<br />preservando tu voz.
                </h1>
                <p className="hero-sub">
                  XTTS2 clona la voz original y la adapta a cualquier idioma con sincronía perfecta.
                </p>
              </div>

              <div
                className={`dropzone ${dragOver ? "dropzone-active" : ""}`}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="video/*"
                  style={{ display: "none" }}
                  onChange={(e) => handleFile(e.target.files[0])}
                />
                <div className="drop-icon">
                  <UploadIcon />
                </div>
                <p className="drop-title">Arrastra tu video aquí</p>
                <p className="drop-sub">o haz clic para seleccionar</p>
                <p className="drop-formats">MP4 · MOV · AVI · WebM · hasta 4GB</p>
              </div>

              {error && <div className="error-banner">{error}</div>}

              <div className="features">
                {["Clonación de voz con XTTS2", "Separación de audio con Demucs", "Transcripción con Whisper", "16+ idiomas soportados"].map(f => (
                  <div key={f} className="feature-chip">
                    <CheckIcon /> {f}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── CONFIG PHASE ── */}
          {phase === "config" && file && (
            <div className="center-layout">
              <div className="file-card">
                <div className="file-icon"><VideoIcon /></div>
                <div className="file-info">
                  <span className="file-name">{file.name}</span>
                  <span className="file-size">{(file.size / 1024 / 1024).toFixed(1)} MB</span>
                </div>
                <button className="file-remove" onClick={reset}>✕</button>
              </div>

              <div className="section">
                <h2 className="section-title">Idiomas de destino</h2>
                <p className="section-sub">Selecciona uno o más idiomas para doblar</p>
                <LanguageSelector selected={selectedLangs} onChange={setSelectedLangs} />
              </div>

              <div className="action-row">
                <button className="btn-ghost" onClick={reset}>Cancelar</button>
                <button
                  className="btn-primary"
                  disabled={selectedLangs.length === 0}
                  onClick={startProcessing}
                >
                  Iniciar doblaje
                  {selectedLangs.length > 0 && (
                    <span className="btn-badge">{selectedLangs.length}</span>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* ── PROCESSING PHASE ── */}
          {phase === "processing" && jobState && (
            <div className="processing-layout">
              <div className="processing-header">
                <div className="file-card compact">
                  <div className="file-icon"><VideoIcon /></div>
                  <div className="file-info">
                    <span className="file-name">{jobState.filename}</span>
                    <span className="file-size">
                      {selectedLangs.map(l => LANGUAGES.find(x => x.code === l)?.flag).join(" ")}
                      {" · "}{selectedLangs.length} idioma{selectedLangs.length > 1 ? "s" : ""}
                    </span>
                  </div>
                </div>
                <div className="progress-info">
                  <span className="progress-pct">{jobState.progress}%</span>
                </div>
              </div>

              <ProgressBar progress={jobState.progress} status={jobState.status} />

              <div className="pipeline">
                {groupOrder.map(gKey => {
                  const groupInfo = jobState.groups?.[gKey];
                  if (!groupInfo) return null;
                  return (
                    <GroupPanel
                      key={gKey}
                      groupKey={gKey}
                      groupInfo={groupInfo}
                      steps={[]}
                      allSteps={jobState.steps || {}}
                    />
                  );
                })}
              </div>
            </div>
          )}

          {/* ── DONE PHASE ── */}
          {phase === "done" && jobState && (
            <div className="center-layout done-layout">
              <div className="done-icon">
                <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                  <circle cx="24" cy="24" r="22" fill="var(--accent)" fillOpacity="0.12"/>
                  <path d="M14 24L21 31L34 17" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <h2 className="done-title">¡Doblaje completado!</h2>
              <p className="done-sub">{jobState.filename} está listo en {selectedLangs.length} idioma{selectedLangs.length > 1 ? "s" : ""}.</p>

              <div className="download-list">
                {selectedLangs.map(lang => {
                  const l = LANGUAGES.find(x => x.code === lang);
                  return (
                    <div key={lang} className="download-item">
                      <span className="dl-flag">{l?.flag}</span>
                      <span className="dl-name">{l?.name}</span>
                      <a
                        href={apiBase ? `${apiBase}/jobs/${jobState.id}/download/${lang}` : "#"}
                        className="btn-download"
                        download
                      >
                        Descargar
                      </a>
                    </div>
                  );
                })}
              </div>

              <button className="btn-ghost" onClick={reset}>Procesar otro video</button>
            </div>
          )}
        </main>
      </div>
    </>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// STYLES — Claude Design System
// ═══════════════════════════════════════════════════════════════════════
const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;450;500;600&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #F9F8F6;
    --surface: #FFFFFF;
    --surface-2: #F5F4F2;
    --surface-3: #EFEEEC;
    --border: #E8E7E4;
    --border-strong: #D4D3CF;
    --text: #1A1917;
    --text-2: #6B6966;
    --text-3: #9B9895;
    --accent: #CC7832;
    --accent-bg: #FFF4EC;
    --accent-border: #F0CBA8;
    --green: #2D7D46;
    --green-bg: #EAF6EE;
    --blue: #1A6FBF;
    --blue-bg: #EAF2FC;
    --radius-sm: 6px;
    --radius: 10px;
    --radius-lg: 14px;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
    --shadow: 0 4px 12px rgba(0,0,0,0.07), 0 1px 3px rgba(0,0,0,0.05);
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', -apple-system, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }

  /* ── HEADER ── */
  .header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    position: sticky; top: 0; z-index: 100;
    backdrop-filter: blur(8px);
  }
  .header-inner {
    max-width: 860px; margin: 0 auto;
    padding: 0 24px;
    height: 52px;
    display: flex; align-items: center; justify-content: space-between;
  }
  .logo {
    display: flex; align-items: center; gap: 8px;
    color: var(--text);
  }
  .logo-text {
    font-weight: 600; font-size: 15px; letter-spacing: -0.3px;
  }
  .logo-badge {
    background: var(--accent-bg);
    color: var(--accent);
    border: 1px solid var(--accent-border);
    border-radius: 4px;
    font-size: 10px; font-weight: 600;
    padding: 1px 5px; letter-spacing: 0.3px;
  }
  .nav { display: flex; gap: 4px; }
  .nav-link {
    color: var(--text-2); text-decoration: none;
    padding: 5px 10px; border-radius: var(--radius-sm);
    font-size: 13px; font-weight: 450;
    transition: all 0.12s;
  }
  .nav-link:hover { color: var(--text); background: var(--surface-2); }

  /* ── MAIN ── */
  .main { min-height: calc(100vh - 52px); padding: 40px 24px 80px; }
  .center-layout {
    max-width: 560px; margin: 0 auto;
    display: flex; flex-direction: column; gap: 24px;
  }
  .processing-layout {
    max-width: 620px; margin: 0 auto;
    display: flex; flex-direction: column; gap: 16px;
  }

  /* ── HERO ── */
  .hero { text-align: center; padding: 8px 0 4px; }
  .hero-title {
    font-size: 28px; font-weight: 600; letter-spacing: -0.7px; line-height: 1.2;
    color: var(--text);
  }
  .hero-sub {
    margin-top: 10px; color: var(--text-2); font-size: 15px; line-height: 1.6;
  }

  /* ── DROPZONE ── */
  .dropzone {
    background: var(--surface);
    border: 1.5px dashed var(--border-strong);
    border-radius: var(--radius-lg);
    padding: 48px 32px;
    text-align: center;
    cursor: pointer;
    transition: all 0.15s;
    display: flex; flex-direction: column; align-items: center; gap: 8px;
  }
  .dropzone:hover, .dropzone-active {
    border-color: var(--accent);
    background: var(--accent-bg);
  }
  .drop-icon { color: var(--text-3); margin-bottom: 4px; }
  .dropzone:hover .drop-icon, .dropzone-active .drop-icon { color: var(--accent); }
  .drop-title { font-size: 15px; font-weight: 500; color: var(--text); }
  .drop-sub { color: var(--text-2); font-size: 13px; }
  .drop-formats {
    margin-top: 4px;
    font-size: 11px; color: var(--text-3); letter-spacing: 0.3px;
  }

  /* ── FEATURES ── */
  .features { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
  .feature-chip {
    display: flex; align-items: center; gap: 6px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 20px; padding: 5px 12px;
    font-size: 12px; color: var(--text-2); font-weight: 450;
  }
  .feature-chip svg { color: var(--green); }

  /* ── FILE CARD ── */
  .file-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px 16px;
    display: flex; align-items: center; gap: 12px;
    box-shadow: var(--shadow-sm);
  }
  .file-card.compact { padding: 10px 14px; }
  .file-icon { color: var(--text-2); flex-shrink: 0; }
  .file-info { flex: 1; min-width: 0; }
  .file-name {
    display: block; font-size: 14px; font-weight: 500;
    color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .file-size { font-size: 12px; color: var(--text-3); }
  .file-remove {
    background: none; border: none; cursor: pointer;
    color: var(--text-3); padding: 4px 8px; border-radius: 4px;
    font-size: 14px; transition: all 0.1s;
  }
  .file-remove:hover { color: var(--text); background: var(--surface-2); }

  /* ── SECTION ── */
  .section { display: flex; flex-direction: column; gap: 12px; }
  .section-title { font-size: 15px; font-weight: 600; letter-spacing: -0.2px; }
  .section-sub { font-size: 13px; color: var(--text-2); margin-top: -4px; }

  /* ── LANGUAGE GRID ── */
  .lang-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 8px; }
  .lang-chip {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 9px 12px;
    display: flex; align-items: center; gap: 8px;
    cursor: pointer; text-align: left;
    transition: all 0.12s; font-size: 13px;
  }
  .lang-chip:hover { border-color: var(--accent); background: var(--accent-bg); }
  .lang-selected {
    border-color: var(--accent) !important;
    background: var(--accent-bg) !important;
  }
  .lang-flag { font-size: 18px; flex-shrink: 0; }
  .lang-name { flex: 1; font-weight: 450; color: var(--text); font-size: 12px; }
  .lang-check { color: var(--accent); flex-shrink: 0; }

  /* ── BUTTONS ── */
  .action-row { display: flex; gap: 10px; justify-content: flex-end; }
  .btn-primary {
    background: var(--text); color: #fff;
    border: none; border-radius: var(--radius-sm);
    padding: 9px 20px; font-size: 14px; font-weight: 500;
    cursor: pointer; display: flex; align-items: center; gap: 8px;
    transition: all 0.12s; letter-spacing: -0.2px;
  }
  .btn-primary:hover { background: #2D2C2A; }
  .btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
  .btn-badge {
    background: rgba(255,255,255,0.2); border-radius: 10px;
    font-size: 11px; padding: 1px 6px; font-weight: 600;
  }
  .btn-ghost {
    background: none; border: 1px solid var(--border);
    color: var(--text-2); border-radius: var(--radius-sm);
    padding: 9px 16px; font-size: 14px; cursor: pointer;
    transition: all 0.12s; font-weight: 450;
  }
  .btn-ghost:hover { border-color: var(--border-strong); color: var(--text); }
  .btn-download {
    background: var(--green-bg); color: var(--green);
    border: 1px solid rgba(45,125,70,0.2);
    border-radius: var(--radius-sm); padding: 6px 14px;
    font-size: 12px; font-weight: 500;
    text-decoration: none; cursor: pointer;
    transition: all 0.12s;
  }
  .btn-download:hover { background: var(--green); color: #fff; }

  /* ── PROGRESS ── */
  .progress-info { display: flex; align-items: center; }
  .progress-pct { font-size: 13px; font-weight: 600; color: var(--text-2); }
  .processing-header { display: flex; align-items: center; gap: 12px; }
  .processing-header .file-card { flex: 1; }
  .progress-track {
    height: 3px; background: var(--border);
    border-radius: 2px; overflow: hidden;
  }
  .progress-fill {
    height: 100%; background: var(--accent);
    border-radius: 2px;
    transition: width 0.4s ease;
  }
  .progress-done { background: var(--green); }

  /* ── PIPELINE GROUPS ── */
  .pipeline { display: flex; flex-direction: column; gap: 8px; }
  .group-panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    transition: all 0.2s;
  }
  .group-active { border-color: var(--border-strong); box-shadow: var(--shadow-sm); }
  .group-done { opacity: 0.7; }

  .group-header {
    padding: 10px 14px;
    display: flex; align-items: center; justify-content: space-between;
    border-bottom: 1px solid var(--border);
    background: var(--surface-2);
  }
  .group-label { font-size: 11px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; color: var(--text-2); }
  .group-status-row { display: flex; gap: 4px; }
  .group-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--border);
    transition: background 0.2s;
  }
  .group-dot.running { background: var(--accent); }
  .group-dot.complete { background: var(--green); }
  .group-dot.pending { background: var(--border); }

  .group-steps { padding: 4px 0; }

  /* ── STEP ROW ── */
  .step-row {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 14px;
    transition: background 0.1s;
  }
  .step-row:hover { background: var(--surface-2); }
  .step-pending .step-indicator { color: var(--text-3); }
  .step-running .step-indicator { color: var(--accent); }
  .step-complete .step-indicator { color: var(--green); }

  .step-indicator {
    width: 18px; height: 18px;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
  }
  .step-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--border);
  }
  .step-label {
    flex: 1; font-size: 13px; color: var(--text);
  }
  .step-pending .step-label { color: var(--text-3); }
  .step-running .step-label { color: var(--text); font-weight: 450; }
  .step-badge {
    font-size: 10px; font-weight: 500;
    color: var(--green);
    background: var(--green-bg);
    border: 1px solid rgba(45,125,70,0.15);
    border-radius: 4px; padding: 1px 6px;
    letter-spacing: 0.2px;
  }

  /* ── DONE ── */
  .done-layout { align-items: center; text-align: center; }
  .done-icon { margin-bottom: 4px; }
  .done-title { font-size: 22px; font-weight: 600; letter-spacing: -0.5px; }
  .done-sub { color: var(--text-2); font-size: 14px; }
  .download-list {
    width: 100%; background: var(--surface);
    border: 1px solid var(--border); border-radius: var(--radius);
    overflow: hidden; box-shadow: var(--shadow-sm);
  }
  .download-item {
    display: flex; align-items: center; gap: 12px;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
  }
  .download-item:last-child { border-bottom: none; }
  .dl-flag { font-size: 20px; }
  .dl-name { flex: 1; font-size: 13px; font-weight: 450; color: var(--text); }

  /* ── ERROR ── */
  .error-banner {
    background: #FEF2F2; border: 1px solid #FECACA;
    color: #DC2626; border-radius: var(--radius-sm);
    padding: 10px 14px; font-size: 13px;
  }

  /* ── SPINNER ── */
  @keyframes spin { to { transform: rotate(360deg); } }
  .spin { animation: spin 0.8s linear infinite; }
`;
