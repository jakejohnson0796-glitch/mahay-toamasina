# MAHAY Toamasina — hub de révision pour l'Université de Toamasina

Prototype fonctionnel (V2) : les étudiants déposent et téléchargent
gratuitement des annales/fiches/cours par filière, s'entraident dans des
**cercles d'étude** en chat temps réel, et peuvent générer un **vrai quiz
IA** à partir d'un document. Les sponsors et répétiteurs paient un
abonnement mensuel pour être visibles auprès des étudiants — c'est ce
deuxième côté du marché qui finance la plateforme, pas l'étudiant.

Identité visuelle : le fil conducteur est le port de Toamasina — chaque
document reçoit une référence façon "manifeste de cargo" (`TOA-DEG-2025-0147`)
et un statut tamponné (approuvé / en attente / rejeté).

## Nouveau dans cette version

- **Supabase** (optionnel) : base de données Postgres et stockage des
  fichiers déposés peuvent basculer sur Supabase via `.env`, à la place de
  SQLite/disque local. Utile dès qu'on déploie ailleurs qu'en local (le
  disque d'un serveur comme Render/Railway est éphémère).
- **Cercles d'étude** : salons de discussion en temps réel (WebSocket)
  où les étudiants créent un groupe (par filière ou libre) et échangent
  des messages, historisés en base.
- **Quiz IA réel, sur une API gratuite** : `app/ai_quiz.py` appelle
  désormais l'API **Groq** (clé gratuite, sans carte bancaire) avec le
  texte extrait du document (`app/text_extraction.py`, PDF via
  `pdfplumber`, OCR optionnel via `pytesseract`), et renvoie un vrai QCM
  (4 choix, bonne réponse, explication).

## Démarrer en local (Windows / VS Code)

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Par défaut (fichier `.env` vide), tout fonctionne exactement comme en V1 :
SQLite (`mahay.db`) + dossier `uploads/` en local, facultés/filières
pré-remplies (`app/seed_data.py`). Seule la génération de quiz nécessite
une clé API pour fonctionner (voir plus bas) — sans elle, la page affiche
un message clair au lieu de planter.

Pour accéder au panneau `/moderation` (valider ou rejeter les documents
déposés), il faut d'abord s'inscrire normalement sur le site, puis se
promouvoir admin en ligne de commande :

```
python -m app.creer_admin 0341234567
```

## Configurer Supabase (base de données + stockage)

1. Créez un projet sur [supabase.com](https://supabase.com) (gratuit pour
   démarrer).
2. **Base de données** : *Project Settings > Database > Connection
   string > URI*. Collez cette valeur dans `DATABASE_URL` (fichier `.env`).
   Choisissez le mode "Transaction pooler" si vous déployez sur un
   hébergeur serverless (Render, Railway...), sinon la connexion directe
   suffit. Au démarrage suivant, `creer_tables()` crée automatiquement
   les tables sur Postgres — rien d'autre à migrer à la main.
3. **Stockage des documents** : *Storage > New bucket* — créez un bucket
   (ex: `documents`), public si vous voulez que le téléchargement
   redirige directement vers un lien public (le cas normal ici, puisque
   les documents approuvés sont déjà censés être publics). Renseignez
   `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (Project Settings > API >
   service_role, **jamais** la clé `anon` côté serveur) et
   `SUPABASE_BUCKET` dans `.env`.
4. Laissez ces variables vides pour continuer en local (SQLite + disque).

## Configurer la génération de quiz IA (API gratuite Groq)

1. Créez un compte sur [console.groq.com](https://console.groq.com) — pas
   de carte bancaire requise. *API Keys > Create API Key*.
2. Renseignez `GROQ_API_KEY` dans `.env`. `GROQ_MODEL` est réglé par
   défaut sur `llama-3.3-70b-versatile`.
3. Limites du palier gratuit (largement suffisantes pour un quiz généré
   à la demande par les étudiants) : 30 requêtes/minute, 1000/jour sur ce
   modèle. Si la plateforme grossit beaucoup, Groq propose un palier payant
   (sans minimum) qui multiplie ces limites par 10.
4. Pour les documents scannés (images, PDF sans texte sélectionnable),
   l'OCR (`pytesseract` + `pdf2image`) nécessite en plus le binaire
   Tesseract (`apt install tesseract-ocr tesseract-ocr-fra` sous Linux,
   installeur officiel sous Windows) et `poppler` pour les PDF
   (`apt install poppler-utils`). Sans ces binaires système, l'OCR est
   simplement ignoré (pas de crash) et seuls les PDF avec texte
   sélectionnable donnent un quiz.

## Cercles d'étude — comment ça marche techniquement

Chat en temps réel via **WebSocket FastAPI natif** (`app/ws_manager.py`,
`app/routers/cercles_router.py`) — pas de service tiers, ça reste 100%
Python, cohérent avec le reste du projet (voir plus bas, "pas de
framework JS"). L'authentification du salon réutilise directement le
cookie de session existant (Starlette applique `SessionMiddleware` aussi
bien aux requêtes HTTP qu'aux WebSockets).

**Limite connue** : le gestionnaire de connexions (`GestionnaireConnexions`)
garde les connexions actives en mémoire, dans le process Python. Avec un
seul worker `uvicorn` (le mode par défaut, largement suffisant pour ce
public), c'est parfait. Si un jour vous scalez sur plusieurs workers ou
plusieurs machines, il faudra un pub/sub partagé entre process pour
diffuser les messages (Supabase Realtime en écoutant les insertions sur
`message_cercle`, ou Redis).

## Ce qui est déjà fonctionnel (testé de bout en bout)

- Inscription / connexion (par numéro de téléphone + mot de passe)
- Dépôt d'un document (PDF, image...) avec filière/matière/année/type,
  vers Supabase Storage ou le disque local selon la config
- File de modération (un admin approuve ou rejette avant publication)
- Liste filtrable des documents publiés + téléchargement
- Cercles d'étude : création, adhésion, chat temps réel persistant
- Quiz généré par une vraie IA à partir du texte extrait du document
- Page sponsoring avec choix du moyen de paiement (le paiement réel
  n'est pas encore branché — voir "Prochaines étapes")

## Ce qui reste à brancher (volontairement laissé en `TODO` dans le code)

1. **Paiement mobile money réel** (`app/routers/sponsoring_router.py`) :
   une passerelle comme PayBriq, Efaina ou Voaray unifie MVola/Orange
   Money/Airtel Money derrière une seule API — ne créer l'abonnement en
   statut `actif` qu'après confirmation par leur webhook.
2. **Icônes PWA** : `app/static/manifest.json` a un tableau `icons` vide
   — ajouter un PNG 192×192 et 512×512 pour que l'installation sur
   Android affiche une vraie icône.
3. ~~Limiter le quiz IA aux abonnés~~ **Fait** : `/documents/{id}/quiz` et
   les cercles d'étude nécessitent maintenant un essai gratuit actif ou
   un abonnement étudiant valide (`app/dependencies.py`, `app/subscription.py`).
4. **Modération des cercles/messages** : pour l'instant, tout étudiant
   connecté peut créer un cercle et y écrire sans limite de débit — un
   garde-fou anti-spam plus poussé (limite de messages/minute, signalement)
   serait à ajouter avant un déploiement à grande échelle.

## Feuille de route suggérée

- **Phase 1 (maintenant)** : valider la demande sur une seule faculté
  (DEGMIA par ex.) avec un petit groupe d'étudiants réels avant d'élargir.
- **Phase 2** : brancher le vrai paiement mobile money pour les sponsors.
- **Phase 3** : limiter le quiz IA aux sponsors/abonnés comme argument de
  vente ("visibilité + accès à l'outil pour vos élèves").
- **Phase 4** : étendre aux autres facultés, puis éventuellement à un
  espace petites annonces/petits boulots (mentionné dans l'idéation
  initiale mais volontairement hors scope de cette V1/V2).

## Pourquoi ces choix techniques

- **FastAPI + SQLModel + SQLite (ou Postgres/Supabase)** : reste dans un
  seul langage (Python), cohérent avec tes autres projets ; SQLModel/
  SQLAlchemy abstraient le moteur donc le code métier ne change pas selon
  la base utilisée.
- **Jinja2 (rendu HTML côté serveur), pas de framework JS** : pas besoin
  d'apprendre React/Vue pour livrer cette version ; même le chat temps
  réel utilise du JavaScript vanilla minimal (WebSocket natif du
  navigateur) plutôt qu'un framework ou une lib tierce.
- **PWA (manifest + service worker) plutôt qu'une app Android native** :
  un seul code sert le web ET le mobile (installable sur l'écran
  d'accueil), sans avoir à apprendre Kotlin/Java.
