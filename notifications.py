"""Module de notifications via Outlook (win32com)."""

import logging

logger = logging.getLogger(__name__)


def envoyer_notification_outlook(destinataire_email, sujet, corps_html):
    """Envoie un email via Outlook installé localement."""
    try:
        import win32com.client
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)
        mail.To = destinataire_email
        mail.Subject = sujet
        mail.HTMLBody = corps_html
        mail.Send()
        return True
    except Exception as e:
        logger.error(f"Erreur envoi Outlook: {e}")
        return False


def notifier_assignation(email, tache_titre, projet_nom, assigne_par):
    sujet = f"[Suivi Projets] Nouvelle tâche assignée : {tache_titre}"
    corps = f"""
    <html><body style="font-family:Segoe UI,sans-serif;">
    <h2 style="color:#1a73e8;">Nouvelle tâche assignée</h2>
    <table style="border-collapse:collapse;">
        <tr><td style="padding:6px 12px;font-weight:bold;">Tâche :</td><td style="padding:6px 12px;">{tache_titre}</td></tr>
        <tr><td style="padding:6px 12px;font-weight:bold;">Projet :</td><td style="padding:6px 12px;">{projet_nom}</td></tr>
        <tr><td style="padding:6px 12px;font-weight:bold;">Assignée par :</td><td style="padding:6px 12px;">{assigne_par}</td></tr>
    </table>
    <p>Connectez-vous à l'application de suivi pour plus de détails.</p>
    </body></html>
    """
    return envoyer_notification_outlook(email, sujet, corps)


def notifier_deadline(email, tache_titre, projet_nom, deadline):
    sujet = f"[Suivi Projets] Rappel deadline : {tache_titre}"
    corps = f"""
    <html><body style="font-family:Segoe UI,sans-serif;">
    <h2 style="color:#e53935;">Rappel de deadline</h2>
    <table style="border-collapse:collapse;">
        <tr><td style="padding:6px 12px;font-weight:bold;">Tâche :</td><td style="padding:6px 12px;">{tache_titre}</td></tr>
        <tr><td style="padding:6px 12px;font-weight:bold;">Projet :</td><td style="padding:6px 12px;">{projet_nom}</td></tr>
        <tr><td style="padding:6px 12px;font-weight:bold;">Deadline :</td><td style="padding:6px 12px;">{deadline}</td></tr>
    </table>
    <p style="color:#e53935;font-weight:bold;">Cette tâche arrive à échéance. Merci de mettre à jour son statut.</p>
    </body></html>
    """
    return envoyer_notification_outlook(email, sujet, corps)


def notifier_commentaire(email, tache_titre, auteur, commentaire):
    sujet = f"[Suivi Projets] Nouveau commentaire sur : {tache_titre}"
    corps = f"""
    <html><body style="font-family:Segoe UI,sans-serif;">
    <h2 style="color:#1a73e8;">Nouveau commentaire</h2>
    <p><strong>{auteur}</strong> a commenté la tâche <strong>{tache_titre}</strong> :</p>
    <blockquote style="border-left:3px solid #1a73e8;padding:8px 16px;margin:12px 0;background:#f5f5f5;">
        {commentaire}
    </blockquote>
    </body></html>
    """
    return envoyer_notification_outlook(email, sujet, corps)


def notifier_statut_change(email, tache_titre, ancien_statut, nouveau_statut, modifie_par):
    sujet = f"[Suivi Projets] Statut modifié : {tache_titre}"
    corps = f"""
    <html><body style="font-family:Segoe UI,sans-serif;">
    <h2 style="color:#1a73e8;">Changement de statut</h2>
    <table style="border-collapse:collapse;">
        <tr><td style="padding:6px 12px;font-weight:bold;">Tâche :</td><td style="padding:6px 12px;">{tache_titre}</td></tr>
        <tr><td style="padding:6px 12px;font-weight:bold;">Ancien statut :</td><td style="padding:6px 12px;">{ancien_statut}</td></tr>
        <tr><td style="padding:6px 12px;font-weight:bold;">Nouveau statut :</td><td style="padding:6px 12px;">{nouveau_statut}</td></tr>
        <tr><td style="padding:6px 12px;font-weight:bold;">Modifié par :</td><td style="padding:6px 12px;">{modifie_par}</td></tr>
    </table>
    </body></html>
    """
    return envoyer_notification_outlook(email, sujet, corps)
