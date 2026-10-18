import { useState, useEffect } from "react";
import { Icon } from "./Icons";

const BASE = "http://127.0.0.1:5000/api";

const NAV = [
  { id:"dashboard",    label:"Tableau de bord",       icon:"dashboard" },
  { id:"historique",   label:"Historique présences",  icon:"history"   },
  { id:"matieres",     label:"Matières & Horaires",   icon:"calendar"  },
  { id:"informations", label:"Informations élèves",   icon:"users"     },
  { id:"facial",       label:"Reconnaissance faciale",icon:"face"      },
  { id:"contact",      label:"Contact Parents",       icon:"mail"      },
];

export default function Sidebar({ page, setPage }) {
  const [coursActuel, setCoursActuel] = useState(null);
  const [heure, setHeure] = useState("");

  useEffect(() => {
    const load = () =>
      fetch(`${BASE}/cours/maintenant`).then(r=>r.json())
        .then(d=>{setCoursActuel(d.cours_actuel);setHeure(d.heure);}).catch(()=>{});
    load();
    const id = setInterval(load,30000);
    return ()=>clearInterval(id);
  },[]);

  return (
    <aside style={{ background:"var(--card)", borderRight:"1px solid var(--border)", padding:"10px 8px", display:"flex", flexDirection:"column", gap:1, overflowY:"auto" }}>
      <div style={{ fontSize:9,fontWeight:600,letterSpacing:".16em",textTransform:"uppercase",color:"var(--ink3)",padding:"8px 10px 8px" }}>Navigation</div>

      {NAV.map(item => {
        const active = page === item.id;
        return (
          <button key={item.id} onClick={()=>setPage(item.id)} style={{
            display:"flex",alignItems:"center",gap:8,
            padding:"8px 10px",borderRadius:4,cursor:"pointer",
            background: active ? "var(--acc-lt)" : "transparent",
            color: active ? "var(--accent)" : "var(--ink2)",
            fontSize:13,fontWeight: active ? 600 : 400,
            border: active ? "1px solid var(--green-mid)" : "1px solid transparent",
            width:"100%",textAlign:"left",
            transition:"background .1s,color .1s",
          }}
            onMouseEnter={e=>{if(!active){e.currentTarget.style.background="var(--bg2)";e.currentTarget.style.color="var(--ink)";}}}
            onMouseLeave={e=>{if(!active){e.currentTarget.style.background="transparent";e.currentTarget.style.color="var(--ink2)";}}}
          >
            <Icon name={item.icon} size={15} color={active ? "var(--accent)" : "var(--ink3)"} />
            <span style={{flex:1}}>{item.label}</span>
            {item.id==="facial" && <span style={{width:5,height:5,borderRadius:"50%",background:"var(--accent)",flexShrink:0}} />}
          </button>
        );
      })}

      <div style={{height:1,background:"var(--border)",margin:"8px 4px"}} />

      {/* Cours actuel */}
      {coursActuel ? (
        <div style={{padding:"10px",borderRadius:4,background:"var(--green-lt)",border:"1px solid var(--green-mid)"}}>
          <div style={{fontSize:9,fontWeight:700,letterSpacing:".14em",textTransform:"uppercase",color:"var(--accent)",marginBottom:4}}>Cours actuel</div>
          <div style={{fontWeight:600,fontSize:13,color:"var(--ink)",marginBottom:2}}>{coursActuel.matiere_nom}</div>
          <div style={{fontSize:10,color:"var(--ink3)",fontFamily:"var(--font-mono)"}}>{coursActuel.heure_debut} – {coursActuel.heure_fin}</div>
          {coursActuel.salle&&<div style={{fontSize:10,color:"var(--ink3)",marginTop:1}}>{coursActuel.salle}</div>}
        </div>
      ):(
        <div style={{padding:"8px 10px",borderRadius:4,background:"var(--bg2)",border:"1px solid var(--border)",display:"flex",alignItems:"center",gap:7}}>
          <span style={{width:6,height:6,borderRadius:"50%",background:"var(--accent)",animation:"blink 2s ease-in-out infinite"}} />
          <span style={{fontSize:11,color:"var(--ink3)"}}>Système actif</span>
        </div>
      )}

      {heure&&<div style={{textAlign:"center",fontSize:15,fontWeight:600,fontFamily:"var(--font-mono)",color:"var(--ink3)",marginTop:4}}>{heure}</div>}
      <div style={{flex:1}} />

      <div style={{height:1,background:"var(--border)",margin:"6px 4px"}} />
      <button onClick={()=>setPage("apropos")} style={{display:"flex",alignItems:"center",gap:8,padding:"7px 10px",borderRadius:4,background:"transparent",color:"var(--ink3)",border:"none",width:"100%",fontSize:12,cursor:"pointer"}}
        onMouseEnter={e=>{e.currentTarget.style.background="var(--bg2)";e.currentTarget.style.color="var(--ink)"}}
        onMouseLeave={e=>{e.currentTarget.style.background="transparent";e.currentTarget.style.color="var(--ink3)"}}
      >
        <Icon name="users" size={13} color="var(--ink3)" />À propos — Équipe
      </button>
      <div style={{textAlign:"center",fontSize:9,color:"var(--ink4)",padding:"4px 0 2px",letterSpacing:".1em"}}>SFIGP v1.0 · ISPM</div>
    </aside>
  );
}
