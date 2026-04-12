"""
Application de Suivi de Projets & Tâches
Streamlit - Multi-utilisateurs - Notifications Outlook
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import shutil
from datetime import datetime, date, timedelta

from database import (
    init_db, get_projets, get_projet, creer_projet, modifier_projet, supprimer_projet,
    dupliquer_projet,
    get_taches, get_tache, creer_tache, modifier_tache, supprimer_tache, deplacer_tache,
    get_commentaires, ajouter_commentaire,
    get_pieces_jointes, ajouter_piece_jointe, supprimer_piece_jointe,
    get_utilisateurs, ajouter_utilisateur, get_noms_utilisateurs, get_stats,
    save_session, load_session, get_last_user,
    verifier_mot_de_passe, utilisateur_a_mot_de_passe, definir_mot_de_passe
)
from notifications import (
    notifier_assignation, notifier_commentaire, notifier_statut_change, notifier_deadline
)
from extracteur import extraire_document

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

STATUTS_TACHE = ["À faire", "En cours", "En revue", "Terminé"]
PRIORITES = ["Basse", "Moyenne", "Haute", "Critique"]
STATUTS_PROJET = ["Actif", "En pause", "Terminé", "Annulé"]

COULEURS_PRIORITE = {"Basse": "#4caf50", "Moyenne": "#2196f3", "Haute": "#ff9800", "Critique": "#f44336"}
COULEURS_STATUT = {"À faire": "#9e9e9e", "En cours": "#2196f3", "En revue": "#ff9800", "Terminé": "#4caf50"}

# --- Init ---

st.set_page_config(page_title="Suivi de Projets", page_icon="📋", layout="wide")
init_db()

# Seed des utilisateurs et projets par défaut au premier lancement
from seed import seed
seed()

# --- CSS ---

st.markdown("""
<style>
    .kanban-card {
        background: white;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.12);
        border-left: 4px solid #2196f3;
    }
    .kanban-card.critique { border-left-color: #f44336; }
    .kanban-card.haute { border-left-color: #ff9800; }
    .kanban-card.moyenne { border-left-color: #2196f3; }
    .kanban-card.basse { border-left-color: #4caf50; }
    .kanban-header {
        font-size: 1.1em;
        font-weight: 600;
        padding: 8px 12px;
        border-radius: 6px;
        margin-bottom: 12px;
        text-align: center;
    }
    .stat-card {
        background: white;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .overdue { color: #f44336; font-weight: bold; }
    .badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8em;
        color: white;
        font-weight: 500;
    }
    div[data-testid="stExpander"] { border: none; }
</style>
""", unsafe_allow_html=True)

# --- Session persistante ---

def restore_session():
    """Restaure la session depuis les query params, puis le fichier JSON."""
    params = st.query_params

    # Initialiser toutes les clés session avec des valeurs par défaut
    if "utilisateur" not in st.session_state:
        st.session_state.utilisateur = None
    if "logged_out" not in st.session_state:
        st.session_state.logged_out = False

    # Ne pas auto-reconnecter si l'utilisateur vient de se déconnecter
    if st.session_state.logged_out:
        st.session_state.utilisateur = None
        return

    # 1. Restaurer l'utilisateur
    if st.session_state.utilisateur is None:
        # D'abord depuis l'URL
        if "user" in params:
            st.session_state.utilisateur = params["user"]
        else:
            # Sinon depuis le fichier de session (dernier utilisateur)
            last_user = get_last_user()
            if last_user:
                st.session_state.utilisateur = last_user

    # 2. Restaurer la page
    if "page" not in st.session_state:
        if "page" in params:
            st.session_state.page = params["page"]
        else:
            saved = load_session(st.session_state.get("utilisateur"))
            st.session_state.page = saved["page"] if saved else "dashboard"
    elif "page" in params and st.session_state.page == "dashboard":
        st.session_state.page = params["page"]

    # 3. Restaurer la tâche/projet sélectionné
    if "tache_selectionnee" not in st.session_state:
        if "tache" in params:
            try:
                st.session_state.tache_selectionnee = int(params["tache"])
            except (ValueError, TypeError):
                st.session_state.tache_selectionnee = None
        else:
            saved = load_session(st.session_state.get("utilisateur"))
            st.session_state.tache_selectionnee = saved.get("tache_id") if saved else None

    if "projet_selectionne" not in st.session_state:
        st.session_state.projet_selectionne = None

    if "wizard_step" not in st.session_state:
        st.session_state.wizard_step = 0
    if "wizard_data" not in st.session_state:
        st.session_state.wizard_data = {}


def sync_session():
    """Sauvegarde l'état courant dans le fichier JSON et les query params."""
    user = st.session_state.get("utilisateur")
    if user:
        page = st.session_state.get("page", "dashboard")
        tache_id = st.session_state.get("tache_selectionnee")
        projet_id = st.session_state.get("projet_selectionne")
        save_session(user, page, tache_id, projet_id)
        # Mettre à jour l'URL
        new_params = {"user": user, "page": page}
        if tache_id:
            new_params["tache"] = str(tache_id)
        st.query_params.update(new_params)


restore_session()

# --- Login ---

def page_login():
    st.markdown("## Suivi de Projets & Taches")
    st.markdown("---")

    utilisateurs = get_noms_utilisateurs()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Se connecter")
        if utilisateurs:
            last = get_last_user()
            default_idx = utilisateurs.index(last) if last and last in utilisateurs else 0
            choix = st.selectbox("Choisir un utilisateur", utilisateurs, index=default_idx, key="login_user")

            if not utilisateur_a_mot_de_passe(choix):
                # Première connexion : créer un mot de passe
                st.info(f"Premiere connexion pour **{choix}**. Creez votre mot de passe.")
                pw1 = st.text_input("Nouveau mot de passe", type="password", key="new_pw1")
                pw2 = st.text_input("Confirmer le mot de passe", type="password", key="new_pw2")
                if st.button("Creer mon mot de passe et me connecter", type="primary", use_container_width=True):
                    if not pw1:
                        st.error("Le mot de passe ne peut pas etre vide.")
                    elif pw1 != pw2:
                        st.error("Les mots de passe ne correspondent pas.")
                    elif len(pw1) < 4:
                        st.error("Le mot de passe doit faire au moins 4 caracteres.")
                    else:
                        definir_mot_de_passe(choix, pw1)
                        st.session_state.utilisateur = choix
                        st.session_state.logged_out = False
                        save_session(choix, "dashboard")
                        st.rerun()
            else:
                # Connexion avec mot de passe
                pw = st.text_input("Mot de passe", type="password", key="login_pw")
                if st.button("Connexion", type="primary", use_container_width=True):
                    if verifier_mot_de_passe(choix, pw):
                        st.session_state.utilisateur = choix
                        st.session_state.logged_out = False
                        saved = load_session(choix)
                        if saved:
                            st.session_state.page = saved.get("page", "dashboard")
                            st.session_state.tache_selectionnee = saved.get("tache_id")
                        save_session(choix, st.session_state.page, st.session_state.get("tache_selectionnee"))
                        st.rerun()
                    else:
                        st.error("Mot de passe incorrect.")
        else:
            st.info("Aucun utilisateur. Creez-en un pour commencer.")

    with col2:
        st.markdown("#### Nouvel utilisateur")
        nouveau_nom = st.text_input("Nom", key="new_user_name")
        nouveau_email = st.text_input("Email (pour les notifications)", key="new_user_email")
        nouveau_pw1 = st.text_input("Mot de passe", type="password", key="new_user_pw1")
        nouveau_pw2 = st.text_input("Confirmer mot de passe", type="password", key="new_user_pw2")
        if st.button("Creer", use_container_width=True):
            if not nouveau_nom.strip():
                st.error("Le nom est obligatoire.")
            elif not nouveau_pw1:
                st.error("Le mot de passe est obligatoire.")
            elif nouveau_pw1 != nouveau_pw2:
                st.error("Les mots de passe ne correspondent pas.")
            elif len(nouveau_pw1) < 4:
                st.error("Le mot de passe doit faire au moins 4 caracteres.")
            elif nouveau_nom.strip() in utilisateurs:
                st.error("Cet utilisateur existe deja.")
            else:
                ajouter_utilisateur(nouveau_nom.strip(), nouveau_email.strip(), nouveau_pw1)
                st.success(f"Utilisateur '{nouveau_nom}' cree !")
                st.rerun()


if not st.session_state.utilisateur:
    page_login()
    st.stop()

# --- Sidebar ---

with st.sidebar:
    st.markdown(f"### Connecte : **{st.session_state.utilisateur}**")
    st.markdown("---")

    if st.button("Dashboard", use_container_width=True, type="primary" if st.session_state.page == "dashboard" else "secondary"):
        st.session_state.page = "dashboard"
        st.rerun()
    if st.button("Nouveau projet (Assistant)", use_container_width=True, type="primary" if st.session_state.page == "wizard" else "secondary"):
        st.session_state.page = "wizard"
        st.session_state.wizard_step = 0
        st.session_state.wizard_data = {}
        st.rerun()
    if st.button("Mes projets", use_container_width=True, type="primary" if st.session_state.page == "projets" else "secondary"):
        st.session_state.page = "projets"
        st.rerun()
    if st.button("Kanban", use_container_width=True, type="primary" if st.session_state.page == "kanban" else "secondary"):
        st.session_state.page = "kanban"
        st.rerun()
    if st.button("Mes taches", use_container_width=True, type="primary" if st.session_state.page == "mes_taches" else "secondary"):
        st.session_state.page = "mes_taches"
        st.rerun()

    st.markdown("---")
    # Tâches en retard
    taches_retard = [t for t in get_taches() if t["deadline"] and t["deadline"] < date.today().isoformat() and t["statut"] != "Terminé"]
    if taches_retard:
        st.markdown(f"**:red[{len(taches_retard)} tache(s) en retard]**")
        for t in taches_retard[:5]:
            st.markdown(f"- :red[{t['titre']}] ({t['deadline']})")

    st.markdown("---")
    # --- Gestion des utilisateurs ---
    with st.popover("Gerer les utilisateurs", use_container_width=True):
        st.markdown("**Ajouter un utilisateur**")
        new_name = st.text_input("Nom", key="sidebar_new_user")
        new_email = st.text_input("Email Outlook", key="sidebar_new_email")
        new_pw = st.text_input("Mot de passe", type="password", key="sidebar_new_pw")
        if st.button("Ajouter", key="sidebar_add_user", type="primary"):
            if not new_name.strip():
                st.error("Le nom est obligatoire.")
            elif not new_pw or len(new_pw) < 4:
                st.error("Mot de passe requis (min 4 caracteres).")
            else:
                ajouter_utilisateur(new_name.strip(), new_email.strip(), new_pw)
                st.success(f"'{new_name}' ajoute !")
                st.rerun()
        st.markdown("---")
        st.markdown("**Utilisateurs existants**")
        for u in get_utilisateurs():
            has_pw = "ok" if u.get("password_hash") else "pas de mdp"
            st.markdown(f"- **{u['nom']}** ({u.get('email', '') or 'pas d email'}) — {has_pw}")

    if st.button("Deconnexion", use_container_width=True):
        # Sauvegarder l'état avant déconnexion
        sync_session()
        st.session_state.utilisateur = None
        st.session_state.page = "dashboard"
        st.session_state.logged_out = True
        st.query_params.clear()
        st.rerun()


# =====================================================================
# ASSISTANT DE CREATION DE PROJET (Wizard)
# =====================================================================

def page_wizard():
    st.markdown("## Assistant de creation de projet")
    step = st.session_state.wizard_step
    data = st.session_state.wizard_data

    # Progress bar
    steps_labels = ["Definition", "Objectifs & Livrables", "Taches", "Planning", "Recapitulatif"]
    progress = step / (len(steps_labels) - 1)
    st.progress(progress)
    cols = st.columns(len(steps_labels))
    for i, label in enumerate(steps_labels):
        with cols[i]:
            if i == step:
                st.markdown(f"**:blue[{i+1}. {label}]**")
            elif i < step:
                st.markdown(f"~~{i+1}. {label}~~")
            else:
                st.markdown(f"{i+1}. {label}")
    st.markdown("---")

    # --- Etape 0 : Définition ---
    if step == 0:
        st.markdown("### Definissons votre projet")

        # --- Import de document ---
        st.markdown("#### Importer un document source")
        st.markdown(
            "Deposez un document (cahier des charges, brief, plan...) pour **pre-remplir automatiquement** "
            "les informations du projet. Formats supportes : Word, Excel, PDF, texte."
        )

        uploaded_doc = st.file_uploader(
            "Choisir un document",
            type=["docx", "xlsx", "xls", "pdf", "txt", "md", "csv"],
            key="wizard_doc_upload"
        )

        if uploaded_doc and not data.get("_doc_imported"):
            # Sauvegarder le fichier
            doc_path = os.path.join(UPLOAD_DIR, f"import_{uploaded_doc.name}")
            with open(doc_path, "wb") as f:
                f.write(uploaded_doc.getbuffer())
            data["_doc_path"] = doc_path
            data["_doc_name"] = uploaded_doc.name

            # Extraire les infos
            with st.spinner("Analyse du document en cours..."):
                try:
                    extraction = extraire_document(doc_path)
                    if extraction:
                        # Pré-remplir les champs seulement s'ils sont vides
                        if extraction.get("nom") and not data.get("nom"):
                            data["nom"] = extraction["nom"]
                        if extraction.get("description") and not data.get("description"):
                            data["description"] = extraction["description"]
                        if extraction.get("categorie") and extraction["categorie"] != "Autre":
                            data["categorie"] = extraction["categorie"]
                        if extraction.get("objectifs"):
                            data["objectifs"] = extraction["objectifs"] + [""] * (10 - len(extraction["objectifs"]))
                            data["nb_objectifs"] = len(extraction["objectifs"])
                        if extraction.get("livrables"):
                            data["livrables"] = extraction["livrables"]
                        if extraction.get("contraintes"):
                            data["contraintes"] = extraction["contraintes"]
                        if extraction.get("taches"):
                            data["taches"] = extraction["taches"]
                            data["nb_taches"] = len(extraction["taches"])

                        data["_doc_imported"] = True
                        data["_texte_brut"] = extraction.get("texte_brut", "")
                        st.session_state.wizard_data = data

                        nb_taches = len(extraction.get("taches", []))
                        nb_obj = len(extraction.get("objectifs", []))
                        st.success(
                            f"Document analyse ! "
                            f"{'Nom, ' if extraction.get('nom') else ''}"
                            f"{'description, ' if extraction.get('description') else ''}"
                            f"{f'{nb_obj} objectif(s), ' if nb_obj else ''}"
                            f"{f'{nb_taches} tache(s), ' if nb_taches else ''}"
                            f"pre-rempli(s). Verifiez et ajustez ci-dessous."
                        )
                        st.rerun()
                    else:
                        st.warning("Le document a ete importe mais aucune information n'a pu etre extraite. Remplissez les champs manuellement.")
                        data["_doc_imported"] = True
                except ImportError as e:
                    st.error(f"Module manquant : {e}")
                except Exception as e:
                    st.error(f"Erreur lors de l'analyse : {e}")
                    data["_doc_imported"] = True

        if data.get("_doc_imported"):
            st.info(f"Document source : **{data.get('_doc_name', '')}** (sera attache au projet)")
            if st.button("Reinitialiser l'import", key="reset_import"):
                for k in ["_doc_imported", "_doc_path", "_doc_name", "_texte_brut"]:
                    data.pop(k, None)
                # Vider les champs pré-remplis
                for k in ["nom", "description", "objectifs", "livrables", "contraintes", "taches"]:
                    data.pop(k, None)
                st.session_state.wizard_data = data
                st.rerun()

            # Aperçu du texte extrait
            if data.get("_texte_brut"):
                with st.expander("Apercu du contenu extrait"):
                    st.text(data["_texte_brut"][:5000])

        st.markdown("---")
        st.markdown("#### Informations du projet")
        st.markdown("*Modifiez les champs pre-remplis si necessaire, ou saisissez manuellement.*")

        data["nom"] = st.text_input("Nom du projet *", value=data.get("nom", ""), placeholder="Ex: Migration ERP, Refonte site web...")
        data["description"] = st.text_area(
            "Decrivez le projet en quelques phrases *",
            value=data.get("description", ""),
            placeholder="Quel est le contexte ? Quel probleme resout-il ? Qui est concerne ?",
            height=120
        )
        categories = ["Developpement", "Infrastructure", "Organisation", "Communication", "Formation", "Autre"]
        data["categorie"] = st.selectbox(
            "Type de projet",
            categories,
            index=categories.index(data.get("categorie", "Developpement")) if data.get("categorie", "Developpement") in categories else 0
        )

        col1, col2 = st.columns(2)
        with col2:
            if st.button("Suivant →", type="primary", use_container_width=True):
                if data.get("nom") and data.get("description"):
                    st.session_state.wizard_data = data
                    st.session_state.wizard_step = 1
                    st.rerun()
                else:
                    st.error("Le nom et la description sont obligatoires.")

    # --- Etape 1 : Objectifs & Livrables ---
    elif step == 1:
        st.markdown("### Objectifs et livrables")
        st.markdown("Definissez ce que le projet doit accomplir et produire.")

        nb_obj = data.get("nb_objectifs", 3)
        data["nb_objectifs"] = st.number_input("Nombre d'objectifs", min_value=1, max_value=10, value=nb_obj)

        objectifs = data.get("objectifs", [""] * 10)
        for i in range(data["nb_objectifs"]):
            objectifs[i] = st.text_input(f"Objectif {i+1}", value=objectifs[i], key=f"obj_{i}",
                                         placeholder="Ex: Reduire les delais de traitement de 50%")
        data["objectifs"] = objectifs

        st.markdown("---")
        data["livrables"] = st.text_area(
            "Livrables attendus (un par ligne)",
            value=data.get("livrables", ""),
            placeholder="Ex:\nDocument de specifications\nPrototype fonctionnel\nRapport de tests",
            height=100
        )

        data["contraintes"] = st.text_area(
            "Contraintes ou risques identifies (optionnel)",
            value=data.get("contraintes", ""),
            placeholder="Budget limité, dépendance externe, ressources partagées...",
            height=80
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("← Precedent", use_container_width=True):
                st.session_state.wizard_data = data
                st.session_state.wizard_step = 0
                st.rerun()
        with col2:
            if st.button("Suivant →", type="primary", use_container_width=True):
                st.session_state.wizard_data = data
                st.session_state.wizard_step = 2
                st.rerun()

    # --- Etape 2 : Tâches ---
    elif step == 2:
        st.markdown("### Decomposition en taches")
        st.markdown(
            "Listez les taches necessaires. Pour chaque tache, indiquez ses **dependances** : "
            "les taches qui doivent etre terminees avant qu'elle puisse commencer. "
            "Une tache sans dependance demarrera des le debut du projet (en parallele)."
        )

        nb_taches = data.get("nb_taches", 5)
        data["nb_taches"] = st.number_input("Nombre de taches", min_value=1, max_value=30, value=nb_taches)

        utilisateurs = get_noms_utilisateurs()
        taches = data.get("taches", [])
        # Ensure list is big enough
        while len(taches) < data["nb_taches"]:
            taches.append({"titre": "", "priorite": "Moyenne", "assigne": "", "duree_jours": 5, "depends_on": []})

        # Ensure all tasks have depends_on field
        for t in taches:
            if "depends_on" not in t:
                t["depends_on"] = []

        # Build list of task labels for dependency selection
        def get_task_label(idx):
            t = taches[idx]
            titre = t["titre"] if t["titre"] else f"(sans titre)"
            return f"T{idx+1}: {titre}"

        for i in range(data["nb_taches"]):
            dep_label = ""
            if taches[i]["depends_on"]:
                dep_refs = [f"T{d+1}" for d in taches[i]["depends_on"] if d < data["nb_taches"]]
                dep_label = f" (apres {', '.join(dep_refs)})" if dep_refs else ""
            elif taches[i]["titre"]:
                dep_label = " (parallele)"

            with st.expander(
                f"Tache {i+1}" + (f" : {taches[i]['titre']}" if taches[i]["titre"] else "") + dep_label,
                expanded=i < 3
            ):
                c1, c2, c3 = st.columns([3, 1, 1])
                with c1:
                    taches[i]["titre"] = st.text_input("Titre", value=taches[i]["titre"], key=f"t_titre_{i}",
                                                        placeholder="Ex: Rediger le cahier des charges")
                with c2:
                    taches[i]["priorite"] = st.selectbox("Priorite", PRIORITES,
                                                          index=PRIORITES.index(taches[i].get("priorite", "Moyenne")),
                                                          key=f"t_prio_{i}")
                with c3:
                    options = [""] + utilisateurs
                    idx = options.index(taches[i]["assigne"]) if taches[i]["assigne"] in options else 0
                    taches[i]["assigne"] = st.selectbox("Assigne a", options, index=idx, key=f"t_assign_{i}")

                c_dur, c_dep = st.columns([1, 2])
                with c_dur:
                    taches[i]["duree_jours"] = st.slider("Duree (jours)", 1, 60,
                                                          value=taches[i].get("duree_jours", 5), key=f"t_duree_{i}")
                with c_dep:
                    # Only allow depending on previous tasks (no circular deps)
                    predecessors_available = [j for j in range(i) if taches[j]["titre"].strip()]
                    if predecessors_available:
                        pred_labels = [get_task_label(j) for j in predecessors_available]
                        # Current selection
                        current_deps = [j for j in taches[i]["depends_on"] if j in predecessors_available]
                        current_labels = [get_task_label(j) for j in current_deps]

                        selected = st.multiselect(
                            "Demarre apres (dependances)",
                            options=pred_labels,
                            default=current_labels,
                            key=f"t_dep_{i}",
                            help="Laisser vide = demarre en parallele des le debut du projet"
                        )
                        # Convert labels back to indices
                        taches[i]["depends_on"] = [predecessors_available[pred_labels.index(s)] for s in selected]
                    else:
                        st.markdown("*Premiere tache : demarre au debut du projet*")
                        taches[i]["depends_on"] = []

        data["taches"] = taches

        col1, col2 = st.columns(2)
        with col1:
            if st.button("← Precedent", use_container_width=True):
                st.session_state.wizard_data = data
                st.session_state.wizard_step = 1
                st.rerun()
        with col2:
            if st.button("Suivant →", type="primary", use_container_width=True):
                taches_valides = [t for t in taches[:data["nb_taches"]] if t["titre"].strip()]
                if taches_valides:
                    st.session_state.wizard_data = data
                    st.session_state.wizard_step = 3
                    st.rerun()
                else:
                    st.error("Au moins une tache doit avoir un titre.")

    # --- Etape 3 : Planning ---
    elif step == 3:
        st.markdown("### Planning")
        st.markdown(
            "Les dates sont calculees automatiquement selon les **dependances** definies a l'etape precedente. "
            "Les taches sans dependance demarrent en parallele des le debut du projet."
        )

        data["date_debut"] = st.date_input("Date de debut du projet",
                                            value=datetime.strptime(data["date_debut"], "%Y-%m-%d").date() if data.get("date_debut") else date.today())
        data["date_debut"] = data["date_debut"].isoformat()

        # Calcul des dates par dépendances
        all_taches = data.get("taches", [])[:data.get("nb_taches", 5)]
        taches_valides = [t for t in all_taches if t["titre"].strip()]

        # Créer un index des tâches valides par leur position dans la liste originale
        idx_map = {}  # original_index -> valid_index
        for vi, t in enumerate(taches_valides):
            oi = all_taches.index(t)
            idx_map[oi] = vi

        date_projet = datetime.strptime(data["date_debut"], "%Y-%m-%d").date()

        # Calculer les dates en résolvant les dépendances (topological)
        dates_calc = {}  # valid_index -> (date_debut, date_fin)

        def calc_dates(vi):
            if vi in dates_calc:
                return dates_calc[vi]
            t = taches_valides[vi]
            deps = t.get("depends_on", [])
            # Filtrer les dépendances valides (qui existent dans idx_map)
            deps_valides = [idx_map[d] for d in deps if d in idx_map]

            if not deps_valides:
                # Pas de dépendance -> commence au début du projet
                d_debut = date_projet
            else:
                # Commence après la fin de toutes les dépendances
                fins = []
                for dep_vi in deps_valides:
                    _, fin_dep = calc_dates(dep_vi)
                    fins.append(fin_dep)
                d_debut = max(fins)

            d_fin = d_debut + timedelta(days=t["duree_jours"])
            dates_calc[vi] = (d_debut, d_fin)
            return d_debut, d_fin

        st.markdown("#### Apercu du planning")
        planning_data = []

        for vi, t in enumerate(taches_valides):
            d_debut, d_fin = calc_dates(vi)
            t["date_debut_calc"] = d_debut.isoformat()
            t["deadline_calc"] = d_fin.isoformat()

            deps = t.get("depends_on", [])
            deps_labels = [f"T{d+1}" for d in deps if d in idx_map]

            planning_data.append({
                "Tache": t["titre"],
                "Debut": t["date_debut_calc"],
                "Fin": t["deadline_calc"],
                "Duree (j)": t["duree_jours"],
                "Dependances": ", ".join(deps_labels) if deps_labels else "Debut projet",
                "Assigne": t.get("assigne", ""),
                "Priorite": t["priorite"]
            })

        df_plan = pd.DataFrame(planning_data)
        st.dataframe(df_plan, use_container_width=True, hide_index=True)

        # Gantt chart
        if planning_data:
            fig = px.timeline(
                df_plan, x_start="Debut", x_end="Fin", y="Tache",
                color="Priorite",
                color_discrete_map=COULEURS_PRIORITE,
                title="Diagramme de Gantt"
            )
            fig.update_yaxes(autorange="reversed")
            fig.update_layout(height=max(300, len(planning_data) * 50))
            st.plotly_chart(fig, use_container_width=True)

        # Deadline projet = dernière tâche
        if taches_valides:
            deadline_projet = max(t["deadline_calc"] for t in taches_valides)
            data["deadline_projet"] = deadline_projet
            duree_totale = (datetime.strptime(deadline_projet, "%Y-%m-%d").date() - date_projet).days
            st.info(f"Deadline estimee du projet : **{deadline_projet}** ({duree_totale} jours)")

        data["taches"] = data.get("taches", [])  # keep full list

        col1, col2 = st.columns(2)
        with col1:
            if st.button("← Precedent", use_container_width=True):
                st.session_state.wizard_data = data
                st.session_state.wizard_step = 2
                st.rerun()
        with col2:
            if st.button("Suivant →", type="primary", use_container_width=True):
                st.session_state.wizard_data = data
                st.session_state.wizard_step = 4
                st.rerun()

    # --- Etape 4 : Récapitulatif & Création ---
    elif step == 4:
        st.markdown("### Recapitulatif du projet")

        st.markdown(f"**Nom :** {data.get('nom', '')}")
        st.markdown(f"**Description :** {data.get('description', '')}")
        st.markdown(f"**Type :** {data.get('categorie', '')}")
        st.markdown(f"**Deadline :** {data.get('deadline_projet', 'Non definie')}")
        if data.get("_doc_name"):
            st.markdown(f"**Document source :** {data['_doc_name']} (sera attache au projet)")

        # Objectifs
        objectifs = [o for o in data.get("objectifs", [])[:data.get("nb_objectifs", 0)] if o.strip()]
        if objectifs:
            st.markdown("**Objectifs :**")
            for o in objectifs:
                st.markdown(f"- {o}")

        if data.get("livrables"):
            st.markdown("**Livrables :**")
            for l in data["livrables"].strip().split("\n"):
                if l.strip():
                    st.markdown(f"- {l.strip()}")

        if data.get("contraintes"):
            st.markdown(f"**Contraintes :** {data['contraintes']}")

        # Tâches
        taches = data.get("taches", [])[:data.get("nb_taches", 5)]
        taches_valides = [t for t in taches if t["titre"].strip()]
        st.markdown(f"**{len(taches_valides)} taches planifiees**")

        for t in taches_valides:
            st.markdown(f"- **{t['titre']}** | {t['priorite']} | {t.get('assigne', '-')} | Deadline: {t.get('deadline_calc', '-')}")

        st.markdown("---")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("← Modifier", use_container_width=True):
                st.session_state.wizard_step = 0
                st.rerun()
        with col2:
            if st.button("Creer le projet", type="primary", use_container_width=True):
                # Build description with objectives and constraints
                desc_full = data.get("description", "")
                if objectifs:
                    desc_full += "\n\n**Objectifs :**\n" + "\n".join(f"- {o}" for o in objectifs)
                if data.get("livrables"):
                    desc_full += "\n\n**Livrables :**\n" + data["livrables"]
                if data.get("contraintes"):
                    desc_full += "\n\n**Contraintes :**\n" + data["contraintes"]

                projet_id = creer_projet(
                    data["nom"],
                    desc_full,
                    data.get("deadline_projet"),
                    st.session_state.utilisateur
                )

                # Create tasks
                for t in taches_valides:
                    tache_id = creer_tache(
                        projet_id, t["titre"], "",
                        t["priorite"], t.get("assigne", ""),
                        t.get("deadline_calc"), st.session_state.utilisateur
                    )
                    # Notify if assigned
                    if t.get("assigne"):
                        users = get_utilisateurs()
                        user_email = next((u["email"] for u in users if u["nom"] == t["assigne"]), None)
                        if user_email:
                            notifier_assignation(user_email, t["titre"], data["nom"], st.session_state.utilisateur)

                # Attacher le document source s'il existe
                if data.get("_doc_path") and os.path.exists(data["_doc_path"]):
                    doc_final = os.path.join(UPLOAD_DIR, f"proj_{projet_id}_{data['_doc_name']}")
                    shutil.copy2(data["_doc_path"], doc_final)
                    ajouter_piece_jointe(data["_doc_name"], doc_final, st.session_state.utilisateur, projet_id=projet_id)

                st.success(f"Projet '{data['nom']}' cree avec {len(taches_valides)} taches !")
                st.session_state.page = "projets"
                st.session_state.wizard_step = 0
                st.session_state.wizard_data = {}
                st.rerun()


# =====================================================================
# DASHBOARD
# =====================================================================

def page_dashboard():
    st.markdown("## Dashboard")

    stats = get_stats()

    # KPI row
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Projets actifs", stats["projets_actifs"])
    c2.metric("Total taches", stats["total_taches"])
    c3.metric("Terminees", stats["taches_terminees"])
    c4.metric("En cours", stats["taches_en_cours"])
    c5.metric("En retard", stats["taches_en_retard"], delta=f"-{stats['taches_en_retard']}" if stats["taches_en_retard"] > 0 else None,
              delta_color="inverse")

    st.markdown("---")

    col1, col2 = st.columns(2)

    # Avancement par projet
    with col1:
        st.markdown("#### Avancement des projets")
        avancements = stats["projets_avancement"]
        if avancements:
            for a in avancements:
                total = a["total_taches"] or 1
                pct = int((a["taches_terminees"] or 0) / total * 100)
                st.markdown(f"**{a['nom']}**" + (f" — Deadline: {a['deadline']}" if a["deadline"] else ""))
                st.progress(pct / 100, text=f"{pct}% ({a['taches_terminees']}/{a['total_taches']} taches)")
        else:
            st.info("Aucun projet actif.")

    # Répartition par priorité
    with col2:
        st.markdown("#### Taches par priorite (en cours)")
        if stats["par_priorite"]:
            df_prio = pd.DataFrame(stats["par_priorite"])
            fig = px.pie(df_prio, names="priorite", values="nb",
                         color="priorite", color_discrete_map=COULEURS_PRIORITE,
                         hole=0.4)
            fig.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=300)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Aucune tache en cours.")

    # Charge par utilisateur
    st.markdown("#### Charge par utilisateur")
    if stats["par_utilisateur"]:
        df_user = pd.DataFrame(stats["par_utilisateur"])
        fig = px.bar(df_user, x="assigne_a", y="nb", color="statut",
                     color_discrete_map=COULEURS_STATUT,
                     barmode="stack", labels={"assigne_a": "Utilisateur", "nb": "Nombre"})
        fig.update_layout(margin=dict(t=20, b=20), height=350)
        st.plotly_chart(fig, use_container_width=True)

    # Tâches en retard
    taches_retard = [t for t in get_taches() if t["deadline"] and t["deadline"] < date.today().isoformat() and t["statut"] != "Terminé"]
    if taches_retard:
        st.markdown("#### Taches en retard")
        for t in taches_retard:
            jours = (date.today() - datetime.strptime(t["deadline"], "%Y-%m-%d").date()).days
            st.markdown(
                f"- **{t['titre']}** ({t['projet_nom']}) — "
                f":red[{jours}j de retard] — Assigne: {t.get('assigne_a', '-')}"
            )


# =====================================================================
# COMPOSANT : AFFICHAGE PIECE JOINTE AVEC PREVIEW
# =====================================================================

EXTENSIONS_IMAGE = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}
EXTENSIONS_TEXTE = {".txt", ".csv", ".log", ".md", ".json", ".xml", ".yaml", ".yml", ".py", ".js", ".html", ".css", ".sql"}

def afficher_piece_jointe(pj, prefix="pj"):
    """Affiche une pièce jointe avec prévisualisation inline."""
    nom = pj["nom_fichier"]
    chemin = pj["chemin"]
    ext = os.path.splitext(nom)[1].lower()
    existe = os.path.exists(chemin)

    with st.expander(f"📎 **{nom}** — {pj.get('uploade_par', '')} — {pj.get('created_at', '')}", expanded=False):
        col_actions = st.columns([1, 1, 4])
        with col_actions[0]:
            if existe:
                with open(chemin, "rb") as f:
                    st.download_button("Telecharger", f.read(), file_name=nom, key=f"dl_{prefix}")
        with col_actions[1]:
            if st.button("Supprimer", key=f"del_{prefix}"):
                supprimer_piece_jointe(pj["id"])
                st.rerun()

        if not existe:
            st.warning("Fichier introuvable sur le disque.")
            return

        # --- Prévisualisation ---
        st.markdown("---")

        if ext in EXTENSIONS_IMAGE:
            st.image(chemin, use_container_width=True)

        elif ext == ".pdf":
            try:
                from streamlit_pdf_viewer import pdf_viewer
                with open(chemin, "rb") as f:
                    pdf_bytes = f.read()
                pdf_viewer(pdf_bytes, height=700)
            except Exception as e:
                st.warning(f"Apercu PDF indisponible ({e}). Utilisez le bouton Telecharger.")

        elif ext in {".xlsx", ".xls"}:
            try:
                df = pd.read_excel(chemin)
                st.markdown(f"**{len(df)} lignes x {len(df.columns)} colonnes**")
                st.dataframe(df.head(200), use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Impossible de lire le fichier Excel : {e}")

        elif ext in EXTENSIONS_TEXTE:
            try:
                with open(chemin, "r", encoding="utf-8", errors="replace") as f:
                    contenu = f.read(50000)  # max 50ko
                if ext in {".py", ".js", ".html", ".css", ".sql", ".json", ".xml", ".yaml", ".yml"}:
                    lang = ext.lstrip(".")
                    if lang == "yml":
                        lang = "yaml"
                    st.code(contenu, language=lang)
                elif ext == ".csv":
                    try:
                        df = pd.read_csv(chemin)
                        st.dataframe(df.head(200), use_container_width=True, hide_index=True)
                    except Exception:
                        st.text(contenu)
                elif ext == ".md":
                    st.markdown(contenu)
                else:
                    st.text(contenu)
            except Exception as e:
                st.error(f"Impossible de lire le fichier : {e}")

        elif ext in {".docx"}:
            try:
                from docx import Document as DocxDocument
                doc = DocxDocument(chemin)
                for para in doc.paragraphs[:100]:
                    st.markdown(para.text)
            except ImportError:
                st.info("Installez python-docx pour previsualiser les fichiers Word : `pip install python-docx`")
            except Exception as e:
                st.error(f"Impossible de lire le fichier Word : {e}")

        else:
            st.info(f"Apercu non disponible pour les fichiers {ext}. Utilisez le bouton Telecharger.")


# =====================================================================
# PROJETS
# =====================================================================

def page_projets():
    st.markdown("## Mes projets")

    # Filtres
    col_f1, col_f2 = st.columns([1, 3])
    with col_f1:
        filtre_statut = st.selectbox("Filtrer par statut", ["Tous"] + STATUTS_PROJET)

    projets = get_projets(statut=filtre_statut if filtre_statut != "Tous" else None)

    if not projets:
        st.info("Aucun projet. Utilisez l'assistant pour en creer un !")
        return

    for p in projets:
        taches = get_taches(projet_id=p["id"])
        total = len(taches)
        terminees = len([t for t in taches if t["statut"] == "Terminé"])
        pct = int(terminees / total * 100) if total > 0 else 0
        en_retard = len([t for t in taches if t["deadline"] and t["deadline"] < date.today().isoformat() and t["statut"] != "Terminé"])

        with st.expander(f"{'🟢' if p['statut']=='Actif' else '🟡' if p['statut']=='En pause' else '⚪'} **{p['nom']}** — {p['statut']} — {pct}% ({terminees}/{total})" + (f" — :red[{en_retard} en retard]" if en_retard else ""), expanded=False):
            tab_info, tab_taches, tab_docs = st.tabs(["Informations", "Taches", "Documents"])

            with tab_info:
                st.markdown(p.get("description", ""))
                st.markdown(f"**Deadline :** {p.get('deadline', 'Non definie')}")
                st.markdown(f"**Cree par :** {p.get('cree_par', '-')} le {p.get('created_at', '')}")
                st.progress(pct / 100, text=f"Avancement: {pct}%")

                # Actions
                col_act1, col_act2, col_act3 = st.columns(3)
                with col_act1:
                    with st.popover("Modifier le projet"):
                        new_nom = st.text_input("Nom", value=p["nom"], key=f"edit_nom_{p['id']}")
                        new_desc = st.text_area("Description", value=p.get("description", ""), key=f"edit_desc_{p['id']}")
                        new_statut = st.selectbox("Statut", STATUTS_PROJET, index=STATUTS_PROJET.index(p["statut"]), key=f"edit_statut_{p['id']}")
                        new_deadline = st.date_input("Deadline",
                                                      value=datetime.strptime(p["deadline"], "%Y-%m-%d").date() if p.get("deadline") else date.today(),
                                                      key=f"edit_dl_{p['id']}")
                        if st.button("Sauvegarder", key=f"save_proj_{p['id']}", type="primary"):
                            modifier_projet(p["id"], new_nom, new_desc, new_statut, new_deadline.isoformat())
                            st.success("Projet mis a jour !")
                            st.rerun()
                with col_act2:
                    with st.popover("Dupliquer ce projet"):
                        st.markdown("Creer une copie de ce projet avec ses taches.")
                        dup_nom = st.text_input("Nom du nouveau projet", value=f"{p['nom']} (copie)", key=f"dup_nom_{p['id']}")
                        dup_taches = st.checkbox("Copier les taches", value=True, key=f"dup_taches_{p['id']}")
                        dup_docs = st.checkbox("Copier les documents", value=False, key=f"dup_docs_{p['id']}")
                        if st.button("Dupliquer", key=f"dup_btn_{p['id']}", type="primary"):
                            new_id = dupliquer_projet(
                                p["id"], dup_nom, st.session_state.utilisateur,
                                copier_taches=dup_taches, copier_docs=dup_docs
                            )
                            if new_id:
                                st.success(f"Projet duplique ! (ID: {new_id})")
                                st.rerun()
                            else:
                                st.error("Erreur lors de la duplication.")
                with col_act3:
                    with st.popover("Supprimer ce projet"):
                        st.markdown(f"**Supprimer le projet '{p['nom']}' ?**")
                        st.markdown(f"Cela supprimera aussi **{total} tache(s)**, commentaires et documents associes.")
                        st.markdown(":red[Cette action est irreversible.]")
                        confirm = st.text_input("Tapez le nom du projet pour confirmer", key=f"del_confirm_{p['id']}")
                        if st.button("Supprimer definitivement", key=f"del_proj_{p['id']}", type="primary"):
                            if confirm.strip() == p["nom"]:
                                supprimer_projet(p["id"])
                                st.success("Projet supprime.")
                                st.rerun()
                            else:
                                st.error("Le nom ne correspond pas.")

            with tab_taches:
                # Ajouter une tâche rapide
                with st.popover("+ Ajouter une tache"):
                    t_titre = st.text_input("Titre", key=f"nt_titre_{p['id']}")
                    t_desc = st.text_area("Description", key=f"nt_desc_{p['id']}")
                    t_prio = st.selectbox("Priorite", PRIORITES, index=1, key=f"nt_prio_{p['id']}")
                    t_assigne = st.selectbox("Assigner a", [""] + get_noms_utilisateurs(), key=f"nt_assign_{p['id']}")
                    t_deadline = st.date_input("Deadline", value=datetime.strptime(p["deadline"], "%Y-%m-%d").date() if p.get("deadline") else date.today() + timedelta(days=7), key=f"nt_dl_{p['id']}")
                    if st.button("Creer", key=f"nt_create_{p['id']}", type="primary"):
                        if t_titre.strip():
                            tid = creer_tache(p["id"], t_titre, t_desc, t_prio, t_assigne, t_deadline.isoformat(), st.session_state.utilisateur)
                            if t_assigne:
                                users = get_utilisateurs()
                                email = next((u["email"] for u in users if u["nom"] == t_assigne), None)
                                if email:
                                    notifier_assignation(email, t_titre, p["nom"], st.session_state.utilisateur)
                            st.success("Tache creee !")
                            st.rerun()

                for t in taches:
                    prio_color = COULEURS_PRIORITE.get(t["priorite"], "#999")
                    statut_color = COULEURS_STATUT.get(t["statut"], "#999")
                    overdue = t["deadline"] and t["deadline"] < date.today().isoformat() and t["statut"] != "Terminé"

                    cols = st.columns([4, 1, 1, 1, 1])
                    with cols[0]:
                        st.markdown(f"**{t['titre']}**" + (f" — :red[EN RETARD]" if overdue else ""))
                    with cols[1]:
                        st.markdown(f"<span class='badge' style='background:{prio_color}'>{t['priorite']}</span>", unsafe_allow_html=True)
                    with cols[2]:
                        st.markdown(f"<span class='badge' style='background:{statut_color}'>{t['statut']}</span>", unsafe_allow_html=True)
                    with cols[3]:
                        st.markdown(f"{t.get('assigne_a', '-')}")
                    with cols[4]:
                        if st.button("Ouvrir", key=f"open_t_{t['id']}"):
                            st.session_state.tache_selectionnee = t["id"]
                            st.session_state.page = "tache_detail"
                            st.rerun()

            with tab_docs:
                # Upload
                uploaded = st.file_uploader("Joindre un document", key=f"upload_proj_{p['id']}")
                if uploaded:
                    filepath = os.path.join(UPLOAD_DIR, f"proj_{p['id']}_{uploaded.name}")
                    with open(filepath, "wb") as f:
                        f.write(uploaded.getbuffer())
                    ajouter_piece_jointe(uploaded.name, filepath, st.session_state.utilisateur, projet_id=p["id"])
                    st.success(f"Fichier '{uploaded.name}' uploade !")
                    st.rerun()

                pjs = get_pieces_jointes(projet_id=p["id"])
                for pj in pjs:
                    afficher_piece_jointe(pj, prefix=f"pj_{pj['id']}")


# =====================================================================
# KANBAN
# =====================================================================

def page_kanban():
    st.markdown("## Vue Kanban")

    # Filtres
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        projets = get_projets()
        noms_projets = {p["id"]: p["nom"] for p in projets}
        filtre_projet = st.selectbox("Projet", ["Tous"] + list(noms_projets.values()))
    with col_f2:
        filtre_assigne = st.selectbox("Assigne a", ["Tous"] + get_noms_utilisateurs())

    projet_id = None
    if filtre_projet != "Tous":
        projet_id = next((pid for pid, pnom in noms_projets.items() if pnom == filtre_projet), None)

    assigne = filtre_assigne if filtre_assigne != "Tous" else None

    # Kanban columns
    cols = st.columns(len(STATUTS_TACHE))

    for col_idx, statut in enumerate(STATUTS_TACHE):
        with cols[col_idx]:
            color = COULEURS_STATUT[statut]
            st.markdown(f"<div class='kanban-header' style='background:{color}20;color:{color};'>{statut}</div>", unsafe_allow_html=True)

            taches = get_taches(projet_id=projet_id, statut=statut, assigne_a=assigne)

            for t in taches:
                prio_color = COULEURS_PRIORITE.get(t["priorite"], "#999")
                prio_class = t["priorite"].lower()
                overdue = t["deadline"] and t["deadline"] < date.today().isoformat() and t["statut"] != "Terminé"

                st.markdown(f"""
                <div class='kanban-card {prio_class}'>
                    <div style='font-weight:600;margin-bottom:4px;'>{t['titre']}</div>
                    <div style='font-size:0.85em;color:#666;'>{t.get('projet_nom', '')}</div>
                    <div style='font-size:0.85em;margin-top:4px;'>
                        <span class='badge' style='background:{prio_color}'>{t['priorite']}</span>
                        {f"<span style='color:#666;margin-left:8px;'>{t.get('assigne_a', '')}</span>" if t.get('assigne_a') else ""}
                    </div>
                    {f"<div style='font-size:0.8em;margin-top:4px;'>" + (f"<span class='overdue'>Retard: {t['deadline']}</span>" if overdue else f"Deadline: {t['deadline']}") + "</div>" if t.get('deadline') else ""}
                </div>
                """, unsafe_allow_html=True)

                # Move buttons
                btn_cols = st.columns(3)
                current_idx = STATUTS_TACHE.index(statut)
                with btn_cols[0]:
                    if current_idx > 0:
                        if st.button("←", key=f"mv_l_{t['id']}", help=f"Vers {STATUTS_TACHE[current_idx-1]}"):
                            ancien = t["statut"]
                            nouveau = STATUTS_TACHE[current_idx - 1]
                            deplacer_tache(t["id"], nouveau)
                            # Notification
                            if t.get("assigne_a"):
                                users = get_utilisateurs()
                                email = next((u["email"] for u in users if u["nom"] == t["assigne_a"]), None)
                                if email:
                                    notifier_statut_change(email, t["titre"], ancien, nouveau, st.session_state.utilisateur)
                            st.rerun()
                with btn_cols[1]:
                    if st.button("Ouvrir", key=f"kb_open_{t['id']}"):
                        st.session_state.tache_selectionnee = t["id"]
                        st.session_state.page = "tache_detail"
                        st.rerun()
                with btn_cols[2]:
                    if current_idx < len(STATUTS_TACHE) - 1:
                        if st.button("→", key=f"mv_r_{t['id']}", help=f"Vers {STATUTS_TACHE[current_idx+1]}"):
                            ancien = t["statut"]
                            nouveau = STATUTS_TACHE[current_idx + 1]
                            deplacer_tache(t["id"], nouveau)
                            if t.get("assigne_a"):
                                users = get_utilisateurs()
                                email = next((u["email"] for u in users if u["nom"] == t["assigne_a"]), None)
                                if email:
                                    notifier_statut_change(email, t["titre"], ancien, nouveau, st.session_state.utilisateur)
                            st.rerun()

            st.markdown(f"<div style='text-align:center;color:#bbb;font-size:0.85em;'>{len(taches)} tache(s)</div>", unsafe_allow_html=True)


# =====================================================================
# MES TACHES
# =====================================================================

def page_mes_taches():
    st.markdown(f"## Mes taches — {st.session_state.utilisateur}")

    taches = get_taches(assigne_a=st.session_state.utilisateur)

    if not taches:
        st.info("Aucune tache assignee.")
        return

    for statut in STATUTS_TACHE:
        taches_statut = [t for t in taches if t["statut"] == statut]
        if taches_statut:
            color = COULEURS_STATUT[statut]
            st.markdown(f"### <span style='color:{color}'>{statut}</span> ({len(taches_statut)})", unsafe_allow_html=True)
            for t in taches_statut:
                overdue = t["deadline"] and t["deadline"] < date.today().isoformat() and t["statut"] != "Terminé"
                prio_color = COULEURS_PRIORITE.get(t["priorite"], "#999")

                cols = st.columns([4, 1, 1, 1])
                with cols[0]:
                    st.markdown(f"**{t['titre']}** — {t.get('projet_nom', '')}" + (f" :red[EN RETARD]" if overdue else ""))
                with cols[1]:
                    st.markdown(f"<span class='badge' style='background:{prio_color}'>{t['priorite']}</span>", unsafe_allow_html=True)
                with cols[2]:
                    st.markdown(f"{t.get('deadline', '-')}")
                with cols[3]:
                    if st.button("Ouvrir", key=f"mt_open_{t['id']}"):
                        st.session_state.tache_selectionnee = t["id"]
                        st.session_state.page = "tache_detail"
                        st.rerun()


# =====================================================================
# DETAIL TACHE
# =====================================================================

def page_tache_detail():
    tache_id = st.session_state.tache_selectionnee
    if not tache_id:
        st.session_state.page = "kanban"
        st.rerun()
        return

    t = get_tache(tache_id)
    if not t:
        st.error("Tache introuvable.")
        return

    overdue = t["deadline"] and t["deadline"] < date.today().isoformat() and t["statut"] != "Terminé"

    if st.button("← Retour"):
        st.session_state.page = "kanban"
        st.rerun()

    st.markdown(f"## {t['titre']}" + (f" :red[EN RETARD]" if overdue else ""))
    st.markdown(f"**Projet :** {t.get('projet_nom', '')}")

    tab1, tab2, tab3 = st.tabs(["Details", "Commentaires", "Documents"])

    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            new_statut = st.selectbox("Statut", STATUTS_TACHE, index=STATUTS_TACHE.index(t["statut"]), key="td_statut")
            new_prio = st.selectbox("Priorite", PRIORITES, index=PRIORITES.index(t["priorite"]), key="td_prio")
            new_assigne = st.selectbox("Assigne a", [""] + get_noms_utilisateurs(),
                                        index=([""] + get_noms_utilisateurs()).index(t["assigne_a"]) if t.get("assigne_a") in get_noms_utilisateurs() else 0,
                                        key="td_assigne")
        with col2:
            new_deadline = st.date_input("Deadline",
                                          value=datetime.strptime(t["deadline"], "%Y-%m-%d").date() if t.get("deadline") else date.today(),
                                          key="td_deadline")
            new_desc = st.text_area("Description", value=t.get("description", ""), height=150, key="td_desc")

        if st.button("Sauvegarder les modifications", type="primary"):
            ancien_statut = t["statut"]
            ancien_assigne = t.get("assigne_a", "")

            modifier_tache(tache_id, statut=new_statut, priorite=new_prio, assigne_a=new_assigne,
                          deadline=new_deadline.isoformat(), description=new_desc)

            # Notifications
            users = get_utilisateurs()
            if new_statut != ancien_statut and new_assigne:
                email = next((u["email"] for u in users if u["nom"] == new_assigne), None)
                if email:
                    notifier_statut_change(email, t["titre"], ancien_statut, new_statut, st.session_state.utilisateur)

            if new_assigne and new_assigne != ancien_assigne:
                email = next((u["email"] for u in users if u["nom"] == new_assigne), None)
                if email:
                    notifier_assignation(email, t["titre"], t.get("projet_nom", ""), st.session_state.utilisateur)

            st.success("Tache mise a jour !")
            st.rerun()

        st.markdown("---")
        if st.button("Supprimer cette tache", type="secondary"):
            supprimer_tache(tache_id)
            st.session_state.page = "kanban"
            st.rerun()

    with tab2:
        # Ajouter commentaire
        commentaire = st.text_area("Ajouter un commentaire", key="new_comment", placeholder="Votre commentaire...")
        if st.button("Publier", type="primary", key="post_comment"):
            if commentaire.strip():
                ajouter_commentaire(tache_id, st.session_state.utilisateur, commentaire)
                # Notify assignee
                if t.get("assigne_a") and t["assigne_a"] != st.session_state.utilisateur:
                    users = get_utilisateurs()
                    email = next((u["email"] for u in users if u["nom"] == t["assigne_a"]), None)
                    if email:
                        notifier_commentaire(email, t["titre"], st.session_state.utilisateur, commentaire)
                st.success("Commentaire ajoute !")
                st.rerun()

        # Liste commentaires
        commentaires = get_commentaires(tache_id)
        for c in commentaires:
            st.markdown(f"""
            <div style='background:#f8f9fa;padding:12px;border-radius:8px;margin:8px 0;border-left:3px solid #1a73e8;'>
                <div style='font-weight:600;color:#1a73e8;'>{c['auteur']} <span style='font-weight:normal;color:#999;font-size:0.85em;'>{c['created_at']}</span></div>
                <div style='margin-top:6px;'>{c['contenu']}</div>
            </div>
            """, unsafe_allow_html=True)

    with tab3:
        uploaded = st.file_uploader("Joindre un document", key=f"upload_tache_{tache_id}")
        if uploaded:
            filepath = os.path.join(UPLOAD_DIR, f"tache_{tache_id}_{uploaded.name}")
            with open(filepath, "wb") as f:
                f.write(uploaded.getbuffer())
            ajouter_piece_jointe(uploaded.name, filepath, st.session_state.utilisateur, tache_id=tache_id)
            st.success(f"Fichier '{uploaded.name}' uploade !")
            st.rerun()

        pjs = get_pieces_jointes(tache_id=tache_id)
        for pj in pjs:
            afficher_piece_jointe(pj, prefix=f"tpj_{pj['id']}")


# =====================================================================
# ROUTING
# =====================================================================

# Sauvegarder l'état courant (session + URL) avant le rendu
sync_session()

page = st.session_state.page

if page == "dashboard":
    page_dashboard()
elif page == "wizard":
    page_wizard()
elif page == "projets":
    page_projets()
elif page == "kanban":
    page_kanban()
elif page == "mes_taches":
    page_mes_taches()
elif page == "tache_detail":
    page_tache_detail()
