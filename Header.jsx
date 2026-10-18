import { useEffect, useState } from "react";
import { Icon } from "./Icons";

const isElectron = typeof window !== "undefined" && !!window.electronAPI;

export default function Header({ user, onLogout, theme, onToggleTheme }) {
  const [clock, setClock] = useState("");

  useEffect(() => {
    const JOURS = ["Dim","Lun","Mar","Mer","Jeu","Ven","Sam"];
    const MOIS  = ["jan","fév","mar","avr","mai","jun","jul","aoû","sep","oct","nov","déc"];
    const tick = () => {
      const now = new Date();
      const p = n => String(n).padStart(2,"0");
      setClock(`${JOURS[now.getDay()]} ${now.getDate()} ${MOIS[now.getMonth()]} ${p(now.getHours())}:${p(now.getMinutes())}:${p(now.getSeconds())}`);
    };
    tick(); const id = setInterval(tick,1000); return () => clearInterval(id);
  }, []);

  const initiales = user ? (user.prenom[0]+user.nom[0]).toUpperCase() : "??";

  return (
    <header style={{
      gridColumn:"1 / -1", height:52,
      background:"var(--accent)",
      display:"flex", alignItems:"center",
      padding:"0 16px", gap:10,
      position:"sticky", top:0, zIndex:100,
      WebkitAppRegion: isElectron ? "drag" : "no-drag",
    }}>
      {/* Logo */}
      <div style={{ display:"flex", alignItems:"center", gap:10, WebkitAppRegion:"no-drag" }}>
        {window._ISPM_LOGO_B64 && (
          <img src={window._ISPM_LOGO_B64} alt="ISPM" style={{ width:34,height:34,borderRadius:"50%",objectFit:"cover",border:"2px solid rgba(255,255,255,.4)" }} />
        )}
        <div>
          <div style={{ fontWeight:700, fontSize:16, color:"#ffffff", letterSpacing:".04em", lineHeight:1 }}>SFIGP</div>
          <div style={{ fontSize:9, color:"rgba(255,255,255,.75)", letterSpacing:".15em" }}>IGGLIA 3B · ISPM</div>
        </div>
      </div>

      <div style={{ flex:1 }} />

      {/* Horloge */}
      <span style={{ fontSize:11, color:"rgba(255,255,255,.85)", fontFamily:"var(--font-mono)", WebkitAppRegion:"no-drag" }}>{clock}</span>

      {/* Thème */}
      <button onClick={onToggleTheme} title="Changer le thème" style={{
        WebkitAppRegion:"no-drag", width:30,height:30,padding:0,
        borderRadius:4, border:"1px solid rgba(255,255,255,.3)",
        background:"rgba(255,255,255,.1)", color:"#fff",
        display:"flex",alignItems:"center",justifyContent:"center",cursor:"pointer",
      }}>
        {theme==="dark"
          ? <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
          : <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
        }
      </button>

      {/* Profil */}
      {user && (
        <div style={{ WebkitAppRegion:"no-drag", display:"flex",alignItems:"center",gap:8,padding:"4px 10px 4px 6px",borderRadius:4,background:"rgba(255,255,255,.12)",border:"1px solid rgba(255,255,255,.2)" }}>
          <div style={{ width:26,height:26,borderRadius:"50%",background:"rgba(255,255,255,.25)",display:"flex",alignItems:"center",justifyContent:"center",fontSize:10,fontWeight:700,color:"#fff",fontFamily:"var(--font-mono)" }}>{initiales}</div>
          <div>
            <div style={{ fontSize:12,fontWeight:600,color:"#fff",lineHeight:1.2 }}>{user.prenom} {user.nom}</div>
            <div style={{ fontSize:10,color:"rgba(255,255,255,.7)" }}>{user.email}</div>
          </div>
        </div>
      )}

      {/* Déconnexion */}
      <button onClick={onLogout} title="Déconnexion" style={{ WebkitAppRegion:"no-drag",width:30,height:30,padding:0,borderRadius:4,border:"1px solid rgba(255,255,255,.3)",background:"rgba(255,255,255,.1)",color:"#fff",display:"flex",alignItems:"center",justifyContent:"center",cursor:"pointer",marginRight:isElectron?4:0 }}
        onMouseEnter={e=>{e.currentTarget.style.background="rgba(220,38,38,.5)"}}
        onMouseLeave={e=>{e.currentTarget.style.background="rgba(255,255,255,.1)"}}
      >
        <Icon name="power" size={13} color="white" />
      </button>

      {isElectron && (
        <div style={{ display:"flex",height:"100%",WebkitAppRegion:"no-drag",borderLeft:"1px solid rgba(255,255,255,.15)",marginLeft:4 }}>
          {[{a:()=>window.electronAPI.minimize(),l:"—"},{a:()=>window.electronAPI.maximize(),l:"□"},{a:()=>window.electronAPI.close(),l:"✕",c:true}].map((b,i)=>(
            <button key={i} onClick={b.a} style={{ width:38,height:"100%",border:"none",background:"transparent",color:"rgba(255,255,255,.8)",fontSize:12,cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center" }}
              onMouseEnter={e=>e.currentTarget.style.background=b.c?"rgba(220,38,38,.5)":"rgba(255,255,255,.1)"}
              onMouseLeave={e=>e.currentTarget.style.background="transparent"}
            >{b.l}</button>
          ))}
        </div>
      )}
    </header>
  );
}
