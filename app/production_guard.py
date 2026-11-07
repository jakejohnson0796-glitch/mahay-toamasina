"""Validation des prerequis obligatoires avant un demarrage en production."""
from __future__ import annotations

from urllib.parse import urlsplit

from sqlalchemy.engine import make_url

from .config import Parametres


def _est_postgresql(url: str) -> bool:
    try:
        scheme = urlsplit(url).scheme.lower()
    except ValueError:
        return False
    return scheme in {"postgresql", "postgres"}


def _role_postgres(url: str) -> str:
    """Extrait seulement le nom du rôle, jamais le mot de passe ni l'URL."""
    try:
        utilisateur = make_url(url).username or ""
    except Exception:
        return ""
    # Supavisor attend ROLE.PROJECT_REF ; une connexion directe utilise ROLE.
    return utilisateur.split(".", 1)[0].strip().lower()


def erreurs_configuration_production(config: Parametres) -> list[str]:
    """Retourne les prerequis manquants pour un deploiement public durable.

    Les integrations optionnelles (IA, LiveKit, SMTP) ne bloquent pas le boot
    tant qu'elles sont absentes. En revanche, la base Postgres, le secret de
    session et le stockage objet sont obligatoires : le disque du Web service
    n'est pas durable entre redeploiements/redemarrages.
    """
    erreurs: list[str] = []

    if config.environnement != "production":
        return erreurs

    if not config.release_commit or config.release_commit == "unknown":
        erreurs.append(
            "RENDER_GIT_COMMIT/GIT_COMMIT est obligatoire en production pour identifier la release réellement servie."
        )

    secret = config.session_secret_key.strip()
    if secret == "a-changer-en-production" or len(secret) < 32:
        erreurs.append("SESSION_SECRET_KEY doit etre un secret aleatoire d'au moins 32 caracteres.")

    if not _est_postgresql(config.database_url):
        erreurs.append("DATABASE_URL doit pointer vers PostgreSQL en production.")

    if not _est_postgresql(config.migration_database_url):
        erreurs.append("MIGRATION_DATABASE_URL doit pointer vers PostgreSQL en production.")
    else:
        role_runtime = _role_postgres(config.database_url)
        role_migration = _role_postgres(config.migration_database_url)
        if role_runtime and role_runtime in {"postgres", "supabase_admin", "service_role"}:
            erreurs.append(
                "DATABASE_URL doit utiliser le rôle personnalisé mahay_runtime, "
                "pas un rôle d'administration ou un rôle qui contourne RLS."
            )
        if not role_runtime or not role_migration or role_runtime == role_migration:
            erreurs.append(
                "DATABASE_URL et MIGRATION_DATABASE_URL doivent utiliser deux rôles PostgreSQL distincts."
            )

    if not config.supabase_url.strip() or not config.supabase_service_key.strip():
        erreurs.append(
            "SUPABASE_URL et SUPABASE_SERVICE_KEY sont obligatoires en production "
            "pour conserver les fichiers hors du disque ephemere du Web service."
        )

    livekit = [config.livekit_url.strip(), config.livekit_api_key.strip(), config.livekit_api_secret.strip()]
    if any(livekit) and not all(livekit):
        erreurs.append("LIVEKIT_URL, LIVEKIT_API_KEY et LIVEKIT_API_SECRET doivent etre fournis ensemble.")

    return erreurs


def valider_configuration_production(config: Parametres) -> None:
    """Leve RuntimeError si la configuration de production est incomplete."""
    erreurs = erreurs_configuration_production(config)
    if erreurs:
        details = "\\n- " + "\\n- ".join(erreurs)
        raise RuntimeError("Configuration production incomplete:" + details)
