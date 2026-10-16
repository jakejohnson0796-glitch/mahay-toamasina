"""Envoi d'emails transactionnels pour la récupération et la MFA.

Sur Render Free, l'API HTTPS Brevo est préférable car les connexions SMTP sortantes
sur les ports 25, 465 et 587 sont bloquées. L'API utilise HTTPS (443). SMTP reste
disponible en local ou chez un hébergeur qui autorise cette connexion.

Aucun SMS n'est envoyé par ce module. Les codes sont générés, hachés, expirés et
consommés dans le routeur métier ; ce module assure uniquement leur transport.
"""
import json
import smtplib
import urllib.error
import urllib.request
from email.mime.text import MIMEText

from .config import parametres


class EmailNonConfigure(RuntimeError):
    """Aucun transport e-mail compatible n'est configuré."""


def _brevo_api_configure() -> bool:
    return bool(parametres.brevo_api_key and parametres.smtp_from_email)


def email_configure() -> bool:
    """Retourne True si le transport e-mail sélectionné est configuré."""
    smtp_configure = bool(
        parametres.smtp_hote and parametres.smtp_utilisateur
        and parametres.smtp_mot_de_passe and parametres.smtp_from_email
    )
    if parametres.email_transport == "brevo_api":
        # Render Free bloque SMTP : ne jamais signaler que l'envoi est prêt
        # si la configuration API HTTPS obligatoire manque.
        return _brevo_api_configure()
    return _brevo_api_configure() or smtp_configure


def _envoyer_via_brevo(destinataire: str, sujet: str, corps: str) -> None:
    """Envoie un email texte via l'API transactionnelle Brevo en HTTPS."""
    payload = {
        "sender": {
            "name": parametres.brevo_sender_name or "Gasy Mahay",
            "email": parametres.smtp_from_email,
        },
        "to": [{"email": destinataire}],
        "subject": sujet,
        "textContent": corps,
    }
    requete = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "accept": "application/json",
            "api-key": parametres.brevo_api_key,
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(requete, timeout=10) as reponse:
            if not 200 <= reponse.status < 300:
                raise RuntimeError(f"Brevo a retourné le statut HTTP {reponse.status}.")
            reponse.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Échec de l'API e-mail HTTPS (HTTP {exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Le service e-mail HTTPS est momentanément inaccessible.") from exc


def envoyer_email(destinataire: str, sujet: str, corps: str) -> None:
    """Envoie via Brevo API HTTPS, ou via SMTP en solution secondaire."""
    if not email_configure():
        raise EmailNonConfigure(
            "Configurez BREVO_API_KEY et SMTP_FROM_EMAIL (recommandé sur Render Free), "
            "ou un ensemble SMTP complet sur un serveur autorisant la sortie SMTP."
        )

    # Le mode forcé "brevo_api" est utilisé par Render Free : ne jamais
    # retomber sur SMTP car les ports sortants SMTP y sont bloqués.
    if parametres.email_transport == "brevo_api" or (
        parametres.brevo_api_key and parametres.smtp_from_email
    ):
        if not _brevo_api_configure():
            raise EmailNonConfigure(
                "Le transport BREVO_API_KEY via HTTPS est requis par cette configuration."
            )
        _envoyer_via_brevo(destinataire, sujet, corps)
        return

    message = MIMEText(corps, "plain", "utf-8")
    message["Subject"] = sujet
    message["From"] = parametres.smtp_from_email
    message["To"] = destinataire
    with smtplib.SMTP(parametres.smtp_hote, parametres.smtp_port, timeout=10) as serveur:
        serveur.starttls()
        serveur.login(parametres.smtp_utilisateur, parametres.smtp_mot_de_passe)
        serveur.sendmail(parametres.smtp_from_email, [destinataire], message.as_string())
