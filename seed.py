"""Initialise les utilisateurs par défaut au premier lancement."""

from database import init_db, get_noms_utilisateurs, ajouter_utilisateur

UTILISATEURS_DEFAUT = [
    ("Romain", "romain@sconseil.be"),
    ("Clara", "Clara@sconseil.be"),
    ("Yves", "yves@sconseil.be"),
    ("Evelyne", "evelyne@sconseil.be"),
]


def seed_utilisateurs():
    init_db()
    existants = get_noms_utilisateurs()
    for nom, email in UTILISATEURS_DEFAUT:
        if nom not in existants:
            ajouter_utilisateur(nom, email)


if __name__ == "__main__":
    seed_utilisateurs()
    print("Utilisateurs initialises:", get_noms_utilisateurs())
