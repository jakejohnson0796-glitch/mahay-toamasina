# Déployer MITARIDALA sur Google Cloud Run en parallèle de Render

Ce déploiement crée un **second hébergement** nommé `mitaridala` sur Cloud Run.
Il ne modifie ni le service Render, ni son domaine, ni son déploiement automatique.
Render reste la production actuelle et la solution de retour arrière.

## Architecture préparée

- Image Docker construite à partir du `Dockerfile` existant et publiée dans Artifact Registry.
- Cloud Run dans `africa-south1` (Johannesburg) par défaut, plus proche de Madagascar que les régions européennes. Vérifier toutefois la région de la base Supabase : placer Cloud Run près de la base peut réduire la latence. Modifier la variable GitHub `GCP_REGION` avant le déploiement si nécessaire.
- PostgreSQL et Supabase Storage restent externes. Aucune base locale ni aucun fichier du disque éphémère Cloud Run ne devient la source de données.
- Le worker IA peut fonctionner avec la file PostgreSQL sans Redis privé Render. `AI_WORKER_INLINE_ENABLED=true` l'active sur Cloud Run.
- Le service est limité à une instance au départ, car le gestionnaire WebSocket des cercles garde encore de l'état en mémoire. L'affinité de session est activée, mais elle ne remplace pas une synchronisation distribuée.

## Coûts et limites à connaître avant de cliquer sur Deploy

Le workflow utilise une instance minimale (1 vCPU, 1 Gio), une seule instance maximum et l'allocation CPU permanente. Ce choix est nécessaire pour que le worker IA puisse traiter les tâches PostgreSQL même lorsqu'aucune requête HTTP n'est en cours. **Cela entraîne une facturation continue tant que l'instance minimale tourne**, même si le site reçoit peu de visites. Consulter le calculateur Google Cloud et définir un budget/alerte de facturation avant le premier déploiement.

Le service garde un délai HTTP/WebSocket de 60 minutes. Cloud Run peut donc fermer une connexion WebSocket à l'expiration de ce délai ou lors d'un redémarrage. Les clients doivent pouvoir se reconnecter. L'affinité de session est de meilleure qualité, mais reste une affinité « best effort ».

## 1. Créer/sélectionner le projet Google Cloud

1. Ouvrir [Google Cloud Console](https://console.cloud.google.com/).
2. Sélectionner un projet de test dédié (par exemple `mitaridala-cloud`) ou en créer un.
3. Activer la facturation et définir un budget/une alerte.
4. Noter le **Project ID** et le **Project number** dans la page d'accueil du projet.
5. Ouvrir [Artifact Registry](https://console.cloud.google.com/artifacts) et créer un dépôt :
   - Nom : `mitaridala`
   - Format : Docker
   - Région : même région que `GCP_REGION` (par défaut `africa-south1`)
   - Mode : standard

Activer également ces API dans « APIs et services > Bibliothèque » :
- Cloud Run API (`run.googleapis.com`)
- Artifact Registry API (`artifactregistry.googleapis.com`)
- IAM API (`iam.googleapis.com`)
- Security Token Service API (`sts.googleapis.com`)
- IAM Credentials API (`iamcredentials.googleapis.com`)
- Secret Manager API (`secretmanager.googleapis.com`)

GitHub Actions construit l'image lui-même : Cloud Build n'est pas nécessaire pour ce workflow.

## 2. Créer les comptes de service

Dans « IAM et administration > Comptes de service », créer :

**Compte de déploiement**
- ID : `mitaridala-deployer`
- Courriel : `mitaridala-deployer@PROJECT_ID.iam.gserviceaccount.com`
- Rôles au niveau du projet :
  - Cloud Run Admin (`roles/run.admin`)
  - Artifact Registry Writer (`roles/artifactregistry.writer`)
  - Secret Manager Viewer (`roles/secretmanager.viewer`) pour vérifier la présence des secrets.

**Compte d'exécution**
- ID : `mitaridala-runtime`
- Courriel : `mitaridala-runtime@PROJECT_ID.iam.gserviceaccount.com`
- Lui accorder Secret Manager Secret Accessor (`roles/secretmanager.secretAccessor`) sur les secrets utilisés par l'application.

Sur le compte `mitaridala-runtime`, accorder aussi au compte de déploiement le rôle Service Account User (`roles/iam.serviceAccountUser`). Le workflow doit pouvoir déployer le service en utilisant ce compte d'exécution.

Remplacer `PROJECT_ID` par le vrai identifiant du projet, sans chevrons.

## 3. Configurer Workload Identity Federation pour GitHub

Ne crée pas de clé JSON de compte de service et ne la stocke pas dans GitHub. Le workflow utilise OIDC / Workload Identity Federation.

Dans « IAM et administration > Workload Identity Federation » :

1. Créer un pool :
   - Nom : `github-actions-mitaridala`
   - ID : `github-actions-mitaridala`
   - Emplacement : global
2. Ajouter un fournisseur :
   - Type : OpenID Connect (OIDC)
   - Nom / ID : `github`
   - Émetteur : `https://token.actions.githubusercontent.com`
   - Audience : audience par défaut
3. Mappages d'attributs :
   - `google.subject` = `assertion.sub`
   - `attribute.repository` = `assertion.repository`
   - `attribute.ref` = `assertion.ref`
4. Condition d'attribut :
   `assertion.repository == 'jakejohnson0796-glitch/mahay-toamasina' && assertion.ref == 'refs/heads/main'`
5. Sur le compte de service `mitaridala-deployer`, autoriser le principal du dépôt à utiliser le compte via le rôle Workload Identity User (`roles/iam.workloadIdentityUser`). Le principal a cette forme :
   `principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions-mitaridala/attribute.repository/jakejohnson0796-glitch/mahay-toamasina`

Remplacer `PROJECT_NUMBER` par le numéro numérique du projet. La ressource du fournisseur à enregistrer dans GitHub est :
`projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions-mitaridala/providers/github`

La condition limite l'identité au dépôt exact et à la branche `main`.

## 4. Créer les secrets dans Secret Manager

Dans [Secret Manager](https://console.cloud.google.com/security/secret-manager), créer un secret distinct pour chaque valeur. Ajouter la valeur comme nouvelle version, puis accorder au compte `mitaridala-runtime` le rôle Secret Accessor sur chaque secret.

Secrets requis par le workflow :
- `DATABASE_URL` : chaîne PostgreSQL/Supabase (pas SQLite).
- `SESSION_SECRET_KEY` : secret aléatoire long, au moins 32 caractères.
- `SUPABASE_URL` : URL du projet Supabase.
- `SUPABASE_SERVICE_KEY` : clé service_role du projet Supabase.
- `GROQ_API_KEY` : clé Groq pour les fonctions IA centrales.

Secrets facultatifs, ajoutés automatiquement s'ils existent :
- `GEMINI_API_KEY`
- `BREVO_API_KEY`, `SMTP_FROM_EMAIL`, `SMTP_HOTE`, `SMTP_UTILISATEUR`, `SMTP_MOT_DE_PASSE`
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
- `ADMIN_PHONE`, `ADMIN_INITIAL_PASSWORD`

Ne pas copier `REDIS_URL` depuis Render : son adresse Key Value interne n'est pas accessible depuis Cloud Run. Sur Cloud Run, le worker peut utiliser PostgreSQL.

**Données :** si Cloud Run doit servir seulement à tester sans toucher aux données réelles, utiliser un projet Supabase de staging et son bucket séparé. Si tu réutilises les identifiants Supabase de Render, les deux hébergements liront et modifieront la même base et les mêmes fichiers. Faire une sauvegarde vérifiée avant le premier démarrage : l'application exécute les migrations au démarrage.

## 5. Ajouter les variables et secrets dans GitHub

Dans le dépôt GitHub, ouvrir « Settings > Secrets and variables > Actions ».

**Repository variables**
- `GCP_PROJECT_ID` = Project ID Google Cloud.
- `GCP_REGION` = `africa-south1` par défaut (ou région choisie).
- `GCP_RUNTIME_SERVICE_ACCOUNT` = `mitaridala-runtime@PROJECT_ID.iam.gserviceaccount.com`.

**Repository secrets**
- `GCP_WORKLOAD_IDENTITY_PROVIDER` = ressource complète du fournisseur créée à l'étape 3.
- `GCP_DEPLOY_SERVICE_ACCOUNT` = `mitaridala-deployer@PROJECT_ID.iam.gserviceaccount.com`.

Les clés de l'application restent dans Secret Manager, pas dans les variables GitHub.

## 6. Lancer le déploiement

1. Vérifier que les cinq secrets requis sont présents dans Secret Manager et accessibles au compte `mitaridala-runtime`.
2. Dans le dépôt, ouvrir l'onglet Actions.
3. Sélectionner « Deploy MITARIDALA to Google Cloud Run ».
4. Cliquer sur « Run workflow », choisir la branche `main`, saisir `DEPLOY`, puis lancer.
5. Le workflow construit l'image, la publie dans Artifact Registry, déploie le service `mitaridala`, puis vérifie `/ready`, l'identifiant exact du commit et la disponibilité du worker IA PostgreSQL.

Le workflow est manuel uniquement. Un push sur `main` ne publie rien automatiquement sur Google Cloud. Render continue à suivre ses propres règles de déploiement indépendamment.

## 7. Après le premier déploiement

- Ouvrir Cloud Run > Services > `mitaridala` et utiliser l'URL `run.app` affichée.
- Vérifier `/health` (release, `ai_queue_backend=postgresql`, `ai_worker_alive=true`) et `/ready`.
- Tester connexion, quiz/tuteur IA, documents, cercles d'étude et classe virtuelle depuis l'URL Cloud Run.
- Ne pas changer le domaine DNS et ne pas supprimer Render avant validation fonctionnelle et vérification des coûts.
- Pour revenir en arrière, cesser d'utiliser l'URL Cloud Run : l'URL et le déploiement Render restent inchangés.

## Paramètres de lancement initiaux

Le workflow impose volontairement :
- `min instances = 1`, `max instances = 1`
- CPU permanent, 1 vCPU, mémoire 1 Gio
- 40 requêtes simultanées maximum par conteneur
- timeout 3600 secondes
- affinité de session activée

Cette configuration est un pilote prudent pour l'état WebSocket en mémoire, pas encore une architecture multi-instance. Pour monter en charge, il faudra externaliser le gestionnaire temps réel (Redis Pub/Sub ou Supabase Realtime) et revoir le dimensionnement.
