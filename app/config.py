"""
Configuration centralisee de MAHAY Toamasina.

Tout ce qui differe entre "je developpe en local" et "c'est deploye en
vrai" passe par des variables d'environnement, lues ici une seule fois
plutot que d'avoir des os.getenv() eparpilles dans tout le code. En local,
un fichier .env (a la racine, a cote de requirements.txt) suffit — voir
.env.example pour la liste complete. En production, ces variables doivent
etre definies directement dans l'environnement d'hebergement (jamais
committees dans le code).
"""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# No-op silencieux si .env n'existe pas (ex: en production, ou les vraies
# variables d'environnement sont deja injectees par l'hebergeur).
load_dotenv()


@dataclass
class Parametres:
    # --- Base de donnees ---
    # Vide => SQLite local (mahay.db), comme dans la V1 initiale.
    # Rempli avec l'URI Postgres de Supabase (Project Settings > Database
    # > Connection string > URI) => bascule automatiquement sur Supabase
    # Postgres, sans toucher au code. L'URI Supabase suit le schema
    # standard "postgresql" avec utilisateur, mot de passe, hote, port
    # 5432 et nom de base "postgres" — jamais de valeur reelle ici, elle
    # vit uniquement dans DATABASE_URL (.env local ou variable d'env de
    # l'hebergeur), jamais commitee.
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL") or "sqlite:///./mahay.db")

    # --- Session (cookies de connexion) ---
    session_secret_key: str = field(default_factory=lambda: os.getenv("SESSION_SECRET_KEY", "a-changer-en-production"))

    # --- Stockage des fichiers deposes (Supabase Storage) ---
    # Si les deux sont vides => fallback sur le disque local (dossier uploads/).
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    supabase_service_key: str = field(default_factory=lambda: os.getenv("SUPABASE_SERVICE_KEY", ""))
    supabase_bucket: str = field(default_factory=lambda: os.getenv("SUPABASE_BUCKET", "documents"))

    # --- Environnement (dev/production) ---
    # Determine notamment si les cookies de session doivent exiger HTTPS
    # (https_only) — voir SessionMiddleware dans main.py. Mets
    # ENVIRONNEMENT=production dans les variables d'env de l'hebergeur
    # (deja fait dans render.yaml).
    environnement: str = field(default_factory=lambda: os.getenv("ENVIRONNEMENT", "developpement"))

    # --- Compte admin auto-initialise (voir app/admin_init.py) ---
    # ADMIN_PHONE absent => aucune initialisation automatique (comportement
    # inchange pour qui n'utilise pas cette fonctionnalite). ADMIN_PHONE
    # present => ce compte est garanti admin a chaque demarrage. Le mot de
    # passe (ADMIN_INITIAL_PASSWORD) n'est utilise QUE si ce compte n'existe
    # pas encore ; il n'est jamais lu ni modifie pour un compte existant.
    admin_phone: str = field(default_factory=lambda: os.getenv("ADMIN_PHONE", ""))
    admin_mot_de_passe_initial: str = field(default_factory=lambda: os.getenv("ADMIN_INITIAL_PASSWORD", ""))

    # --- Generation de quiz par IA (API Groq — gratuite) ---
    # Cle gratuite sur https://console.groq.com (aucune carte bancaire requise).
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    groq_model: str = field(default_factory=lambda: os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))


parametres = Parametres()
