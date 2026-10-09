"""Diagnostics opérationnels consultables uniquement depuis l'administration.

Les contrôles distinguent la connectivité réelle de la simple présence d'une
configuration. Aucun secret, URL complète ou message d'exception n'est rendu.
"""
from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from .config import parametres
from .database import engine


def _element(nom: str, statut: str, libelle: str, detail: str) -> dict[str, str]:
    return {"nom": nom, "statut": statut, "libelle": libelle, "detail": detail}


def diagnostic_base_de_donnees() -> dict[str, str]:
    """Teste une requête réelle, sans afficher l'URI de connexion."""
    try:
        with engine.connect() as connexion:
            resultat = connexion.execute(text("SELECT 1")).scalar_one()
        if resultat != 1:
            raise RuntimeError("unexpected result")
    except Exception:
        return _element(
            "Base de données PostgreSQL",
            "error",
            "Indisponible",
            "La requête de contrôle SELECT 1 a échoué. Vérifie la connexion et les journaux du service.",
        )
    return _element(
        "Base de données",
        "ok",
        "Accessible",
        "La connexion répond à SELECT 1. Les données de connexion restent masquées.",
    )


def comparer_revisions_migrations(
    revisions_courantes: set[str],
    revisions_attendues: set[str],
) -> dict[str, str]:
    """Compare le schéma réellement appliqué aux têtes Alembic versionnées."""
    if revisions_attendues and revisions_courantes == revisions_attendues:
        detail = "Révision(s) appliquée(s) : " + ", ".join(sorted(revisions_courantes)) + "."
        return _element("Migrations Alembic", "ok", "À jour", detail)

    courantes = ", ".join(sorted(revisions_courantes)) or "aucune"
    attendues = ", ".join(sorted(revisions_attendues)) or "impossible à déterminer"
    return _element(
        "Migrations Alembic",
        "error",
        "À vérifier",
        f"Révision appliquée : {courantes}. Révision attendue : {attendues}.",
    )


def diagnostic_migrations() -> dict[str, str]:
    """Compare alembic_version au graphe de migrations livré avec l'application."""
    try:
        racine = Path(__file__).resolve().parent.parent
        config = Config()
        config.set_main_option("script_location", str(racine / "alembic"))
        config.config_file_name = None
        revisions_attendues = set(ScriptDirectory.from_config(config).get_heads())
        with engine.connect() as connexion:
            lignes = connexion.execute(text("SELECT version_num FROM alembic_version")).all()
        revisions_courantes = {str(ligne[0]) for ligne in lignes}
        return comparer_revisions_migrations(revisions_courantes, revisions_attendues)
    except Exception:
        return _element(
            "Migrations Alembic",
            "error",
            "Non vérifiables",
            "La version du schéma n'a pas pu être lue. Vérifie le schéma et les journaux du service.",
        )


def diagnostic_stockage_supabase() -> dict[str, str]:
    """Teste l'accès au bucket sans exposer l'URL, la clé ou le corps d'erreur."""
    base = (parametres.supabase_url or "").strip().rstrip("/")
    cle = (parametres.supabase_service_key or "").strip()
    bucket = (parametres.supabase_bucket or "").strip()

    if not base or not cle or not bucket:
        return _element(
            "Supabase Storage",
            "warning",
            "Configuration incomplète",
            "L'URL, la clé de service ou le nom du bucket manque. Le stockage des documents doit être configuré.",
        )

    try:
        morceaux = urlsplit(base)
        # La clé de service est un secret : ne jamais l'envoyer par HTTP en clair.
        if morceaux.scheme.lower() != "https" or not morceaux.netloc:
            return _element(
                "Supabase Storage",
                "error",
                "URL non sécurisée",
                "Le point de stockage doit utiliser une URL HTTPS valide.",
            )
        url = f"{base}/storage/v1/bucket/{urllib.parse.quote(bucket, safe='')}"
        requete = urllib.request.Request(
            url,
            headers={
                "apikey": cle,
                "Authorization": f"Bearer {cle}",
                "Accept": "application/json",
            },
            method="GET",
        )
        with urllib.request.urlopen(requete, timeout=2.5) as reponse:
            code = int(getattr(reponse, "status", 200))
        if 200 <= code < 300:
            return _element(
                "Supabase Storage",
                "ok",
                "Accessible",
                "Le bucket répond au contrôle HTTP. Aucun contenu de document n'a été téléchargé.",
            )
        return _element(
            "Supabase Storage",
            "error",
            "Erreur HTTP",
            "Le service de stockage a répondu avec un statut inattendu.",
        )
    except urllib.error.HTTPError as erreur:
        if erreur.code in (401, 403):
            detail = "Supabase Storage a refusé l'accès de service. Vérifie les identifiants côté hébergeur."
        elif erreur.code == 404:
            detail = "Le bucket demandé est introuvable. Vérifie son nom dans la configuration."
        else:
            detail = "Supabase Storage a renvoyé une erreur HTTP. Consulte les journaux du fournisseur."
        return _element("Supabase Storage", "error", "Échec du contrôle", detail)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return _element(
            "Supabase Storage",
            "error",
            "Injoignable",
            "Le contrôle de connexion a échoué ou expiré. Aucune donnée d'identification n'est affichée.",
        )
    except Exception:
        return _element(
            "Supabase Storage",
            "error",
            "Non vérifiable",
            "Le contrôle du stockage a échoué. Vérifie la configuration et les journaux du fournisseur.",
        )


def diagnostic_worker_ia(etat_application: Any) -> dict[str, str]:
    """Vérifie la cohérence entre Redis configuré et thread worker actif."""
    if not (parametres.redis_url or "").strip():
        return _element(
            "Worker IA",
            "warning",
            "Non démarré",
            "REDIS_URL n'est pas défini : le worker intégré ne démarre pas et les tâches IA peuvent prendre du retard.",
        )
    thread = getattr(etat_application, "ai_worker_thread", None)
    try:
        actif = bool(thread and thread.is_alive())
    except Exception:
        actif = False
    if actif:
        return _element(
            "Worker IA",
            "ok",
            "Actif",
            "Le thread de traitement est vivant. Ce contrôle ne simule pas une requête auprès du fournisseur IA.",
        )
    return _element(
        "Worker IA",
        "error",
        "Arrêté",
        "Redis est configuré, mais le thread du worker n'est pas actif.",
    )


def _diagnostic_configuration(
    nom: str,
    valeurs: list[str],
    *,
    obligatoire: bool,
    description: str,
) -> dict[str, str]:
    presentes = [bool((valeur or "").strip()) for valeur in valeurs]
    if all(presentes):
        return _element(
            nom,
            "ok",
            "Configuré",
            f"{description} Configuration présente ; la disponibilité distante n'est pas testée ici.",
        )
    if any(presentes):
        return _element(
            nom,
            "warning",
            "Incomplet",
            f"{description} Certaines valeurs sont manquantes ; aucun secret n'est affiché.",
        )
    if obligatoire:
        return _element(
            nom,
            "warning",
            "À configurer",
            f"{description} Paramètre absent ; la fonctionnalité concernée peut échouer.",
        )
    return _element(
        nom,
        "info",
        "Optionnel",
        f"{description} Non configuré, ce qui est acceptable si la fonctionnalité n'est pas utilisée.",
    )


def collecter_diagnostics(etat_application: Any) -> dict[str, Any]:
    """Retourne l'aperçu pour l'administrateur sans inclure de secrets."""
    base = diagnostic_base_de_donnees()
    if base["statut"] == "ok":
        migrations = diagnostic_migrations()
    else:
        migrations = _element(
            "Migrations Alembic",
            "info",
            "Non vérifiées",
            "La base étant inaccessible, la version appliquée ne peut pas être lue.",
        )

    release = (parametres.release_commit or "").strip()
    release_item = _element(
        "Release du service",
        "ok" if release and release != "unknown" else "warning",
        "Identifiée" if release and release != "unknown" else "Inconnue",
        (
            f"Commit déclaré par l'environnement : {release[:12]}. "
            "Cette information ne remplace pas la vérification du CI ni celle du déploiement public."
            if release and release != "unknown"
            else "Aucun SHA de release n'est fourni par l'environnement."
        ),
    )
    controles = [
        base,
        migrations,
        diagnostic_stockage_supabase(),
        diagnostic_worker_ia(etat_application),
        _diagnostic_configuration(
            "Fournisseur IA Groq",
            [parametres.groq_api_key],
            obligatoire=True,
            description="Clé d'accès aux fonctions IA.",
        ),
        _diagnostic_configuration(
            "Gemini",
            [parametres.gemini_api_key],
            obligatoire=False,
            description="Fournisseur IA secondaire.",
        ),
        _diagnostic_configuration(
            "SMTP",
            [parametres.smtp_hote, parametres.smtp_utilisateur, parametres.smtp_mot_de_passe],
            obligatoire=False,
            description="Envoi des e-mails, notamment la récupération de compte.",
        ),
        _diagnostic_configuration(
            "LiveKit",
            [parametres.livekit_url, parametres.livekit_api_key, parametres.livekit_api_secret],
            obligatoire=False,
            description="Audio, vidéo et partage d'écran pour les classes virtuelles.",
        ),
        release_item,
    ]
    erreurs = sum(1 for item in controles if item["statut"] == "error")
    avertissements = sum(1 for item in controles if item["statut"] == "warning")
    if erreurs:
        etat_global, libelle_global = "error", "Problème à traiter"
    elif avertissements:
        etat_global, libelle_global = "warning", "Attention requise"
    else:
        etat_global, libelle_global = "ok", "Contrôles satisfaisants"

    return {
        "diagnostics": controles,
        "etat_global": etat_global,
        "libelle_global": libelle_global,
        "nb_erreurs": erreurs,
        "nb_avertissements": avertissements,
        "environnement": parametres.environnement,
    }
