"""Module de gestion de la base de données SQLite pour le suivi de projets."""

import sqlite3
import os
import json
import shutil
import hashlib
import secrets
import glob as glob_mod
from datetime import datetime
from contextlib import contextmanager

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "data", "projets.db")
BACKUP_DIR = os.path.join(BASE_DIR, "data", "backups")
SESSION_FILE = os.path.join(BASE_DIR, "data", "sessions.json")
MAX_BACKUPS = 20

os.makedirs(BACKUP_DIR, exist_ok=True)


def backup_db():
    """Crée un backup horodaté de la base avant chaque écriture."""
    if not os.path.exists(DB_PATH):
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"projets_{timestamp}.db")
    # Éviter les backups trop rapprochés (< 30s)
    existing = sorted(glob_mod.glob(os.path.join(BACKUP_DIR, "projets_*.db")))
    if existing:
        last = os.path.getmtime(existing[-1])
        if (datetime.now().timestamp() - last) < 30:
            return
    shutil.copy2(DB_PATH, backup_path)
    # Nettoyer les anciens backups
    if len(existing) >= MAX_BACKUPS:
        for old in existing[:len(existing) - MAX_BACKUPS + 1]:
            os.remove(old)


# --- Sessions persistantes (fichier JSON) ---

def save_session(user_nom, page="dashboard", tache_id=None, projet_id=None):
    """Sauvegarde l'état de session dans un fichier JSON."""
    sessions = load_all_sessions()
    sessions[user_nom] = {
        "page": page,
        "tache_id": tache_id,
        "projet_id": projet_id,
        "last_login": datetime.now().isoformat(),
    }
    # Garder aussi le dernier utilisateur connecté globalement
    sessions["__last_user__"] = user_nom
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)


def load_all_sessions():
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def load_session(user_nom=None):
    """Charge la session d'un utilisateur, ou du dernier utilisateur connecté."""
    sessions = load_all_sessions()
    if user_nom is None:
        user_nom = sessions.get("__last_user__")
    if user_nom and user_nom in sessions:
        data = sessions[user_nom]
        data["user"] = user_nom
        return data
    return None


def get_last_user():
    sessions = load_all_sessions()
    return sessions.get("__last_user__")


@contextmanager
def get_connection(readonly=False):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        if not readonly:
            conn.commit()
    finally:
        conn.close()


@contextmanager
def get_write_connection():
    """Connexion en écriture avec backup automatique avant modification."""
    backup_db()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def _hash_password(password, salt=None):
    """Hash un mot de passe avec un salt aléatoire."""
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()
    return f"{salt}:{h}"


def _verify_password(password, stored_hash):
    """Vérifie un mot de passe contre le hash stocké."""
    if not stored_hash:
        return False
    salt, h = stored_hash.split(":", 1)
    return _hash_password(password, salt) == stored_hash


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS utilisateurs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT UNIQUE NOT NULL,
                email TEXT,
                password_hash TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS projets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT NOT NULL,
                description TEXT,
                statut TEXT DEFAULT 'Actif',
                deadline TEXT,
                cree_par TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                updated_at TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS taches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                projet_id INTEGER NOT NULL,
                titre TEXT NOT NULL,
                description TEXT,
                statut TEXT DEFAULT 'À faire',
                priorite TEXT DEFAULT 'Moyenne',
                assigne_a TEXT,
                deadline TEXT,
                cree_par TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                updated_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (projet_id) REFERENCES projets(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS commentaires (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tache_id INTEGER NOT NULL,
                auteur TEXT NOT NULL,
                contenu TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (tache_id) REFERENCES taches(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS pieces_jointes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                projet_id INTEGER,
                tache_id INTEGER,
                nom_fichier TEXT NOT NULL,
                chemin TEXT NOT NULL,
                uploade_par TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (projet_id) REFERENCES projets(id) ON DELETE CASCADE,
                FOREIGN KEY (tache_id) REFERENCES taches(id) ON DELETE CASCADE
            );
        """)
        # Migration : ajouter password_hash si la colonne n'existe pas
        cols = [row[1] for row in conn.execute("PRAGMA table_info(utilisateurs)").fetchall()]
        if "password_hash" not in cols:
            conn.execute("ALTER TABLE utilisateurs ADD COLUMN password_hash TEXT")

# --- Utilisateurs ---

def get_utilisateurs():
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM utilisateurs ORDER BY nom").fetchall()]

def ajouter_utilisateur(nom, email="", password=None):
    with get_write_connection() as conn:
        pw_hash = _hash_password(password) if password else None
        conn.execute("INSERT OR IGNORE INTO utilisateurs (nom, email, password_hash) VALUES (?, ?, ?)", (nom, email, pw_hash))


def definir_mot_de_passe(nom, password):
    with get_write_connection() as conn:
        pw_hash = _hash_password(password)
        conn.execute("UPDATE utilisateurs SET password_hash=? WHERE nom=?", (pw_hash, nom))


def verifier_mot_de_passe(nom, password):
    with get_connection() as conn:
        row = conn.execute("SELECT password_hash FROM utilisateurs WHERE nom=?", (nom,)).fetchone()
        if not row:
            return False
        return _verify_password(password, row["password_hash"])


def utilisateur_a_mot_de_passe(nom):
    with get_connection() as conn:
        row = conn.execute("SELECT password_hash FROM utilisateurs WHERE nom=?", (nom,)).fetchone()
        return row is not None and row["password_hash"] is not None


def get_noms_utilisateurs():
    return [u["nom"] for u in get_utilisateurs()]

# --- Projets ---

def get_projets(statut=None):
    with get_connection() as conn:
        if statut:
            rows = conn.execute("SELECT * FROM projets WHERE statut=? ORDER BY deadline, created_at DESC", (statut,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM projets ORDER BY deadline, created_at DESC").fetchall()
        return [dict(r) for r in rows]

def get_projet(projet_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM projets WHERE id=?", (projet_id,)).fetchone()
        return dict(row) if row else None

def creer_projet(nom, description, deadline, cree_par):
    with get_write_connection() as conn:
        cur = conn.execute(
            "INSERT INTO projets (nom, description, deadline, cree_par) VALUES (?, ?, ?, ?)",
            (nom, description, deadline, cree_par)
        )
        return cur.lastrowid

def modifier_projet(projet_id, nom, description, statut, deadline):
    with get_write_connection() as conn:
        conn.execute(
            "UPDATE projets SET nom=?, description=?, statut=?, deadline=?, updated_at=datetime('now','localtime') WHERE id=?",
            (nom, description, statut, deadline, projet_id)
        )

def supprimer_projet(projet_id):
    with get_write_connection() as conn:
        conn.execute("DELETE FROM projets WHERE id=?", (projet_id,))

def dupliquer_projet(projet_id, nouveau_nom, cree_par, copier_taches=True, copier_docs=False, reset_statut=True):
    """Duplique un projet existant avec ses tâches et optionnellement ses documents."""
    import shutil

    projet = get_projet(projet_id)
    if not projet:
        return None

    # Créer le nouveau projet
    new_projet_id = creer_projet(
        nouveau_nom,
        projet.get("description", ""),
        projet.get("deadline"),
        cree_par
    )

    if copier_taches:
        taches = get_taches(projet_id=projet_id)
        for t in taches:
            creer_tache(
                new_projet_id,
                t["titre"],
                t.get("description", ""),
                t["priorite"],
                t.get("assigne_a", ""),
                t.get("deadline"),
                cree_par,
            )

    if copier_docs:
        pjs = get_pieces_jointes(projet_id=projet_id)
        upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
        for pj in pjs:
            if os.path.exists(pj["chemin"]):
                new_name = f"proj_{new_projet_id}_{pj['nom_fichier']}"
                new_path = os.path.join(upload_dir, new_name)
                shutil.copy2(pj["chemin"], new_path)
                ajouter_piece_jointe(pj["nom_fichier"], new_path, cree_par, projet_id=new_projet_id)

    return new_projet_id

# --- Tâches ---

def get_taches(projet_id=None, statut=None, assigne_a=None):
    with get_connection() as conn:
        query = "SELECT t.*, p.nom as projet_nom FROM taches t JOIN projets p ON t.projet_id=p.id WHERE 1=1"
        params = []
        if projet_id:
            query += " AND t.projet_id=?"
            params.append(projet_id)
        if statut:
            query += " AND t.statut=?"
            params.append(statut)
        if assigne_a:
            query += " AND t.assigne_a=?"
            params.append(assigne_a)
        query += " ORDER BY CASE t.priorite WHEN 'Critique' THEN 0 WHEN 'Haute' THEN 1 WHEN 'Moyenne' THEN 2 WHEN 'Basse' THEN 3 END, t.deadline"
        return [dict(r) for r in conn.execute(query, params).fetchall()]

def get_tache(tache_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT t.*, p.nom as projet_nom FROM taches t JOIN projets p ON t.projet_id=p.id WHERE t.id=?",
            (tache_id,)
        ).fetchone()
        return dict(row) if row else None

def creer_tache(projet_id, titre, description, priorite, assigne_a, deadline, cree_par):
    with get_write_connection() as conn:
        cur = conn.execute(
            "INSERT INTO taches (projet_id, titre, description, priorite, assigne_a, deadline, cree_par) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (projet_id, titre, description, priorite, assigne_a, deadline, cree_par)
        )
        return cur.lastrowid

def modifier_tache(tache_id, **kwargs):
    with get_write_connection() as conn:
        sets = []
        params = []
        for k, v in kwargs.items():
            sets.append(f"{k}=?")
            params.append(v)
        sets.append("updated_at=datetime('now','localtime')")
        params.append(tache_id)
        conn.execute(f"UPDATE taches SET {', '.join(sets)} WHERE id=?", params)

def supprimer_tache(tache_id):
    with get_write_connection() as conn:
        conn.execute("DELETE FROM taches WHERE id=?", (tache_id,))

def deplacer_tache(tache_id, nouveau_statut):
    modifier_tache(tache_id, statut=nouveau_statut)

# --- Commentaires ---

def get_commentaires(tache_id):
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM commentaires WHERE tache_id=? ORDER BY created_at DESC", (tache_id,)
        ).fetchall()]

def ajouter_commentaire(tache_id, auteur, contenu):
    with get_write_connection() as conn:
        conn.execute(
            "INSERT INTO commentaires (tache_id, auteur, contenu) VALUES (?, ?, ?)",
            (tache_id, auteur, contenu)
        )

# --- Pièces jointes ---

def get_pieces_jointes(projet_id=None, tache_id=None):
    with get_connection() as conn:
        if tache_id:
            rows = conn.execute("SELECT * FROM pieces_jointes WHERE tache_id=? ORDER BY created_at DESC", (tache_id,)).fetchall()
        elif projet_id:
            rows = conn.execute("SELECT * FROM pieces_jointes WHERE projet_id=? ORDER BY created_at DESC", (projet_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM pieces_jointes ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

def ajouter_piece_jointe(nom_fichier, chemin, uploade_par, projet_id=None, tache_id=None):
    with get_write_connection() as conn:
        conn.execute(
            "INSERT INTO pieces_jointes (projet_id, tache_id, nom_fichier, chemin, uploade_par) VALUES (?, ?, ?, ?, ?)",
            (projet_id, tache_id, nom_fichier, chemin, uploade_par)
        )

def supprimer_piece_jointe(pj_id):
    with get_write_connection() as conn:
        row = conn.execute("SELECT chemin FROM pieces_jointes WHERE id=?", (pj_id,)).fetchone()
        if row and os.path.exists(row["chemin"]):
            os.remove(row["chemin"])
        conn.execute("DELETE FROM pieces_jointes WHERE id=?", (pj_id,))

# --- Stats ---

def get_stats():
    with get_connection() as conn:
        stats = {}
        stats["total_projets"] = conn.execute("SELECT COUNT(*) FROM projets").fetchone()[0]
        stats["projets_actifs"] = conn.execute("SELECT COUNT(*) FROM projets WHERE statut='Actif'").fetchone()[0]
        stats["total_taches"] = conn.execute("SELECT COUNT(*) FROM taches").fetchone()[0]
        stats["taches_terminees"] = conn.execute("SELECT COUNT(*) FROM taches WHERE statut='Terminé'").fetchone()[0]
        stats["taches_en_cours"] = conn.execute("SELECT COUNT(*) FROM taches WHERE statut='En cours'").fetchone()[0]
        stats["taches_a_faire"] = conn.execute("SELECT COUNT(*) FROM taches WHERE statut='À faire'").fetchone()[0]
        stats["taches_en_retard"] = conn.execute(
            "SELECT COUNT(*) FROM taches WHERE deadline < date('now','localtime') AND statut != 'Terminé'"
        ).fetchone()[0]

        stats["par_priorite"] = [dict(r) for r in conn.execute(
            "SELECT priorite, COUNT(*) as nb FROM taches WHERE statut != 'Terminé' GROUP BY priorite"
        ).fetchall()]

        stats["par_utilisateur"] = [dict(r) for r in conn.execute(
            "SELECT assigne_a, statut, COUNT(*) as nb FROM taches WHERE assigne_a IS NOT NULL AND assigne_a != '' GROUP BY assigne_a, statut"
        ).fetchall()]

        stats["projets_avancement"] = [dict(r) for r in conn.execute("""
            SELECT p.id, p.nom, p.deadline,
                   COUNT(t.id) as total_taches,
                   SUM(CASE WHEN t.statut='Terminé' THEN 1 ELSE 0 END) as taches_terminees
            FROM projets p
            LEFT JOIN taches t ON t.projet_id = p.id
            WHERE p.statut = 'Actif'
            GROUP BY p.id
        """).fetchall()]

        return stats
