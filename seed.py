"""Initialise les utilisateurs et projets par défaut au premier lancement."""

import json
import os
import shutil

from database import (
    init_db, get_noms_utilisateurs, get_projets, ajouter_utilisateur,
    creer_projet, creer_tache, ajouter_commentaire, ajouter_piece_jointe
)

BASE_DIR = os.path.dirname(__file__)
SEED_FILE = os.path.join(BASE_DIR, "data", "seed_data.json")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")


def seed():
    init_db()
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Seed utilisateurs
    if not get_noms_utilisateurs():
        if os.path.exists(SEED_FILE):
            with open(SEED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for u in data.get("utilisateurs", []):
                ajouter_utilisateur(u["nom"], u.get("email", ""))
        else:
            for nom, email in [
                ("Romain", "romain@sconseil.be"),
                ("Clara", "Clara@sconseil.be"),
                ("Yves", "yves@sconseil.be"),
                ("Evelyne", "evelyne@sconseil.be"),
            ]:
                ajouter_utilisateur(nom, email)

    # Seed projets (seulement si aucun projet n'existe)
    if not get_projets() and os.path.exists(SEED_FILE):
        with open(SEED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        for p in data.get("projets", []):
            projet_id = creer_projet(
                p["nom"],
                p.get("description", ""),
                p.get("deadline"),
                p.get("cree_par", "Romain"),
            )

            for t in p.get("taches", []):
                tache_id = creer_tache(
                    projet_id,
                    t["titre"],
                    t.get("description", ""),
                    t.get("priorite", "Moyenne"),
                    t.get("assigne_a", ""),
                    t.get("deadline"),
                    t.get("cree_par", "Romain"),
                )
                for c in t.get("commentaires", []):
                    ajouter_commentaire(tache_id, c["auteur"], c["contenu"])

            # Pièces jointes : copier depuis docs/ vers uploads/
            for pj in p.get("pieces_jointes", []):
                src_name = f"proj_{p['id']}_{pj['nom_fichier']}"
                src_path = os.path.join(DOCS_DIR, src_name)
                if os.path.exists(src_path):
                    dest_path = os.path.join(UPLOAD_DIR, f"proj_{projet_id}_{pj['nom_fichier']}")
                    shutil.copy2(src_path, dest_path)
                    ajouter_piece_jointe(
                        pj["nom_fichier"], dest_path,
                        pj.get("uploade_par", "Romain"),
                        projet_id=projet_id
                    )


if __name__ == "__main__":
    seed()
    print("Seed termine. Utilisateurs:", get_noms_utilisateurs())
    print("Projets:", len(get_projets()))
