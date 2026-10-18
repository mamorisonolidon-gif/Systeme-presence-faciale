/* Badge & Avatar — Style classique ISPM */

export const STATUS_MAP = {
  present: { label:"Présent",        bg:"var(--st-pres-bg)",  color:"var(--st-present)", dot:"var(--st-present)"  },
  late:    { label:"Retard",          bg:"var(--st-late-bg)",  color:"var(--st-late)",    dot:"var(--st-late)"    },
  absent:  { label:"Absent",          bg:"var(--st-abs-bg)",   color:"var(--st-absent)",  dot:"var(--st-absent)"  },
  unset:   { label:"Non renseigné",   bg:"var(--st-unset-bg)", color:"var(--st-unset)",   dot:"var(--st-unset)"   },
};

export function StatusBadge({ status, style = {} }) {
  const s = STATUS_MAP[status] || STATUS_MAP.unset;
  return (
    <span style={{
      display:"inline-flex", alignItems:"center", gap:5,
      padding:"2px 8px", borderRadius:4,
      fontSize:11, fontWeight:600,
      background:s.bg, color:s.color,
      border:`1px solid ${s.dot}30`,
      ...style,
    }}>
      <span style={{ width:5, height:5, borderRadius:"50%", background:s.dot, flexShrink:0 }} />
      {s.label}
    </span>
  );
}

/* Avatar : couleur unie verte (sans glow) — initiales blanches */
function hashId(id = "") {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = id.charCodeAt(i) + ((h << 5) - h);
  return Math.abs(h);
}

const GREENS = ["#1a7a4a","#145c38","#1d6b42","#22834f","#186644","#107040","#0f5c35","#196644","#1e7248","#248050"];

export function getAvatarColor(id = "") {
  return GREENS[hashId(id) % GREENS.length];
}

export function Avatar({ prenom = "", nom = "", id = "", size = 40, fontSize = 13 }) {
  const bg = getAvatarColor(id || prenom + nom);
  return (
    <div style={{
      width:size, height:size, borderRadius:"50%",
      background:bg, color:"#ffffff",
      display:"flex", alignItems:"center", justifyContent:"center",
      fontFamily:"var(--font-mono)", fontSize, fontWeight:700,
      flexShrink:0, letterSpacing:".03em",
      border:"2px solid rgba(255,255,255,.25)",
    }}>
      {(prenom[0]||"").toUpperCase()}{(nom[0]||"").toUpperCase()}
    </div>
  );
}
