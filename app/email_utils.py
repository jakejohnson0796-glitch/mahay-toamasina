"""
Envoi d'email via SMTP, pour la fonctionnalite "mot de passe oublie"
(voir /mot-de-passe-oublie dans auth_router.py). Utilise `smtplib` de la
bibliotheque standard Python -- aucune dependance externe a ajouter,
contrairement a un envoi de SMS (Twilio etc.) qui est en plus payant.
Fonctionne avec n'importe quel fournisseur SMTP : un compte Gmail avec
un "mot de passe d'application" (myaccount.google.com/apppasswords),
l'offre SMTP gratuite de Brevo/Sendinblue, ou tout autre fournisseur.

Module volontairement minimal : un seul usage (code de reinitialisation
a 6 chiffres), pas de generalisation prematuree vers d'autres types
d'email (notifications, etc.) tant que le besoin ne se presente pas.
"""
import smtplib
from email.mime.text import MIMEText

from .config import parametres


class EmailNonConfigure(RuntimeError):
    """Levee si SMTP_HOTE / SMTP_UTILISATEUR / SMTP_MOT_DE_PASSE /
    SMTP_FROM_EMAIL ne sont pas toutes definies. Permet d'afficher un
    message clair a l'utilisateur plutot qu'une 500 brute si "mot de
    passe oublie" est utilise avant que le SMTP soit configure."""


def email_configure() -> bool:
    return bool(
        parametres.smtp_hote and parametres.smtp_utilisateur
        and parametres.smtp_mot_de_passe and parametres.smtp_from_email
    )


def envoyer_email(destinataire: str, sujet: str, corps: str) -> None:
    """Envoie un email texte brut. Leve EmailNonConfigure si le SMTP
    n'est pas configure, ou l'exception smtplib telle quelle si l'envoi
    echoue (identifiants invalides, hote injoignable...) : c'est a
    l'appelant de decider comment presenter l'erreur (voir
    /mot-de-passe-oublie dans auth_router.py)."""
    if not email_configure():
        raise EmailNonConfigure(
            "L'envoi d'email n'est pas configure sur ce serveur (SMTP_HOTE / SMTP_UTILISATEUR / "
            "SMTP_MOT_DE_PASSE / SMTP_FROM_EMAIL manquantes)."
        )

    message = MIMEText(corps, "plain", "utf-8")
    message["Subject"] = sujet
    message["From"] = parametres.smtp_from_email
    message["To"] = destinataire

    # STARTTLS sur le port 587 : convention la plus repandue chez les
    # fournisseurs SMTP grand public (Gmail, Brevo...). Si un jour un
    # fournisseur exige le SSL implicite (port 465, smtplib.SMTP_SSL),
    # ce sera a adapter ici -- pas anticipe tant que ce n'est pas
    # reellement necessaire.
    with smtplib.SMTP(parametres.smtp_hote, parametres.smtp_port, timeout=10) as serveur:
        serveur.starttls()
        serveur.login(parametres.smtp_utilisateur, parametres.smtp_mot_de_passe)
        serveur.sendmail(parametres.smtp_from_email, [destinataire], message.as_string())
