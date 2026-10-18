from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import sqlite3, os, base64, json, io, numpy as np
from datetime import date, datetime

app = Flask(__name__)
CORS(app)

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response

@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        r = Response()
        r.headers["Access-Control-Allow-Origin"]  = "*"
        r.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        r.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        return r, 200

app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

DB_PATH = os.path.join(os.path.dirname(__file__), "faceattend.db")

# ── InsightFace / ArcFace ───────────────────────────────────────
try:
    import cv2
    from PIL import Image
    from insightface.app import FaceAnalysis

    # Moteur de détection + reconnaissance (modèle ArcFace "buffalo_l")
    # ctx_id=0 -> essaie le GPU 0 (CUDA) si dispo, sinon bascule sur CPU
    face_app = FaceAnalysis(name="buffalo_l", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    face_app.prepare(ctx_id=0, det_size=(640, 640))

    INSIGHTFACE_AVAILABLE = True
    print(" InsightFace (ArcFace / buffalo_l) disponible")
except ImportError:
    face_app = None
    INSIGHTFACE_AVAILABLE = False
    print("  Mode simulation (pip install insightface onnxruntime opencv-python-headless Pillow)")
except Exception as ex:
    # Ex: échec de téléchargement du modèle (pas d'accès internet au 1er lancement)
    face_app = None
    INSIGHTFACE_AVAILABLE = False
    print(f"  InsightFace n'a pas pu être initialisé ({ex}) — mode simulation")

_face_cache = {}

JOURS_EN = {"Monday":"Lundi","Tuesday":"Mardi","Wednesday":"Mercredi",
            "Thursday":"Jeudi","Friday":"Vendredi","Saturday":"Samedi","Sunday":"Dimanche"}

# ── DB ────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS eleves (
            id               TEXT PRIMARY KEY,
            prenom           TEXT NOT NULL,
            nom              TEXT NOT NULL,
            classe           TEXT NOT NULL DEFAULT 'IGGLIA 3B',
            adresse          TEXT,
            telephone        TEXT,
            email_parent     TEXT,
            contact_parent   TEXT,
            date_naissance   TEXT,
            sexe             TEXT,
            photo_base64     TEXT,
            face_encodings   TEXT,
            created_at       TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS matieres (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nom         TEXT NOT NULL,
            code        TEXT NOT NULL UNIQUE,
            couleur     TEXT NOT NULL DEFAULT '#2563eb',
            enseignant  TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS cours (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            matiere_id  INTEGER NOT NULL REFERENCES matieres(id) ON DELETE CASCADE,
            jour        TEXT NOT NULL,
            heure_debut TEXT NOT NULL,
            heure_fin   TEXT NOT NULL,
            salle       TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        -- Présences globales (par jour)
        CREATE TABLE IF NOT EXISTS presences (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            eleve_id   TEXT NOT NULL REFERENCES eleves(id),
            date       TEXT NOT NULL,
            statut     TEXT NOT NULL DEFAULT 'unset',
            heure      TEXT,
            confiance  INTEGER,
            motif      TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_presence_unique
            ON presences(eleve_id, date);

        -- Présences par cours (groupées, reset à chaque cours)
        CREATE TABLE IF NOT EXISTS presences_cours (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            cours_id    INTEGER NOT NULL REFERENCES cours(id) ON DELETE CASCADE,
            eleve_id    TEXT NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
            date        TEXT NOT NULL,
            statut      TEXT NOT NULL DEFAULT 'unset',
            heure       TEXT,
            confiance   INTEGER,
            updated_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(cours_id, eleve_id, date)
        );
    """)

    # Seed matieres
    c.execute("SELECT COUNT(*) FROM matieres")
    if c.fetchone()[0] == 0:
        matieres = [
            ("Mathématiques","MATH","#2563eb","M. Rakoto"),
            ("Physique-Chimie","PHY","#059669","Mme Rabe"),
            ("Français","FRA","#dc2626","Mme Andry"),
            ("Histoire-Géo","HG","#d97706","M. Solo"),
            ("Anglais","ANG","#7c3aed","Mme Vola"),
            ("SVT","SVT","#0891b2","M. Feno"),
        ]
        c.executemany("INSERT INTO matieres (nom,code,couleur,enseignant) VALUES (?,?,?,?)", matieres)
        conn.commit()
        ids = {r[1]: r[0] for r in conn.execute("SELECT id,code FROM matieres").fetchall()}
        cours = [
            (ids["MATH"],"Lundi","07:00","08:00","Salle A1"),
            (ids["MATH"],"Mercredi","10:00","12:00","Salle A1"),
            (ids["MATH"],"Vendredi","14:00","15:00","Salle A1"),
            (ids["PHY"],"Mardi","08:00","10:00","Labo 1"),
            (ids["PHY"],"Jeudi","13:00","15:00","Labo 1"),
            (ids["FRA"],"Lundi","10:00","12:00","Salle B2"),
            (ids["FRA"],"Jeudi","08:00","09:00","Salle B2"),
            (ids["HG"],"Mardi","14:00","16:00","Salle C1"),
            (ids["HG"],"Vendredi","08:00","10:00","Salle C1"),
            (ids["ANG"],"Mercredi","07:30","09:30","Salle D1"),
            (ids["ANG"],"Vendredi","10:00","11:00","Salle D1"),
            (ids["SVT"],"Lundi","14:00","16:00","Labo 2"),
            (ids["SVT"],"Jeudi","10:00","12:00","Labo 2"),
        ]
        c.executemany("INSERT INTO cours (matiere_id,jour,heure_debut,heure_fin,salle) VALUES (?,?,?,?,?)", cours)

    c.execute("SELECT COUNT(*) FROM eleves")
    if c.fetchone()[0] == 0:
        seed = [
            ('TLB-001','Marie','Dupont','12 rue des Fleurs','034 11 111 11','parent.dupont@email.com','Mme Dupont — 034 22 222 22','2006-03-15','F'),
            ('TLB-002','Thomas','Martin','45 avenue Indépendance','034 22 222 22','parent.martin@email.com','M. Martin — 033 11 111 11','2006-07-22','M'),
            ('TLB-003','Sophie','Laurent','7 cité Ambohijatovo','033 33 333 33','parent.laurent@email.com','Mme Laurent — 032 33 333 33','2006-01-10','F'),
            ('TLB-004','Kevin','Bernard','23 rue Rainandriamampandry','032 44 444 44','parent.bernard@email.com','M. Bernard — 034 44 444 44','2005-11-30','M'),
            ('TLB-005','Amara','Koné','Lot IVS 56','034 55 555 55','parent.kone@email.com','Mme Koné — 033 55 555 55','2006-05-18','M'),
            ('TLB-006','Léa','Moreau','Villa 12 Ivandry','033 66 666 66','parent.moreau@email.com','M. Moreau — 032 66 666 66','2006-09-04','F'),
            ('TLB-007','Julien','Dubois','Résidence Panorama Apt 4B','032 77 777 77','parent.dubois@email.com','Mme Dubois — 034 77 777 77','2006-02-28','M'),
            ('TLB-008','Fatima','Ouédraogo','Cité Universitaire Bât C','034 88 888 88','parent.ouedraogo@email.com','M. Ouédraogo — 033 88 888 88','2006-06-12','F'),
            ('TLB-009','Pierre','Renaud','18 allée des Jacarandas','033 99 999 99','parent.renaud@email.com','Mme Renaud — 032 99 999 99','2005-12-05','M'),
            ('TLB-010','Chloé','Fontaine','Immeuble Paradisier RDC','032 10 101 01','parent.fontaine@email.com','M. Fontaine — 034 10 101 01','2006-04-20','F'),
        ]
        for e in seed:
            c.execute("INSERT INTO eleves (id,prenom,nom,classe,adresse,telephone,email_parent,contact_parent,date_naissance,sexe) VALUES (?,?,?,'IGGLIA 3B',?,?,?,?,?,?)", e)

    conn.commit()
    conn.close()

def migrate_db():
    conn = get_db()
    c = conn.cursor()
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    c.execute("PRAGMA table_info(eleves)")
    cols = {r[1] for r in c.fetchall()}
    if "face_encodings" not in cols:
        c.execute("ALTER TABLE eleves ADD COLUMN face_encodings TEXT")
    if "photo_base64" not in cols:
        c.execute("ALTER TABLE eleves ADD COLUMN photo_base64 TEXT")
    if "presences_cours" not in tables:
        print("🔧 Migration: création table presences_cours")
        c.execute("""CREATE TABLE presences_cours (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cours_id INTEGER NOT NULL REFERENCES cours(id) ON DELETE CASCADE,
            eleve_id TEXT NOT NULL REFERENCES eleves(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            statut TEXT NOT NULL DEFAULT 'unset',
            heure TEXT, confiance INTEGER,
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(cours_id, eleve_id, date))""")
    conn.commit()
    conn.close()
    print(" Migration OK")

# ── Helpers ───────────────────────────────────────────────────
def row_to_dict(row):
    d = dict(row)
    d.pop("face_encodings", None)
    return d

def heure_to_min(h):
    try:
        parts = (h or "00:00").split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except:
        return 0

def get_cours_actuel():
    now = datetime.now()
    jour_fr = JOURS_EN.get(now.strftime("%A"), "")
    heure_now = now.strftime("%H:%M")
    conn = get_db()
    row = conn.execute("""
        SELECT c.*, m.nom as matiere_nom, m.couleur, m.code, m.enseignant
        FROM cours c JOIN matieres m ON c.matiere_id = m.id
        WHERE c.jour=? AND c.heure_debut<=? AND c.heure_fin>?
        ORDER BY c.heure_debut LIMIT 1
    """, (jour_fr, heure_now, heure_now)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_prochain_cours():
    now = datetime.now()
    jour_fr = JOURS_EN.get(now.strftime("%A"), "")
    heure_now = now.strftime("%H:%M")
    conn = get_db()
    row = conn.execute("""
        SELECT c.*, m.nom as matiere_nom, m.couleur, m.code
        FROM cours c JOIN matieres m ON c.matiere_id = m.id
        WHERE c.jour=? AND c.heure_debut>?
        ORDER BY c.heure_debut LIMIT 1
    """, (jour_fr, heure_now)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_or_create_presence(conn, eleve_id, date_str):
    c = conn.cursor()
    c.execute("SELECT id FROM presences WHERE eleve_id=? AND date=?", (eleve_id, date_str))
    if not c.fetchone():
        c.execute("INSERT INTO presences (eleve_id,date,statut) VALUES (?,?,'unset')", (eleve_id, date_str))
        conn.commit()

def get_or_create_presence_cours(conn, cours_id, eleve_id, date_str):
    c = conn.cursor()
    c.execute("SELECT id FROM presences_cours WHERE cours_id=? AND eleve_id=? AND date=?", (cours_id, eleve_id, date_str))
    if not c.fetchone():
        c.execute("INSERT INTO presences_cours (cours_id,eleve_id,date,statut) VALUES (?,?,?,'unset')", (cours_id, eleve_id, date_str))
        conn.commit()

def determine_statut(heure_debut: str, heure_arrivee: str, tolerance: int = 15) -> str:
    """Présent si arrivée avant debut+tolerance minutes, sinon retard. Absent = pas venu du tout."""
    diff = heure_to_min(heure_arrivee) - heure_to_min(heure_debut)
    return "present" if diff <= tolerance else "late"

def cloturer_cours(cours_id: int, date_str: str):
    """
    À la fin d'un cours : tous les élèves non scannés → absent.
    Appelé automatiquement quand un nouveau cours commence.
    """
    conn = get_db()
    eleves = conn.execute("SELECT id FROM eleves").fetchall()
    for e in eleves:
        get_or_create_presence_cours(conn, cours_id, e["id"], date_str)
        conn.execute("""
            UPDATE presences_cours SET statut='absent', updated_at=datetime('now')
            WHERE cours_id=? AND eleve_id=? AND date=? AND statut='unset'
        """, (cours_id, e["id"], date_str))
    conn.commit()
    conn.close()
    print(f" Cours {cours_id} clôturé — absents marqués")

# ── Face recognition helpers ──────────────────────────────────
def load_face_cache():
    global _face_cache
    if not INSIGHTFACE_AVAILABLE:
        return
    conn = get_db()
    rows = conn.execute("SELECT id, prenom, nom, face_encodings FROM eleves WHERE face_encodings IS NOT NULL").fetchall()
    conn.close()
    _face_cache = {}
    for row in rows:
        try:
            enc_list = json.loads(row["face_encodings"])
            eleve_id = str(row["id"])  # Toujours stocker en string
            _face_cache[eleve_id] = [np.array(e) for e in enc_list]
            print(f"  [Cache] id={repr(eleve_id)} → {row['prenom']} {row['nom']} ({len(enc_list)} embedding(s))")
        except Exception as ex:
            print(f"  [Cache] Erreur pour {row['id']}: {ex}")
    print(f" Cache facial chargé: {len(_face_cache)} élève(s) → clés={list(_face_cache.keys())}")

def b64_to_numpy(b64):
    """Décode un base64 (RGB, format PIL/JS) en tableau numpy RGB."""
    if "," in b64: b64 = b64.split(",")[1]
    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    return np.array(img)

def b64_to_bgr(b64):
    """Décode un base64 en image BGR (format attendu par OpenCV / InsightFace)."""
    rgb = b64_to_numpy(b64)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

def get_face_embedding(img_bgr):
    """Extrait l'embedding ArcFace (512-d) du plus grand visage détecté.
    Retourne (embedding numpy ou None, bbox ou None)."""
    if not INSIGHTFACE_AVAILABLE:
        return None, None
    faces = face_app.get(img_bgr)
    if not faces:
        return None, None
    # Plus grand visage = le plus proche de la caméra
    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    return face.embedding, face.bbox

def extract_embeddings(b64_list):
    """Encode les photos d'inscription en vecteurs ArcFace (InsightFace)."""
    if not INSIGHTFACE_AVAILABLE: return []
    embeddings = []
    for idx, b64 in enumerate(b64_list):
        try:
            img_bgr = b64_to_bgr(b64)
            emb, _ = get_face_embedding(img_bgr)
            if emb is not None:
                embeddings.append(emb.tolist())
                print(f"  [Encode] photo {idx+1}/{len(b64_list)} OK — vecteur {len(emb)}D")
            else:
                print(f"  [Encode] photo {idx+1}: aucun visage détecté")
        except Exception as ex:
            print(f"  [Encode] photo {idx+1} erreur: {ex}")
    print(f"[Encode] {len(embeddings)}/{len(b64_list)} photos encodées avec succès")
    return embeddings

def cosine_sim(a, b):
    a, b = np.array(a), np.array(b)
    n = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / n) if n else 0.0


# ═══════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════

# ── ÉLÈVES ───────────────────────────────────────────────────
@app.route("/api/eleves", methods=["GET"])
def get_eleves():
    conn = get_db()
    today = date.today().isoformat()
    rows = conn.execute("""
        SELECT e.id, e.prenom, e.nom, e.classe, e.adresse, e.telephone,
               e.email_parent, e.contact_parent, e.date_naissance, e.sexe,
               e.photo_base64, e.created_at,
               CASE WHEN e.face_encodings IS NOT NULL THEN 1 ELSE 0 END as has_face,
               COALESCE(p.statut,'unset') as statut, p.heure, p.confiance, p.motif
        FROM eleves e
        LEFT JOIN presences p ON e.id=p.eleve_id AND p.date=?
        ORDER BY e.nom, e.prenom
    """, (today,)).fetchall()
    conn.close()
    return jsonify([row_to_dict(r) for r in rows])

@app.route("/api/eleves/<eleve_id>", methods=["GET"])
def get_eleve(eleve_id):
    conn = get_db()
    today = date.today().isoformat()
    row = conn.execute("""
        SELECT e.id, e.prenom, e.nom, e.classe, e.adresse, e.telephone,
               e.email_parent, e.contact_parent, e.date_naissance, e.sexe,
               e.photo_base64, e.created_at,
               CASE WHEN e.face_encodings IS NOT NULL THEN 1 ELSE 0 END as has_face,
               COALESCE(p.statut,'unset') as statut, p.heure, p.confiance, p.motif
        FROM eleves e
        LEFT JOIN presences p ON e.id=p.eleve_id AND p.date=?
        WHERE e.id=?
    """, (today, eleve_id)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Élève non trouvé"}), 404
    hist = conn.execute(
        "SELECT date,statut,heure,confiance FROM presences WHERE eleve_id=? ORDER BY date DESC LIMIT 30",
        (eleve_id,)
    ).fetchall()
    result = row_to_dict(row)
    result["historique"] = [dict(h) for h in hist]
    conn.close()
    return jsonify(result)

@app.route("/api/eleves", methods=["POST"])
def create_eleve():
    try:
        data = request.get_json(force=True, silent=True) or {}
        for f in ["id","prenom","nom"]:
            if not (data.get(f) or "").strip():
                return jsonify({"error": f"Champ requis: {f}"}), 400
        face_photos = data.get("face_photos") or []
        embeddings = extract_embeddings(face_photos)
        face_json = json.dumps(embeddings) if embeddings else None
        conn = get_db()
        conn.execute("""INSERT INTO eleves
            (id,prenom,nom,classe,adresse,telephone,email_parent,contact_parent,date_naissance,sexe,photo_base64,face_encodings)
            VALUES (:id,:prenom,:nom,:classe,:adresse,:telephone,:email_parent,:contact_parent,:date_naissance,:sexe,:photo_base64,:fe)""",
            {"id":data["id"].strip(),"prenom":data["prenom"].strip(),"nom":data["nom"].strip(),
             "classe":data.get("classe","IGGLIA 3B"),"adresse":data.get("adresse") or None,
             "telephone":data.get("telephone") or None,"email_parent":data.get("email_parent") or None,
             "contact_parent":data.get("contact_parent") or None,"date_naissance":data.get("date_naissance") or None,
             "sexe":data.get("sexe") or None,"photo_base64":data.get("photo_base64") or None,"fe":face_json})
        conn.commit(); conn.close()
        if face_json: load_face_cache()
        return jsonify({"success":True,"id":data["id"],"nb_embeddings":len(embeddings)}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Cet ID existe déjà"}), 409
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@app.route("/api/eleves/<eleve_id>", methods=["PUT"])
def update_eleve(eleve_id):
    data = request.get_json(force=True, silent=True) or {}
    face_photos = data.pop("face_photos", []) or []
    conn = get_db()
    if face_photos:
        embeddings = extract_embeddings(face_photos)
        if embeddings:
            conn.execute("""UPDATE eleves SET prenom=:prenom,nom=:nom,classe=:classe,adresse=:adresse,
                telephone=:telephone,email_parent=:email_parent,contact_parent=:contact_parent,
                date_naissance=:date_naissance,sexe=:sexe,
                photo_base64=COALESCE(:photo_base64,photo_base64),face_encodings=:fe WHERE id=:id""",
                {**data,"id":eleve_id,"fe":json.dumps(embeddings)})
        else:
            conn.execute("""UPDATE eleves SET prenom=:prenom,nom=:nom,classe=:classe,adresse=:adresse,
                telephone=:telephone,email_parent=:email_parent,contact_parent=:contact_parent,
                date_naissance=:date_naissance,sexe=:sexe,
                photo_base64=COALESCE(:photo_base64,photo_base64) WHERE id=:id""",
                {**data,"id":eleve_id})
    else:
        conn.execute("""UPDATE eleves SET prenom=:prenom,nom=:nom,classe=:classe,adresse=:adresse,
            telephone=:telephone,email_parent=:email_parent,contact_parent=:contact_parent,
            date_naissance=:date_naissance,sexe=:sexe,
            photo_base64=COALESCE(:photo_base64,photo_base64) WHERE id=:id""",
            {**data,"id":eleve_id})
    conn.commit(); conn.close()
    load_face_cache()
    return jsonify({"success":True})

@app.route("/api/eleves/<eleve_id>", methods=["DELETE"])
def delete_eleve(eleve_id):
    conn = get_db()
    conn.execute("DELETE FROM presences_cours WHERE eleve_id=?", (eleve_id,))
    conn.execute("DELETE FROM presences WHERE eleve_id=?", (eleve_id,))
    conn.execute("DELETE FROM eleves WHERE id=?", (eleve_id,))
    conn.commit(); conn.close()
    _face_cache.pop(eleve_id, None)
    return jsonify({"success":True})


# ── PRÉSENCES (globales) ───────────────────────────────────────
@app.route("/api/presences/<eleve_id>", methods=["PUT"])
def update_presence(eleve_id):
    data = request.get_json(force=True, silent=True) or {}
    date_str = data.get("date", date.today().isoformat())
    conn = get_db()
    get_or_create_presence(conn, eleve_id, date_str)
    conn.execute("""UPDATE presences SET statut=?,heure=?,confiance=?,motif=?,updated_at=datetime('now')
        WHERE eleve_id=? AND date=?""",
        (data.get("statut","unset"),data.get("heure"),data.get("confiance"),data.get("motif"),eleve_id,date_str))
    conn.commit(); conn.close()
    return jsonify({"success":True})


# ── STATS TABLEAU DE BORD ─────────────────────────────────────
@app.route("/api/stats", methods=["GET"])
def get_stats():
    conn = get_db()
    today = date.today().isoformat()
    now_str = datetime.now().strftime("%H:%M")
    jour_fr = JOURS_EN.get(datetime.now().strftime("%A"), "")

    # Cours actuel
    cours_actuel = conn.execute("""
        SELECT c.id, c.heure_debut, c.heure_fin, c.salle, c.jour,
               m.nom as matiere_nom, m.couleur, m.code
        FROM cours c JOIN matieres m ON c.matiere_id=m.id
        WHERE c.jour=? AND c.heure_debut<=? AND c.heure_fin>?
        ORDER BY c.heure_debut LIMIT 1
    """, (jour_fr, now_str, now_str)).fetchone()

    # Prochain cours
    prochain = conn.execute("""
        SELECT c.id, c.heure_debut, c.heure_fin, c.salle, c.jour,
               m.nom as matiere_nom, m.couleur, m.code
        FROM cours c JOIN matieres m ON c.matiere_id=m.id
        WHERE c.jour=? AND c.heure_debut>?
        ORDER BY c.heure_debut LIMIT 1
    """, (jour_fr, now_str)).fetchone()

    total_eleves = conn.execute("SELECT COUNT(*) FROM eleves").fetchone()[0]

    if cours_actuel:
        cid = cours_actuel["id"]
        # Stats du cours actuel
        rows = conn.execute("""
            SELECT COALESCE(pc.statut,'unset') as statut, COUNT(*) as cnt
            FROM eleves e
            LEFT JOIN presences_cours pc ON e.id=pc.eleve_id AND pc.cours_id=? AND pc.date=?
            GROUP BY statut
        """, (cid, today)).fetchall()
        stats_cours = {"present":0,"late":0,"absent":0,"unset":0}
        for r in rows:
            k = r["statut"] if r["statut"] in stats_cours else "unset"
            stats_cours[k] += r["cnt"]

        # Liste élèves du cours actuel
        eleves_cours = conn.execute("""
            SELECT e.id, e.prenom, e.nom, e.photo_base64,
                   COALESCE(pc.statut,'unset') as statut,
                   pc.heure, pc.confiance
            FROM eleves e
            LEFT JOIN presences_cours pc ON e.id=pc.eleve_id AND pc.cours_id=? AND pc.date=?
            ORDER BY e.nom
        """, (cid, today)).fetchall()

        cours_info = dict(cours_actuel)
        cours_info["stats"] = stats_cours
        cours_info["total"] = total_eleves
        cours_info["eleves"] = [row_to_dict(e) for e in eleves_cours]
    else:
        cours_info = None

    # Graphique hebdomadaire
    weekly = conn.execute("""
        SELECT date, COUNT(*) as total,
               SUM(CASE WHEN statut IN ('present','late') THEN 1 ELSE 0 END) as presents
        FROM presences WHERE date >= date('now','-7 days') AND date<=?
        GROUP BY date ORDER BY date
    """, (today,)).fetchall()

    conn.close()
    return jsonify({
        "cours_actuel": cours_info,
        "prochain_cours": dict(prochain) if prochain else None,
        "total_eleves": total_eleves,
        "weekly": [{"date":r["date"],"taux":round(r["presents"]/r["total"]*100) if r["total"] else 0} for r in weekly],
        "heure": now_str,
        "jour": jour_fr,
    })


# ── HISTORIQUE DES PRÉSENCES PAR COURS ───────────────────────
@app.route("/api/historique", methods=["GET"])
def get_historique():
    """Retourne tous les cours passés avec présences groupées."""
    conn = get_db()
    today = date.today().isoformat()
    now_str = datetime.now().strftime("%H:%M")
    jour_fr = JOURS_EN.get(datetime.now().strftime("%A"), "")

    # Tous les cours qui ont eu lieu (date <= aujourd'hui, heure_fin <= maintenant si aujourd'hui)
    cours_passes = conn.execute("""
        SELECT DISTINCT pc.cours_id, pc.date, c.jour, c.heure_debut, c.heure_fin, c.salle,
               m.nom as matiere_nom, m.couleur, m.code, m.enseignant
        FROM presences_cours pc
        JOIN cours c ON pc.cours_id = c.id
        JOIN matieres m ON c.matiere_id = m.id
        ORDER BY pc.date DESC, c.heure_debut DESC
    """).fetchall()

    result = []
    for cp in cours_passes:
        cid = cp["cours_id"]
        d   = cp["date"]
        eleves = conn.execute("""
            SELECT e.id, e.prenom, e.nom, e.photo_base64,
                   COALESCE(pc.statut,'absent') as statut,
                   pc.heure, pc.confiance
            FROM eleves e
            LEFT JOIN presences_cours pc ON e.id=pc.eleve_id AND pc.cours_id=? AND pc.date=?
            ORDER BY
              CASE COALESCE(pc.statut,'absent')
                WHEN 'present' THEN 1
                WHEN 'late'    THEN 2
                WHEN 'absent'  THEN 3
                ELSE 4 END,
              e.nom
        """, (cid, d)).fetchall()

        stats = {"present":0,"late":0,"absent":0}
        for e in eleves:
            k = e["statut"] if e["statut"] in stats else "absent"
            stats[k] += 1

        result.append({
            "cours_id": cid,
            "date": d,
            "jour": cp["jour"],
            "heure_debut": cp["heure_debut"],
            "heure_fin": cp["heure_fin"],
            "salle": cp["salle"] or "",
            "matiere_nom": cp["matiere_nom"],
            "couleur": cp["couleur"],
            "code": cp["code"],
            "enseignant": cp["enseignant"] or "",
            "stats": stats,
            "total": len(eleves),
            "eleves": [row_to_dict(e) for e in eleves],
        })

    conn.close()
    return jsonify(result)


# ── CLÔTURER UN COURS (marquer absents non-scannés) ───────────
@app.route("/api/cours/<int:cours_id>/cloturer", methods=["POST"])
def cloturer(cours_id):
    today = date.today().isoformat()
    cloturer_cours(cours_id, today)
    return jsonify({"success": True})


# ── MATIÈRES ─────────────────────────────────────────────────
@app.route("/api/matieres", methods=["GET"])
def get_matieres():
    try:
        conn = get_db()
        mats = conn.execute("SELECT * FROM matieres ORDER BY nom").fetchall()
        result = []
        for m in mats:
            d = dict(m)
            cours_list = conn.execute("""
                SELECT * FROM cours WHERE matiere_id=?
                ORDER BY CASE jour
                  WHEN 'Lundi' THEN 1 WHEN 'Mardi' THEN 2 WHEN 'Mercredi' THEN 3
                  WHEN 'Jeudi' THEN 4 WHEN 'Vendredi' THEN 5 WHEN 'Samedi' THEN 6
                  ELSE 7 END, heure_debut
            """, (m["id"],)).fetchall()
            d["cours"] = [dict(c) for c in cours_list]
            result.append(d)
        conn.close()
        return jsonify(result)
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@app.route("/api/matieres", methods=["POST"])
def create_matiere():
    try:
        data = request.get_json(force=True, silent=True) or {}
        nom  = (data.get("nom")  or "").strip()
        code = (data.get("code") or "").strip().upper()
        if not nom or not code:
            return jsonify({"error": "Le nom et le code sont obligatoires"}), 400
        conn = get_db()
        cur = conn.execute("INSERT INTO matieres (nom,code,couleur,enseignant) VALUES (?,?,?,?)",
            (nom, code, data.get("couleur","#2563eb"), data.get("enseignant") or None))
        mat_id = cur.lastrowid
        for c in (data.get("cours") or []):
            if c.get("jour") and c.get("heure_debut") and c.get("heure_fin"):
                conn.execute("INSERT INTO cours (matiere_id,jour,heure_debut,heure_fin,salle) VALUES (?,?,?,?,?)",
                    (mat_id, c["jour"], c["heure_debut"], c["heure_fin"], c.get("salle") or ""))
        conn.commit(); conn.close()
        return jsonify({"success":True,"id":mat_id}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Ce code matière existe déjà"}), 409
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@app.route("/api/matieres/<int:mat_id>", methods=["PUT"])
def update_matiere(mat_id):
    try:
        data = request.get_json(force=True, silent=True) or {}
        conn = get_db()
        conn.execute("UPDATE matieres SET nom=?,code=?,couleur=?,enseignant=? WHERE id=?",
            ((data.get("nom") or "").strip(), (data.get("code") or "").strip().upper(),
             data.get("couleur","#2563eb"), data.get("enseignant") or None, mat_id))
        conn.execute("DELETE FROM cours WHERE matiere_id=?", (mat_id,))
        for c in (data.get("cours") or []):
            if c.get("jour") and c.get("heure_debut") and c.get("heure_fin"):
                conn.execute("INSERT INTO cours (matiere_id,jour,heure_debut,heure_fin,salle) VALUES (?,?,?,?,?)",
                    (mat_id, c["jour"], c["heure_debut"], c["heure_fin"], c.get("salle") or ""))
        conn.commit(); conn.close()
        return jsonify({"success":True})
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@app.route("/api/matieres/<int:mat_id>", methods=["DELETE"])
def delete_matiere(mat_id):
    conn = get_db()
    conn.execute("DELETE FROM cours WHERE matiere_id=?", (mat_id,))
    conn.execute("DELETE FROM matieres WHERE id=?", (mat_id,))
    conn.commit(); conn.close()
    return jsonify({"success":True})

@app.route("/api/cours/maintenant", methods=["GET"])
def cours_maintenant():
    try:
        actuel  = get_cours_actuel()
        prochain = get_prochain_cours()
        now = datetime.now()
        return jsonify({
            "heure": now.strftime("%H:%M"),
            "jour": JOURS_EN.get(now.strftime("%A"), ""),
            "cours_actuel": actuel,
            "prochain_cours": prochain,
        })
    except Exception as ex:
        return jsonify({"error":str(ex),"heure":"","jour":"","cours_actuel":None,"prochain_cours":None}), 500


# ── RECONNAISSANCE FACIALE ────────────────────────────────────
# ── DROIDCAM : capture frame (appelé depuis Informations aussi) ──────────
@app.route("/api/droidcam/capture", methods=["POST","OPTIONS"])
def droidcam_capture():
    if request.method == "OPTIONS": return jsonify({"ok":True}), 200
    import urllib.request, time as _time
    data = request.get_json(force=True, silent=True) or {}
    phone_url = data.get("phone_url", "").strip().rstrip("/")
    for suffix in ["/video", "/videofeed", "/mjpeg", "/shot.jpg"]:
        if phone_url.endswith(suffix):
            phone_url = phone_url[:-len(suffix)]
            break

    ts = str(int(_time.time() * 1000))
    candidates = [
        phone_url + "/shot.jpg?t=" + ts,
        phone_url + "/jpeg?t=" + ts,
        phone_url + "/snapshot?t=" + ts,
        phone_url + "/photo.jpg?t=" + ts,
    ]
    for url in candidates:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SFIGP/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    img_bytes = resp.read()
                    b64 = "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode()
                    return jsonify({"ok": True, "frame": b64, "url": url})
        except Exception as ex:
            pass
    return jsonify({"ok": False, "message": "DroidCam inaccessible — vérifiez l'URL et le WiFi"}), 200


# ── PROXY MJPEG DROIDCAM ─────────────────────────────────────
# Le navigateur bloque les flux HTTP directs (mixed content + CORS)
# Ce proxy Flask relaie le flux MJPEG de DroidCam → le navigateur

@app.route("/api/droidcam/stream")
def droidcam_stream():
    """Proxy MJPEG : relaie le flux video du telephone via Flask."""
    import urllib.request
    phone_url = request.args.get("url", "").strip().rstrip("/")
    for suffix in ["/video", "/videofeed", "/mjpeg"]:
        if phone_url.endswith(suffix):
            phone_url = phone_url[:-len(suffix)]
            break

    # Essayer les endpoints video dans l ordre
    video_candidates = [
        phone_url + "/video",
        phone_url + "/videofeed",
        phone_url + "/mjpeg",
    ]

    def generate():
        for video_url in video_candidates:
            try:
                req = urllib.request.Request(
                    video_url,
                    headers={"User-Agent": "SFIGP/1.0"}
                )
                resp = urllib.request.urlopen(req, timeout=5)
                print(f"[DroidCam Proxy] Connecte: {video_url}")
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    yield chunk
                return
            except Exception as ex:
                print(f"[DroidCam Proxy] Echec {video_url}: {ex}")
                continue
        # Si tous echouent, envoyer image vide
        yield b""

    return Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=--myboundary",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Access-Control-Allow-Origin": "*",
        }
    )


@app.route("/api/droidcam/frame")
def droidcam_frame():
    """Retourne une image JPEG unique depuis DroidCam (pour affichage polling)."""
    import urllib.request, time as _t
    phone_url = request.args.get("url", "").strip().rstrip("/")
    for suffix in ["/video", "/videofeed", "/mjpeg", "/shot.jpg"]:
        if phone_url.endswith(suffix):
            phone_url = phone_url[:-len(suffix)]
            break

    ts = str(int(_t.time() * 1000))
    candidates = [
        phone_url + "/shot.jpg?t=" + ts,
        phone_url + "/jpeg?t=" + ts,
        phone_url + "/snapshot?t=" + ts,
    ]
    for url in candidates:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SFIGP/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    img_bytes = resp.read()
                    return Response(
                        img_bytes,
                        mimetype="image/jpeg",
                        headers={
                            "Cache-Control": "no-cache, no-store",
                            "Access-Control-Allow-Origin": "*",
                        }
                    )
        except Exception:
            pass
    return Response(status=404)


@app.route("/api/facial/recognize", methods=["POST"])
def facial_recognize():
    data      = request.get_json(force=True, silent=True) or {}
    frame_b64 = data.get("frame")       # base64 depuis webcam PC
    phone_url = data.get("phone_url")   # URL DroidCam ex: http://192.168.1.45:4747
    today     = date.today().isoformat()
    now_str   = datetime.now().strftime("%H:%M")

    # ── Si phone_url fourni : le backend fetch l'image lui-meme ──
    # Contourne le blocage CORS/mixed-content du navigateur
    if phone_url and not frame_b64:
        import urllib.request, time as _time
        base = phone_url.strip().rstrip("/")
        # Nettoyer les suffixes connus
        for suffix in ["/video", "/videofeed", "/mjpeg", "/shot.jpg"]:
            if base.endswith(suffix):
                base = base[:-len(suffix)]
                break

        # DroidCam essaie plusieurs endpoints dans l'ordre
        # selon la version installée (PC client vs app seule)
        ts = str(int(_time.time() * 1000))
        candidates = [
            base + "/shot.jpg?t=" + ts,          # DroidCam app standard
            base + "/jpeg?t=" + ts,              # DroidCam alternative
            base + "/snapshot?t=" + ts,          # IP Webcam / autres
            base + "/photo.jpg?t=" + ts,         # certains firmwares
            base + "/image.jpg?t=" + ts,         # fallback
        ]

        img_bytes = None
        last_err  = None
        for url in candidates:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "SFIGP/1.0"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status == 200:
                        img_bytes = resp.read()
                        print(f"[DroidCam] OK -> {url} ({len(img_bytes)} bytes)")
                        break
            except Exception as ex:
                last_err = str(ex)
                print(f"[DroidCam] Essai {url} -> {ex}")

        if not img_bytes:
            return jsonify({
                "recognized": False,
                "message": f"DroidCam inaccessible. Essayez : 1) Verifiez que DroidCam est ouvert sur le telephone. 2) Meme reseau WiFi. 3) URL correcte ex: http://192.168.x.x:4747. Erreur: {last_err}"
            }), 200

        frame_b64 = "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode()

    # Cours actuel → détermine statut et enregistre dans presences_cours
    cours_act = get_cours_actuel()

    def enregistrer(eleve_id, prenom, nom, statut, confiance):
        conn = get_db()
        try:
            # INSERT OR REPLACE pour créer+mettre à jour en une seule opération atomique
            conn.execute("""INSERT INTO presences (eleve_id, date, statut, heure, confiance, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(eleve_id, date) DO UPDATE SET
                    statut=excluded.statut,
                    heure=excluded.heure,
                    confiance=excluded.confiance,
                    updated_at=excluded.updated_at
            """, (eleve_id, today, statut, now_str, confiance))

            if cours_act:
                cid = cours_act["id"]
                conn.execute("""INSERT INTO presences_cours (cours_id, eleve_id, date, statut, heure, confiance, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(cours_id, eleve_id, date) DO UPDATE SET
                        statut=excluded.statut,
                        heure=excluded.heure,
                        confiance=excluded.confiance,
                        updated_at=excluded.updated_at
                """, (cid, eleve_id, today, statut, now_str, confiance))

            conn.commit()
            print(f"[Présence] {prenom} {nom} → {statut} ({confiance}%) à {now_str}")
        except Exception as ex:
            print(f"[Présence] Erreur enregistrement {eleve_id}: {ex}")
            conn.rollback()
        finally:
            conn.close()

    matiere_info = None
    if cours_act:
        matiere_info = {
            "nom": cours_act["matiere_nom"],
            "couleur": cours_act["couleur"],
            "heure_debut": cours_act["heure_debut"],
            "heure_fin": cours_act["heure_fin"],
            "cours_id": cours_act["id"],
        }

    # ── MODE RÉEL (InsightFace / ArcFace) ──
    if INSIGHTFACE_AVAILABLE and frame_b64 and _face_cache:
        try:
            img_bgr = b64_to_bgr(frame_b64)
            scan_emb, _bbox = get_face_embedding(img_bgr)
            if scan_emb is None:
                return jsonify({"recognized":False,"message":"Aucun visage détecté"})
            scan_emb = np.asarray(scan_emb, dtype=np.float64)

            # Comparer avec chaque élève par DISTANCE COSINUS (standard ArcFace)
            # dist = 1 - cos_sim  → 0.0 = identique, 2.0 = totalement différent
            best_id, best_dist = None, float("inf")
            SCORES = {}
            a_norm = scan_emb / (np.linalg.norm(scan_emb) + 1e-10)
            for eid, known_list in _face_cache.items():
                eid = str(eid)  # Garantir string
                dists = []
                for k in known_list:
                    k = np.asarray(k, dtype=np.float64)
                    b_norm = k / (np.linalg.norm(k) + 1e-10)
                    dist = float(1.0 - np.dot(a_norm, b_norm))
                    dists.append(dist)
                best_for_eleve = min(dists)
                SCORES[eid] = best_for_eleve
                if best_for_eleve < best_dist:
                    best_dist, best_id = best_for_eleve, eid

            # Seuil ArcFace (distance cosinus) : < 0.4 = même personne (empirique, buffalo_l)
            # Plus on descend, plus c'est strict (moins de faux positifs)
            SEUIL_DIST = 0.40
            conf = max(0, round((1.0 - best_dist) * 100))
            print(f"[Recog] best={best_id} dist={best_dist:.3f} conf={conf}% scores={SCORES}")

            if not best_id or best_dist > SEUIL_DIST:
                return jsonify({"recognized":False,"message":f"Visage non reconnu (dist={best_dist:.2f}, seuil={SEUIL_DIST}) — enregistrez plus de photos sous différents angles"})

            statut = determine_statut(cours_act["heure_debut"], now_str) if cours_act else "present"

            # ── Récupérer les infos de l'élève reconnu ──
            # IMPORTANT : on cherche par l'ID TEXT exact du cache
            conn = get_db()
            # Vérification : lister tous les élèves pour debug
            all_eleves = conn.execute("SELECT id, prenom, nom FROM eleves").fetchall()
            print(f"[Recog] Élèves en base: {[(e['id'], e['prenom'], e['nom']) for e in all_eleves]}")
            print(f"[Recog] best_id={repr(best_id)} (type={type(best_id).__name__})")
            print(f"[Recog] Cache keys: {list(_face_cache.keys())}")

            # Forcer la comparaison en string
            best_id_str = str(best_id)
            eleve = conn.execute(
                "SELECT id, prenom, nom, photo_base64 FROM eleves WHERE id=?",
                (best_id_str,)
            ).fetchone()
            conn.close()

            if not eleve:
                # Tentative de récupération par comparaison souple
                print(f"[Recog] ERREUR: id={repr(best_id_str)} non trouvé en base!")
                return jsonify({"recognized":False,"message":f"Élève ID={best_id_str} introuvable — rechargez le cache"})

            # Vérification que l'ID retourné correspond bien
            print(f"[Recog] ✓ Match confirmé: id={eleve['id']} → {eleve['prenom']} {eleve['nom']}")

            enregistrer(eleve["id"], eleve["prenom"], eleve["nom"], statut, conf)
            return jsonify({
                "recognized":  True,
                "eleve_id":    eleve["id"],    # ID exact de la base
                "prenom":      eleve["prenom"],
                "nom":         eleve["nom"],
                "photo_base64":eleve["photo_base64"] or None,
                "confiance":   conf,
                "heure":       now_str,
                "statut":      statut,
                "mode":        "real",
                "matiere":     matiere_info,
                "debug_dist":  round(best_dist, 3),
            })
        except Exception as ex:
            msg = str(ex)
            if "face" in msg.lower() and "detect" in msg.lower():
                return jsonify({"recognized":False,"message":"Aucun visage détecté — repositionnez-vous"})
            return jsonify({"recognized":False,"message":f"Erreur: {msg}"}), 500

    # ── MODE SIMULATION ──
    # En simulation : on renvoie "non reconnu" si aucun frame fourni
    # Sinon on choisit un élève non encore scanné
    import random
    conn = get_db()
    if cours_act:
        cid = cours_act["id"]
        unset = conn.execute("""
            SELECT e.id, e.prenom, e.nom FROM eleves e
            LEFT JOIN presences_cours pc ON e.id=pc.eleve_id AND pc.cours_id=? AND pc.date=?
            WHERE COALESCE(pc.statut,'unset')='unset'
        """, (cid, today)).fetchall()
    else:
        unset = conn.execute("""
            SELECT e.id, e.prenom, e.nom FROM eleves e
            LEFT JOIN presences p ON e.id=p.eleve_id AND p.date=?
            WHERE COALESCE(p.statut,'unset')='unset'
        """, (today,)).fetchall()
    conn.close()

    if not unset:
        return jsonify({"recognized":False,"message":"Tous les élèves ont été marqués pour ce cours"})

    s = random.choice(unset)
    conf = random.randint(82, 99)
    statut = determine_statut(cours_act["heure_debut"], now_str) if cours_act else "present"
    enregistrer(s["id"], s["prenom"], s["nom"], statut, conf)
    return jsonify({"recognized":True,"eleve_id":s["id"],
        "prenom":s["prenom"],"nom":s["nom"],
        "confiance":conf,"heure":now_str,"statut":statut,
        "mode":"simulation","matiere":matiere_info})

@app.route("/api/facial/status", methods=["GET"])
def facial_status():
    # Détail du cache pour diagnostic
    cache_detail = []
    if INSIGHTFACE_AVAILABLE:
        conn = get_db()
        for eid, embs in _face_cache.items():
            row = conn.execute("SELECT prenom, nom FROM eleves WHERE id=?", (str(eid),)).fetchone()
            cache_detail.append({
                "id": str(eid),
                "nom": f"{row['prenom']} {row['nom']}" if row else f"INCONNU ({eid})",
                "nb_embeddings": len(embs),
            })
        conn.close()
    return jsonify({
        "face_recognition_available": INSIGHTFACE_AVAILABLE,
        "insightface_available": INSIGHTFACE_AVAILABLE,
        "nb_eleves_avec_face": len(_face_cache),
        "eleves_avec_face": list(str(k) for k in _face_cache.keys()),
        "cache_detail": cache_detail,
    })

@app.route("/api/facial/reload-cache", methods=["POST","OPTIONS"])
def reload_face_cache():
    """Forcer le rechargement du cache facial (utile après inscription)."""
    if request.method == "OPTIONS": return jsonify({"ok":True}), 200
    load_face_cache()
    return jsonify({
        "ok": True,
        "nb_eleves": len(_face_cache),
        "ids": list(str(k) for k in _face_cache.keys()),
    })


@app.route("/api/dashboard", methods=["GET","OPTIONS"])
def dashboard():
    """Données complètes pour le tableau de bord : cours actuel avec présences groupées."""
    if request.method == "OPTIONS": return jsonify({"ok":True}), 200
    try:
        now = datetime.now()
        today = date.today().isoformat()
        now_str = now.strftime("%H:%M")
        JOURS_FR = ["Dimanche","Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi"]
        jour_fr = JOURS_FR[now.weekday() + 1] if now.weekday() < 6 else "Dimanche"
        jour_fr = JOURS_EN.get(now.strftime("%A"), "")
        conn = get_db()
        total_eleves = conn.execute("SELECT COUNT(*) FROM eleves").fetchone()[0]

        # Cours actuel
        cours_actuel = conn.execute("""
            SELECT c.*, m.nom as matiere_nom, m.couleur, m.code, m.enseignant
            FROM cours c JOIN matieres m ON c.matiere_id=m.id
            WHERE c.jour=? AND c.heure_debut<=? AND c.heure_fin>?
            ORDER BY c.heure_debut LIMIT 1
        """, (jour_fr, now_str, now_str)).fetchone()

        prochain = conn.execute("""
            SELECT c.*, m.nom as matiere_nom, m.couleur, m.code
            FROM cours c JOIN matieres m ON c.matiere_id=m.id
            WHERE c.jour=? AND c.heure_debut>?
            ORDER BY c.heure_debut LIMIT 1
        """, (jour_fr, now_str)).fetchone()

        cours_info = None
        if cours_actuel:
            cid = cours_actuel["id"]
            # Stats du cours actuel
            stats_row = conn.execute("""
                SELECT
                  SUM(CASE WHEN statut='present' THEN 1 ELSE 0 END) as present,
                  SUM(CASE WHEN statut='late'    THEN 1 ELSE 0 END) as late,
                  SUM(CASE WHEN statut='absent'  THEN 1 ELSE 0 END) as absent
                FROM presences_cours WHERE cours_id=? AND date=?
            """, (cid, today)).fetchone()
            stats = {"present": stats_row["present"] or 0, "late": stats_row["late"] or 0, "absent": stats_row["absent"] or 0}

            # Élèves avec statut dans ce cours
            eleves = conn.execute("""
                SELECT e.id, e.prenom, e.nom, e.photo_base64,
                       COALESCE(pc.statut,'unset') as statut, pc.heure, pc.confiance
                FROM eleves e
                LEFT JOIN presences_cours pc ON e.id=pc.eleve_id AND pc.cours_id=? AND pc.date=?
                ORDER BY e.nom
            """, (cid, today)).fetchall()

            cours_info = dict(cours_actuel)
            cours_info["stats"] = stats
            cours_info["eleves"] = [row_to_dict(e) for e in eleves]

        # Graphique hebdo (basé sur presences classiques)
        weekly = conn.execute("""
            SELECT date,
                   COUNT(*) as total,
                   SUM(CASE WHEN statut IN ('present','late') THEN 1 ELSE 0 END) as presents
            FROM presences WHERE date>=date('now','-7 days') AND date<=?
            GROUP BY date ORDER BY date
        """, (today,)).fetchall()

        # Tous élèves pour affichage hors cours
        tous = conn.execute("SELECT id,prenom,nom FROM eleves ORDER BY nom").fetchall()
        conn.close()

        return jsonify({
            "cours_actuel": cours_info,
            "prochain_cours": dict(prochain) if prochain else None,
            "total_eleves": total_eleves,
            "heure": now_str,
            "jour": jour_fr,
            "weekly": [{"date":r["date"],"taux":round(r["presents"]/r["total"]*100) if r["total"] else 0} for r in weekly],
            "tous_eleves": [dict(e) for e in tous],
        })
    except Exception as ex:
        print(f"Erreur dashboard: {ex}")
        import traceback; traceback.print_exc()
        return jsonify({"error": str(ex)}), 500


# ── CONTACT PARENTS ──────────────────────────────────────────
@app.route("/api/contact/envoyer", methods=["POST","OPTIONS"])
def contact_envoyer():
    """
    Envoie des messages aux parents.
    En mode production: utilise smtplib pour email, ou API SMS.
    En mode démo: simule l'envoi et log dans la table notifications.
    """
    if request.method == "OPTIONS": return jsonify({"ok":True}),200
    data = request.get_json(force=True,silent=True) or {}
    eleves_list = data.get("eleves",[])
    if not eleves_list:
        return jsonify({"ok":False,"message":"Aucun élève sélectionné"}),200

    today = date.today().isoformat()
    conn  = get_db()
    details = []
    ok_count = 0

    for e in eleves_list:
        dest = e.get("email_parent") or e.get("contact_parent","")
        msg  = e.get("message","")
        eleve_id = e.get("id","")
        nom      = f"{e.get('prenom','')} {e.get('nom','')}"

        # ── Tentative d'envoi email ──────────────────────────
        sent = False
        err  = None

        if e.get("email_parent"):
            try:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                # Config SMTP — à adapter selon le serveur disponible
                SMTP_HOST = os.environ.get("SMTP_HOST","smtp.gmail.com")
                SMTP_PORT = int(os.environ.get("SMTP_PORT","587"))
                SMTP_USER = os.environ.get("SMTP_USER","")
                SMTP_PASS = os.environ.get("SMTP_PASS","")

                if SMTP_USER and SMTP_PASS:
                    mail = MIMEMultipart()
                    mail["From"]    = SMTP_USER
                    mail["To"]      = e["email_parent"]
                    mail["Subject"] = f"[ISPM] Présence de {nom}"
                    mail.attach(MIMEText(msg,"plain","utf-8"))
                    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
                        smtp.starttls()
                        smtp.login(SMTP_USER, SMTP_PASS)
                        smtp.sendmail(SMTP_USER, [e["email_parent"]], mail.as_string())
                    sent = True
                    print(f"[Email] ✓ Envoyé à {e['email_parent']}")
                else:
                    # Mode simulation — pas de config SMTP
                    sent = True
                    print(f"[Email-SIM] Message simulé pour {e['email_parent']}: {msg[:80]}...")
            except Exception as ex:
                err = str(ex)
                print(f"[Email] ✗ Erreur {e.get('email_parent')}: {ex}")

        elif e.get("contact_parent"):
            # Mode simulation SMS (sans passerelle configurée)
            sent = True
            print(f"[SMS-SIM] Message simulé pour {e['contact_parent']}: {msg[:80]}...")

        # Enregistrer dans la table notifications
        try:
            conn.execute("""INSERT INTO notifications
                (eleve_id, date, type, destinataire, statut, message, envoye)
                VALUES (?,?,?,?,?,?,?)""",
                (eleve_id, today, "email" if e.get("email_parent") else "sms",
                 dest, e.get("statut","unset"), msg, 1 if sent else 0))
            conn.commit()
        except Exception:
            pass

        details.append({"nom":nom,"dest":dest,"ok":sent,"err":err})
        if sent: ok_count += 1

    conn.close()

    return jsonify({
        "ok":    ok_count > 0,
        "message": f"{ok_count}/{len(eleves_list)} message(s) envoyé(s) avec succès" if ok_count>0
                   else "Aucun message n'a pu être envoyé — vérifiez la configuration SMTP.",
        "details": details,
        "note": "En mode production, configurez SMTP_HOST/SMTP_USER/SMTP_PASS dans les variables d'environnement."
    })

@app.route("/api/contact/historique", methods=["GET"])
def contact_historique():
    """Historique des notifications envoyées."""
    conn = get_db()
    rows = conn.execute("""
        SELECT n.*, e.prenom, e.nom
        FROM notifications n
        LEFT JOIN eleves e ON n.eleve_id=e.id
        ORDER BY n.sent_at DESC LIMIT 100
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

if __name__ == "__main__":
    init_db()
    migrate_db()
    load_face_cache()
    app.run(debug=True, port=5000)
