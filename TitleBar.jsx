import { useState, useEffect } from "react";

// Détection Electron
const isElectron = typeof window !== "undefined" && window.electronAPI?.isElectron;

export default function TitleBar() {
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    if (!isElectron) return;
    const check = async () => {
      const m = await window.electronAPI.isMaximized();
      setMaximized(m);
    };
    check();
    const id = setInterval(check, 500);
    return () => clearInterval(id);
  }, []);

  if (!isElectron) return null;

  const btnBase = {
    width: 46, height: 32,
    border: "none", background: "transparent",
    display: "flex", alignItems: "center", justifyContent: "center",
    cursor: "pointer", transition: "background .15s",
    flexShrink: 0,
  };

  return (
    <div style={{
      position: "fixed", top: 0, left: 0, right: 0, height: 32,
      background: "var(--card)",
      borderBottom: "1px solid var(--border)",
      display: "flex", alignItems: "center",
      zIndex: 9999,
      WebkitAppRegion: "drag",
      userSelect: "none",
    }}>
      {/* Zone draggable + titre */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", paddingLeft: 16, gap: 8 }}>
        {/* Icône mini */}
        <div style={{ width: 16, height: 16, borderRadius: 4, background: "linear-gradient(135deg, var(--accent), var(--acc-dk))", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round">
            <path d="M9 10h.01"/><path d="M15 10h.01"/><path d="M9.5 15a3.5 3.5 0 0 0 5 0"/>
          </svg>
        </div>
        <span style={{ fontSize: 11, fontWeight: 600, color: "var(--ink3)", letterSpacing: ".04em" }}>
          FaceAttend — IGGLIA 3B
        </span>
      </div>

      {/* Boutons fenêtre — pas draggable */}
      <div style={{ display: "flex", WebkitAppRegion: "no-drag" }}>
        {/* Minimiser */}
        <button
          onClick={() => window.electronAPI.minimize()}
          title="Minimiser"
          style={{ ...btnBase, color: "var(--ink3)" }}
          onMouseEnter={e => e.currentTarget.style.background = "var(--bg3)"}
          onMouseLeave={e => e.currentTarget.style.background = "transparent"}
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
        </button>

        {/* Maximiser / Restaurer */}
        <button
          onClick={async () => { await window.electronAPI.maximize(); const m = await window.electronAPI.isMaximized(); setMaximized(m); }}
          title={maximized ? "Restaurer" : "Maximiser"}
          style={{ ...btnBase, color: "var(--ink3)" }}
          onMouseEnter={e => e.currentTarget.style.background = "var(--bg3)"}
          onMouseLeave={e => e.currentTarget.style.background = "transparent"}
        >
          {maximized ? (
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="6" y="6" width="12" height="12" rx="1"/>
              <path d="M4 4h6v2H6v6H4V4z" fill="currentColor" stroke="none"/>
            </svg>
          ) : (
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="4" y="4" width="16" height="16" rx="1"/>
            </svg>
          )}
        </button>

        {/* Fermer */}
        <button
          onClick={() => window.electronAPI.close()}
          title="Fermer"
          style={{ ...btnBase, color: "var(--ink3)", borderTopRightRadius: 0 }}
          onMouseEnter={e => { e.currentTarget.style.background = "#e81123"; e.currentTarget.style.color = "#fff"; }}
          onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--ink3)"; }}
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </div>
  );
}
