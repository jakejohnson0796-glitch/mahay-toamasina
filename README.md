# MITARIDALA — Ton chemin vers la réussite

MITARIDALA est une plateforme éducative conçue pour les élèves, étudiants et enseignants de Madagascar. Elle relie les ressources scolaires et universitaires à la pratique, à l'accompagnement pédagogique et au suivi des progrès.

**Application :** [mitaridala.onrender.com](https://mitaridala.onrender.com) · **Travail restant :** [TODO.md](TODO.md) · **Responsive :** [docs/responsive-design.md](docs/responsive-design.md) · **Release :** [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md)

> **Objectif pédagogique :** trouver une ressource, comprendre, pratiquer, corriger ses erreurs, réviser et progresser. L'IA aide l'apprentissage ; elle ne remplace ni le raisonnement de l'élève, ni le cours, ni la validation d'un enseignant.

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Parcours d'apprentissage](#parcours-dapprentissage)
- [Architecture](#architecture)
- [Démarrage local](#démarrage-local)
- [Configuration](#configuration)
- [Tests et vérifications](#tests-et-vérifications)
- [Déploiement Render](#déploiement-render)
- [Sécurité et confidentialité](#sécurité-et-confidentialité)
- [Référentiel académique](#référentiel-académique)
- [Contribuer](#contribuer)

## Fonctionnalités

### Documents et bibliothèque pédagogique
- Recherche dans les cours, annales, exercices et corrigés.
- Dépôt et modération avant publication ; l'administration peut rectifier les métadonnées (titre, type, matière, année et rattachement académique).
- Fichiers servis par une route contrôlée côté serveur : un document approuvé n'est pas pour autant librement téléchargeable par un visiteur anonyme. Les documents de cercle restent réservés aux membres autorisés.
- Validation des extensions, limites de taille et contrôles de fichiers avant stockage.

### Fiches de révision
- Un cours approuvé peut déclencher la génération asynchrone d'une fiche pédagogique persistée, avec résumé, notions importantes, méthodes/formules, exemples et exercices guidés.
- Les fiches issues des documents ont un contenu source commun ; leur présentation et leur ordre de priorité peuvent être adaptés à la progression de l'étudiant connecté.
- Les fiches produites après une séance de classe virtuelle sont individuelles. Elles peuvent être exportées en PDF ou DOCX lorsque les sources disponibles le permettent.
- Une tâche en attente, échouée ou sans contenu source suffisant ne doit pas être présentée comme une fiche prête. La plateforme doit signaler les limites au lieu d'inventer le contenu d'un cours ou d'une séance.

### Quiz IA et Tuteur IA
- Quiz générés à partir d'une matière, d'un niveau, d'un document ou de notions à réviser, avec historique et analyse des erreurs.
- Tuteur IA conçu pour expliquer une notion, donner un exemple, proposer un exercice puis guider vers la correction.
- Des vérifications de cohérence et de format sont appliquées aux sorties selon le parcours. Les réponses générées peuvent néanmoins contenir des erreurs ; vérifier les résultats importants avec le cours ou une source fiable.

### Jeu cérébral et jeux classiques
- Défis courts, niveaux progressifs et retours liés aux réponses.
- Les pages de jeu doivent rester utilisables sur petit écran, au clavier et avec une préférence de réduction des animations.
- La diversité et la fraîcheur du contenu des quiz et des jeux restent des objectifs de qualité à mesurer par des tests dédiés.

### Cercles et classe virtuelle
- Recherche, création et adhésion à des cercles d'étude.
- Messagerie et mises à jour temps réel avec WebSocket.
- Classe virtuelle avec les outils intégrés disponibles, dont vidéo, chat, tableau blanc et devoirs.
- Notifications, activités, progression et rappels.

### Profils scolaires et universitaires
Le référentiel sépare les parcours afin d'éviter de mélanger les identifiants universitaires et scolaires :

~~~text
Université
  └── Université → composante/faculté → mention → filière/parcours → niveau

Collège
  └── 6e → 5e → 4e → 3e → matières et programme vérifiés

Lycée
  └── Seconde → Première → Terminale → série/option → matières vérifiées
~~~

Les profils professeur peuvent déclarer les cycles concernés, mais une déclaration ne vaut pas automatiquement validation administrative. Les données de catalogue encore ambiguës doivent rester à vérifier plutôt que d'être inventées.

## Parcours d'apprentissage

~~~text
Chercher une ressource
        ↓
Lire et comprendre
        ↓
Répondre à un quiz / essayer un exercice
        ↓
Analyser les erreurs et cibler une notion
        ↓
Demander une explication au Tuteur IA
        ↓
Réviser et recommencer
        ↓
Observer sa progression
~~~

Les règles commerciales actuellement prévues par le projet distinguent deux périodes : **Quiz IA et Tuteur IA pendant 14 jours**, et les autres accès Premium éligibles pendant **60 jours** pour un nouveau compte, selon les règles d'accès de l'application. Les droits effectifs restent déterminés côté serveur et par l'état de l'abonnement.

## Architecture

### Technologies principales
- **Python 3.12**, FastAPI et Uvicorn.
- **SQLModel / SQLAlchemy** et **Alembic** pour les données et migrations.
- **Jinja2**, HTML, CSS et JavaScript pour l'interface rendue côté serveur.
- **SQLite** pour un démarrage local simple ; **PostgreSQL** pour le service de production.
- **Supabase Storage** pour le stockage documentaire distant lorsqu'il est configuré.
- **Redis / Render Key Value** pour accélérer la distribution des tâches IA.
- **KaTeX**, Marked, DOMPurify et Highlight.js pour afficher du contenu scientifique et formaté.
- **LiveKit**, lorsqu'il est configuré, pour les fonctions de communication de la classe virtuelle.

### Tâches IA et données
PostgreSQL conserve l'état durable des tâches et leurs résultats. Redis sert de mécanisme de notification rapide ; il n'est pas la seule source de vérité. Le worker IA est intégré au processus Web pour rester compatible avec le déploiement retenu. Des contrôles de reprise et de tâche en attente restent à surveiller en exploitation.

~~~text
Route / action utilisateur
        ↓
Enregistrement durable de la tâche dans PostgreSQL
        ↓
Notification rapide via Redis (si configuré)
        ↓
Worker IA → génération → contrôle
        ↓
Résultat et statut enregistrés en base
~~~

### Interface
Le frontend utilise des templates et feuilles de style du projet, sans imposer de framework CSS supplémentaire. Les dépendances du rendu sont vérifiées et embarquées pendant la construction de l'image afin que les pages n'aient pas à s'appuyer sur un CDN pour ces bibliothèques. Les règles responsive communes, la navigation mobile, les thèmes clair/sombre et la réduction des animations sont documentés dans [docs/responsive-design.md](docs/responsive-design.md).

## Démarrage local

### Prérequis
- Python **3.12** ;
- Git ;
- un terminal (PowerShell sous Windows, Bash sous Linux/macOS) ;
- SQLite pour commencer sans base externe.

### Windows / PowerShell

~~~powershell
git clone https://github.com/jakejohnson0796-glitch/mahay-toamasina.git
cd mahay-toamasina
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
~~~

### Linux / macOS

~~~bash
git clone https://github.com/jakejohnson0796-glitch/mahay-toamasina.git
cd mahay-toamasina
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
~~~

Ouvrir ensuite [http://127.0.0.1:8000](http://127.0.0.1:8000).

Si **DATABASE_URL** est vide, le projet utilise SQLite pour le développement. Compléter seulement les variables des services que l'on veut essayer. Le fichier **.env.example** contient des valeurs d'exemple, pas des secrets de production. Pour générer une clé de session de développement distincte :

~~~bash
python -c "import secrets; print(secrets.token_hex(32))"
~~~

Copier la valeur obtenue dans **SESSION_SECRET_KEY** de **.env**. Ne jamais exposer ni committer le contenu d'un vrai fichier **.env**.

## Configuration

Les paramètres de référence se trouvent dans [.env.example](.env.example) et dans [render.yaml](render.yaml). Principales familles :

| Variable | Utilité | Requis pour |
|---|---|---|
| **DATABASE_URL** | URL de base de données | PostgreSQL en production ; vide en local pour SQLite |
| **SESSION_SECRET_KEY** | Signature des sessions | Obligatoire en production ; valeur secrète et aléatoire |
| **ENVIRONNEMENT** | Mode d'exécution | **developpement** en local ; **production** sur Render |
| **SUPABASE_URL**, **SUPABASE_SERVICE_KEY**, **SUPABASE_BUCKET** | Stockage distant | Dépôts durables via Supabase Storage |
| **REDIS_URL**, **AI_QUEUE_REDIS_KEY** | Notification de tâches IA | Redis/Render Key Value configuré |
| **GROQ_API_KEY**, **GROQ_MODEL** | Fournisseur principal des parcours IA | Fonctions IA qui utilisent Groq |
| **GROQ_CRITIC_MODEL**, **AI_ENSEMBLE_ENABLED** | Critique et arbitrage IA | Vérification multi-modèles activée |
| **GEMINI_API_KEY**, **GEMINI_MODEL** | Vérification indépendante optionnelle | Gemini activé et configuré |
| **LIVEKIT_URL**, **LIVEKIT_API_KEY**, **LIVEKIT_API_SECRET** | Communication en classe virtuelle | Fonctionnalités LiveKit |
| **EMAIL_TRANSPORT**, **BREVO_API_KEY**, variables SMTP_* | E-mails, OTP et récupération de compte | Envoi d'e-mails configuré |

La configuration de Render force **ENVIRONNEMENT=production** et utilise **autoDeployTrigger: checksPass**. Ne remplacez pas un secret de production par la valeur de démonstration du fichier exemple. Ne mettez jamais les clés API, secrets LiveKit, clé Supabase de service ou mot de passe de base dans le navigateur ou dans Git.

Pour le service Render gratuit, le dépôt prévoit le transport e-mail Brevo par API HTTPS. Un SMTP alternatif dépend des ports sortants autorisés par l'hébergeur et de la configuration réelle du compte expéditeur.

## Tests et vérifications

La CI exécute deux jobs principaux : **test** et **postgres-smoke**.

Le job **test** contrôle notamment :
- la compilation Python et le graphe Alembic ;
- le contrat de déploiement et l'identité de release ;
- le rendu IA, la sélection de langue et plusieurs scripts de smoke test navigateur ;
- le responsive des pages ciblées, la hiérarchie des cercles, la navigation retour, la voix du Tuteur et la lisibilité des fiches ;
- les fichiers de test Python isolément, afin de limiter les interférences entre certains tests historiques.

Le job **postgres-smoke** applique les migrations à PostgreSQL 16, les rejoue pour vérifier leur idempotence, puis démarre l'application et contrôle le référentiel. Ces contrôles sont complémentaires : ils ne remplacent pas les essais manuels des parcours critiques ni la vérification du service après déploiement.

Commandes utiles depuis l'environnement virtuel :

~~~bash
python scripts/verify_migrations.py
python -m compileall -q app tests
python scripts/verify_deployment_contract.py
python scripts/verify_release_identity.py
~~~

La CI isole chaque fichier de test Python dans un processus distinct. Pour reproduire cette stratégie sous Bash :

~~~bash
for test_file in tests/test_*.py; do
  python -m pytest -q "$test_file" || exit 1
done
~~~

Sous PowerShell :

~~~powershell
Get-ChildItem tests/test_*.py | ForEach-Object {
    python -m pytest -q $_.FullName
    if ($LASTEXITCODE -ne 0) { throw "Échec du test : $($_.Name)" }
}
~~~

Pour reproduire l'environnement de production, utiliser une base PostgreSQL de test et la checklist [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md). Ne jamais exécuter de test destructif sur les données de production.

### Contrôles après déploiement
- **GET /health** : liveness rapide du processus ;
- **GET /ready** : disponibilité applicative, vérification de la base et fin de l'initialisation ;
- journaux de démarrage, migrations, initialisation des données et worker IA ;
- vérification, depuis un navigateur, des parcours modifiés et des contrôles d'autorisation.

## Déploiement Render

Le service public MITARIDALA est hébergé sur Render, région de Francfort, depuis la branche **main**. La configuration du service utilise Docker et **/health** comme contrôle de liveness. Render est configuré pour déployer les commits après réussite des contrôles CI (**checksPass**) ; ne pas contourner ce garde-fou avec un déploiement manuel pendant une CI rouge ou incomplète.

Le démarrage de production doit notamment avoir :
1. **ENVIRONNEMENT=production** ;
2. une **SESSION_SECRET_KEY** réelle, aléatoire et privée ;
3. **DATABASE_URL** pointant sur PostgreSQL ;
4. les variables Storage nécessaires aux dépôts durables ;
5. les clés des fournisseurs activés et les variables d'e-mail requises par les parcours utilisés.

Le processus applique les migrations et initialise les données au démarrage. **/health** et **/ready** n'ont pas la même signification : un processus peut être vivant avant d'être prêt à servir tous les parcours.

En cas d'échec, arrêter le processus de livraison, analyser les événements et les logs Render, puis corriger ou revenir au commit précédent connu comme fonctionnel. Ne pas fusionner un changement applicatif avec une CI rouge.

## Sécurité et confidentialité

Les protections existantes comprennent notamment :
- cookies de session configurés pour la production HTTPS et invalidation selon les opérations sensibles ;
- contrôles CSRF, limites anti-abus sur plusieurs routes et confirmations pour certaines actions d'administration ;
- double authentification TOTP et codes e-mail temporaires selon la configuration ;
- validation des fichiers déposés et vérifications d'autorisation côté serveur ;
- URLs signées de stockage distant pour éviter de dépendre d'un accès public permanent aux fichiers privés ;
- en-têtes HTTP de sécurité et politique CSP définie par le projet ;
- limite de taille du corps HTTP exécutée avant le parsing des formulaires : **2 MiB par défaut**, **21 MiB** pour un document/devoir unique, **102 MiB** pour le dépôt multiple prévu et **6 MiB** pour une photo de profil. Les limites comprennent une marge pour l'enveloppe multipart ; les limites de fichier restent contrôlées séparément.

Ces mesures réduisent certains risques connus, mais aucune application ne peut être déclarée impossible à contourner. Les autorisations doivent être validées côté serveur, les secrets conservés hors du dépôt et les protections régulièrement testées. La configuration de l'adresse IP utilisée pour les limites anti-abus dépend des proxys réels en amont et reste à vérifier dans les scénarios d'exploitation documentés dans [TODO.md](TODO.md).

## Référentiel académique

Le projet distingue les données universitaires, scolaires et techniques/professionnelles. Les sources de référence incluent notamment :
- [MEN — Collège](https://www.education.gov.mg/systeme-educatif/college/) ;
- [MEN — Lycée](https://www.education.gov.mg/systeme-educatif/lycee/) ;
- [MEN — Répartition annuelle du programme scolaire](https://www.education.gov.mg/repartition-annuelle-du-programme-scolaire/) ;
- [MEN — Répartition annuelle du programme d'études](https://www.education.gov.mg/repartition-annuelle-du-programme-detudes/) ;
- [METFP — Cartographie](https://www.metfp.gov.mg/cartographie) ;
- [METFP — Ressources de formation](https://www.metfp.gov.mg/formation/ressource).

**Le catalogue scolaire et ETFP reste partiel.** Les sources scolaires utilisées comprennent des documents datés de 2024–2025 ; elles ne suffisent pas à certifier toute l'offre actuelle 2026–2027. Une école répertoriée, un référentiel de formation retrouvé et une formation effectivement ouverte pendant une année donnée sont trois statuts différents. Les lignes dont la source ou l'année n'est pas vérifiée doivent rester en attente de validation. La feuille de route détaille les lots de vérification nationaux dans [TODO.md](TODO.md), et le chantier de conception des cycles est décrit dans [docs/extension-college-lycee-universite.md](docs/extension-college-lycee-universite.md).

Quelques endpoints de catalogue sont exposés par l'application :
- **GET /api/scolaire/niveaux?cycle=college|lycee**
- **GET /api/scolaire/niveaux/{id}/options**
- **GET /api/scolaire/niveaux/{id}/matieres?option_id={id}**
- **GET /api/scolaire/etablissements**
- **GET /api/scolaire/etfp/parcours?q={mot}&secteur={secteur}**
- **GET /api/scolaire/offres?region={region}&type_offre=formation&annee_scolaire=2026-2027**
- **GET /api/scolaire/etablissements/{id}/offres?annee_scolaire=2026-2027**

La présence d'une route ne garantit pas l'exhaustivité de ses données : les offres et rattachements doivent être vérifiés par rapport aux sources et à leur date.

## Contribuer

Avant de proposer un changement :

1. lire le domaine concerné et les documents liés ;
2. identifier les dépendances entre routes, services, modèles, templates et migrations ;
3. ajouter ou mettre à jour des tests ciblés ;
4. exécuter les contrôles de compilation, migrations et tests applicables ;
5. pour l'interface, vérifier les petits écrans, les thèmes, le clavier et la réduction des animations ;
6. mettre à jour **README.md** et **TODO.md** si le comportement ou la priorité change ;
7. créer une branche et une pull request claire ; attendre une CI verte avant la fusion ;
8. après fusion/déploiement, vérifier **/health**, **/ready**, les logs et le parcours utilisateur modifié.

Les changements de rendu scientifique ne doivent pas être inclus dans une modification sans rapport. Lorsqu'un changement touche LaTeX/KaTeX, ajouter des cas de régression avant la livraison.

## Vision

**Trouver. Comprendre. Pratiquer. Progresser. Partager.**

MITARIDALA veut construire, avec ses utilisateurs et enseignants, un espace d'apprentissage fiable et adapté aux réalités scolaires et universitaires de Madagascar.
