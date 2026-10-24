# MITARIDALA — Ton chemin vers la réussite

MITARIDALA est une plateforme éducative malgache qui guide les étudiants de la recherche de ressources jusqu'à la compréhension, la pratique et la progression.

MITARIDALA rassemble dans un même espace :

- les ressources académiques et documents de révision ;
- les quiz et révisions assistés par IA ;
- le Tuteur IA ;
- les cercles d'étude et la messagerie ;
- la classe virtuelle ;
- le suivi des activités, notifications et progression ;
- un référentiel académique structuré par université, composante, mention, filière et niveau.

> **Idée centrale :** aider un étudiant à passer de « je cherche » à « je comprends », puis à « je pratique » et « je progresse ».

**Accès rapides** : [application en ligne](https://mitaridala.onrender.com) · [feuille de route TODO](TODO.md) · [convention responsive](docs/responsive-design.md) · [checklist de release](docs/RELEASE_CHECKLIST.md).

---

## 1. Ce que MITARIDALA apporte

### Ressources académiques

La bibliothèque permet de retrouver des annales, corrigés, fiches et cours classés selon le référentiel académique.

Le dépôt d'un document passe par un processus de validation avant sa publication. Le système peut également analyser le document déposé afin d'aider à identifier automatiquement son type et sa matière. Depuis le panneau de modération, un administrateur peut corriger le titre, le type, la matière, l'année et la filière/parcours, y compris après publication. Si la matière, le type ou la filière change, la fiche pédagogique repasse en attente de vérification.

### Carnet de révision IA personnel

À la fin de chaque séance terminée d'une classe virtuelle, MITARIDALA met en file une fiche de révision individuelle pour chaque étudiant inscrit. La génération est asynchrone et durable ; les fiches sont conservées en base pour ne pas appeler l'IA à chaque consultation ou téléchargement.

Chaque carnet peut contenir un résumé, les objectifs, les notions et exemples essentiels, les formules ou méthodes à retenir, des exercices avec indice et correction, les points à retravailler et un plan de révision espacé. La personnalisation s'appuie sur les supports approuvés et les notes disponibles, ainsi que sur les difficultés et quiz de l'étudiant concerné. Les scores individuels ne sont pas visibles aux autres étudiants ou au professeur.

Depuis la liste des séances, l'étudiant peut télécharger sa fiche au format **PDF** ou **Word (DOCX)**. L'accès est vérifié côté serveur et réservé à son propriétaire. En l'absence de notes ou de transcription de séance, la fiche doit signaler cette limite et présenter un guide général au lieu d'inventer le contenu du direct.

### Fiches de révision automatiques depuis les documents

Lorsqu'un administrateur approuve un document classé **Cours**, MITARIDALA extrait son texte puis met en file une fiche de révision source : résumé orienté examen, notions et exemples, formules/méthodes, exercices avec indices et corrections, points à consolider, auto-évaluation et plan de révision espacée. Le traitement se fait en arrière-plan et les fichiers PDF et Word sont accessibles depuis le hub d'apprentissage du document.

Le carnet pédagogique de référence est généré une fois par document source et reste commun aux utilisateurs autorisés à consulter ce document (un document de cercle reste réservé à ses membres). **La fiche présentée à l'étudiant et ses exports PDF/Word sont ensuite personnalisés pour son compte** : notions faibles ou à revoir d'après ses quiz, plan de révision adapté, exercices associés placés en priorité, acquis confirmés et conseil relié aux échanges de Tuteur IA. Un nouveau compte reçoit une personnalisation de démarrage qui ne prétend pas connaître ses difficultés avant son premier diagnostic. Cette personnalisation est calculée à la demande, à partir de données de l'étudiant connecté ; elle ne modifie jamais le carnet source commun et ne révèle pas le profil d'un autre étudiant. Les contrôles de publication restent prioritaires : un fichier en attente ou rejeté ne déclenche pas de fiche visible. Les documents déjà approuvés sont rattrapés progressivement ; une erreur d'extraction ou un texte insuffisant est signalé au lieu d'être inventé. Les liens de consultation et de téléchargement vérifient à nouveau l'autorisation côté serveur. Si les métadonnées du document changent, la fiche source est invalidée puis régénérée.

### Apprentissage actif

MITARIDALA ne se limite pas à afficher des documents. Les ressources peuvent servir de point de départ pour :

- créer ou passer des quiz ;
- revoir les résultats et les erreurs ;
- cibler les notions difficiles ;
- demander une explication ;
- refaire un exercice ;
- travailler avec d'autres étudiants.

### Tuteur IA

Le Tuteur IA structure ses réponses autour de quatre éléments pédagogiques :

1. explication ;
2. exemple ;
3. exercice ;
4. correction.

Les sorties importantes font l'objet de contrôles locaux et, selon le scénario, d'une vérification multi-modèles avant leur affichage.

L'IA reste un outil d'accompagnement : une réponse générée peut nécessiter une vérification avec le cours, l'enseignant ou une source officielle.

### Quiz IA

Le système peut générer des quiz à partir de ressources ou d'un contexte d'apprentissage. Les tentatives sont conservées pour permettre le suivi des résultats.

Une partie de la validation des quiz vérifie notamment la cohérence des choix, des explications et des résultats mathématiques ou techniques.

### Jeu cérébral

Le jeu cérébral propose des défis courts avec progression de difficulté et retours pédagogiques. L’expérience visuelle est enrichie par des illustrations et des animations ; les interactions doivent rester lisibles sur mobile et l’animation pouvoir être réduite lorsque l’utilisateur préfère moins de mouvement. Les tests du jeu et des illustrations font partie de la suite de régression.

### Collaboration

Les fonctionnalités collaboratives comprennent :

- cercles d'étude ;
- recherche et adhésion aux cercles ;
- messages en temps réel par WebSocket ;
- réponses et discussions autour des messages ;
- réactions, mentions et notifications ;
- classe virtuelle avec vidéo, chat, tableau blanc et devoirs.

---

## 2. Parcours étudiant

Le parcours général est pensé comme une boucle :

~~~text
Chercher
   ↓
Trouver
   ↓
Pratiquer
   ↓
Se tromper
   ↓
Comprendre
   ↓
Réviser
   ↓
Progresser
   ↓
Partager à son tour
~~~

La plateforme inclut également :

- notifications internes ;
- rappel d'inactivité après plusieurs jours sans utilisation ;
- suivi de progression ;
- défis et gamification ;
- révisions adaptatives ;
- historique des quiz et activités.

Les nouveaux comptes étudiants disposent d'un **essai gratuit de 60 jours** pour les fonctionnalités Premium prévues par le projet. Le **Quiz IA** et le **Tuteur IA** sont accessibles gratuitement pendant les **14 premiers jours** de cet essai ; les autres fonctionnalités Premium restent accessibles pendant les 60 jours. Un abonnement payant actif rétablit l'accès aux fonctions IA pendant sa période de validité.

---

## 3. Architecture technique

### Backend

- Python 3.12
- FastAPI
- SQLModel / SQLAlchemy
- Jinja2
- sessions serveur signées par cookie
- WebSocket natif FastAPI
- services métier séparés par domaine

### Base de données

L’application peut fonctionner avec :

- SQLite en local ;
- PostgreSQL en environnement de déploiement ;
- Supabase pour la base PostgreSQL et le stockage documentaire selon la configuration.

Les migrations sont gérées avec Alembic et leur graphe est contrôlé dans la CI.

### File de tâches IA

Les traitements IA longs sont conçus autour d'une file durable :

~~~text
Requête
   ↓
PostgreSQL : tâche durable
   ↓
Redis / Render Key Value : notification rapide
   ↓
Worker IA intégré au service Web
   ↓
Vérification / traitement
   ↓
PostgreSQL : état final
~~~

PostgreSQL reste la source durable. Redis accélère la distribution des tâches mais n'est pas le stockage de vérité.

### Frontend

- Jinja2 et HTML rendu côté serveur ;
- CSS du projet ;
- JavaScript ciblé et sans framework obligatoire ;
- PWA ;
- fondation responsive commune, puis couche de finition visuelle globale chargée après les styles métier ;
- adaptations aux zones de sécurité, à l’orientation, à la navigation tactile, au mode sombre, aux préférences de mouvement réduit et aux modes de contraste renforcé ;
- interfaces adaptatives des pages publiques, étudiantes, collaboratives et administratives. Les couches partagées comprennent notamment **responsive-universal.css** et **interface-polish.css** ; voir [la convention responsive](docs/responsive-design.md).

---

## 4. IA multi-modèles

L'ensemble IA est conçu pour que les modèles coopèrent autour d'une réponse commune :

~~~text
                 ┌─────────────────┐
                 │  Génération     │
                 │  principale     │
                 └────────┬────────┘
                          ↓
                 ┌─────────────────┐
                 │ Critique /      │
                 │ vérification    │
                 └────────┬────────┘
                          ↓
                 ┌─────────────────┐
                 │ Arbitrage /     │
                 │ contrôle final  │
                 └────────┬────────┘
                          ↓
                    Réponse unique
~~~

Les fournisseurs et modèles sont configurables par variables d'environnement. La configuration actuelle prévoit notamment Groq, un modèle critique configurable et Gemini en option.

Le système conserve aussi des informations sur certaines erreurs et interactions de l'ensemble IA afin d'améliorer progressivement les contrôles.

---

## 5. Sécurité et confidentialité

Le projet intègre plusieurs protections côté serveur :

- mots de passe hachés ;
- rotation de session après authentification ;
- empreinte de session invalidée après changement critique du compte ;
- cookie de session sécurisé en production ;
- protection CSRF sur les opérations d'état ;
- limitation anti-brute-force et anti-spam ;
- double authentification TOTP ;
- codes de secours 2FA hachés ;
- choix de double authentification par application TOTP hors ligne ou code OTP par email, sans SMS payant ;
- codes email à usage unique, expirables, hachés en base et protégés contre le rejeu ;

- validation du type réel des fichiers déposés ;
- contrôles contre certains chemins dangereux dans les archives ;
- contrôles d'autorisation côté serveur pour les documents, cercles et fonctions d'administration ;
- politique CSP stricte basée sur nonce et hashes ;
- en-têtes HTTP de sécurité ;
- séparation des secrets serveur et du navigateur.

Les clés de service Supabase, secrets LiveKit, clés IA, SMTP et clé de session doivent rester dans l'environnement serveur.

---

## 6. Mot de passe oublié

Le parcours de récupération du mot de passe existe.

Le principe est :

1. saisir le numéro utilisé pour le compte ;
2. recevoir un code par email lorsque le compte dispose d'une adresse et que le SMTP est configuré ;
3. saisir le code temporaire ;
4. choisir un nouveau mot de passe.

Les codes sont temporaires et protégés par une limitation des tentatives.

La récupération dépend donc d'une adresse email enregistrée sur le compte et d'une configuration SMTP fonctionnelle.

---

## 7. Référentiel académique

Le référentiel est séparé par portée afin d'éviter de mélanger les identifiants et parcours scolaires et universitaires.

~~~text
Université
   ↓
Composante / Faculté
   ↓
Mention
   ↓
Filière / parcours
   ↓
Niveau universitaire

Collège (6e, 5e, 4e, 3e) / Lycée (Seconde, Première, Terminale)
   ↓
Série / option
   ↓
Matière et programme
   ↓
Établissement scolaire (facultatif)
~~~

La plateforme évite autant que possible de déduire automatiquement une classification académique lorsqu'elle est ambiguë. La version initiale du catalogue est datée **2024-2025**, car c'est l'année des PDF RAPS/RAPE officiels effectivement retrouvés pendant cette revue (par exemple les répartitions de 6e, 3e, Terminale A/D et Terminale S/OSE). Elle n'est donc pas présentée comme un référentiel déjà confirmé pour 2026-2027. Le statut reste **partiel** ; les associations de matières non recoupées avec un sommaire par classe/série restent en attente de validation et ne sont pas proposées aux élèves. Le catalogue ne prétend pas être exhaustif pour le technique/professionnel ou pour chaque établissement du pays.

Les sources de base incluent les pages du [MEN sur le collège](https://www.education.gov.mg/systeme-educatif/college/), le [lycée](https://www.education.gov.mg/systeme-educatif/lycee/), la [répartition annuelle du programme scolaire](https://www.education.gov.mg/repartition-annuelle-du-programme-scolaire/) et la [répartition annuelle du programme d'études](https://www.education.gov.mg/repartition-annuelle-du-programme-detudes/). Les séries nouvelles L, S et OSE coexistent dans les sources avec certaines séries historiques en raison du déploiement progressif ; les options filles ne sont jamais inventées par le code.

Pour les administrateurs, la gestion du catalogue scolaire est disponible dans `/admin/referentiel/scolaire`. Les nouvelles matières, options, associations programme/classe et établissements sont enregistrées en attente ; elles ne doivent être proposées aux élèves qu'après vérification d'une source HTTPS du domaine officiel `education.gov.mg`.

Les API publiques principales sont :

- `GET /api/scolaire/niveaux?cycle=college|lycee`
- `GET /api/scolaire/niveaux/{id}/options`
- `GET /api/scolaire/niveaux/{id}/matieres?option_id={id}`
- `GET /api/scolaire/etablissements`

Le dépôt des documents et leur quiz peuvent être associés à une classe et à une série scolaires sans attribuer de fausse filière universitaire. Les fiches de révision utilisent ce niveau scolaire lorsqu'il est disponible. Les cercles scolaires peuvent aussi cibler une matière précise : la sélection est alimentée par l'API des matières vérifiées, la demande conserve la matière lors de l'approbation, et la recherche prend en charge le filtre matière. Une matière reste facultative pour les cercles généraux de classe/série.

La source de données est synchronisée au démarrage lorsque le référentiel versionné est présent. Les anciennes données peuvent être réconciliées et les doublons historiques traités de manière idempotente.

---

## 8. Démarrer en local

### Pré-requis

- Python 3.12 ;
- Git ;
- un environnement virtuel Python ;
- SQLite pour un démarrage simple.

### Installation Windows / VS Code

~~~powershell
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
~~~

Puis ouvrir :

~~~text
http://127.0.0.1:8000
~~~

Sans services externes, le projet peut fonctionner avec SQLite et les fonctionnalités optionnelles restent désactivées lorsque leurs variables d'environnement ne sont pas configurées.

---

## 9. Variables d'environnement

Le fichier .env.example documente les principaux paramètres.

### Base et session

~~~text
DATABASE_URL=
SESSION_SECRET_KEY=
ENVIRONNEMENT=developpement
~~~

### Stockage documentaire

~~~text
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
SUPABASE_BUCKET=documents
~~~

### File IA

~~~text
REDIS_URL=
AI_QUEUE_REDIS_KEY=mahay:ai:queue
~~~

### IA

~~~text
GROQ_API_KEY=
GROQ_MODEL=
GROQ_CRITIC_MODEL=
AI_ENSEMBLE_ENABLED=true
AI_ENSEMBLE_USE_GEMINI=true
GEMINI_API_KEY=
GEMINI_MODEL=
~~~

### Classe virtuelle

~~~text
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
~~~

### Mot de passe oublié

~~~text
EMAIL_TRANSPORT=brevo_api  # nécessaire sur Render Free ; auto en local
BREVO_API_KEY=
BREVO_SENDER_NAME=MITARIDALA
SMTP_FROM_EMAIL=

# SMTP alternatif uniquement si l'hébergeur autorise les ports sortants
SMTP_HOTE=
SMTP_PORT=587
SMTP_UTILISATEUR=
SMTP_MOT_DE_PASSE=
~~~

### Administration

~~~text
ADMIN_PHONE=
ADMIN_INITIAL_PASSWORD=
~~~

Ne committez jamais un fichier .env réel ou un secret.

---

## 10. Tests et qualité

La CI du projet comporte deux jobs principaux (**test** et **postgres-smoke**) et contrôle plusieurs niveaux de qualité :

1. validation du graphe Alembic et de l’identité de release ;
2. compilation Python de l'application et des tests ;
3. vérification du contrat de déploiement Render ;
4. exécution des tests automatisés, isolés par fichier ;
5. smoke test PostgreSQL avec migrations rejouées pour vérifier leur idempotence, puis démarrage réel et vérification du référentiel ;
6. smoke tests navigateur pour le rendu IA, le sélecteur de langue, les cercles, la voix du Tuteur et le responsive ;
7. contrôle responsive couvrant sept familles de pages, onze largeurs d’écran (265 à 1440 px) et les thèmes clair/sombre.

Pour reproduire les contrôles localement :

~~~powershell
python scripts/verify_migrations.py
python -m compileall -q app tests
python scripts/verify_deployment_contract.py
python scripts/verify_release_identity.py
pytest -q
~~~

Pour une vérification proche de la CI, exécutez aussi les tests PostgreSQL avec une base de test dédiée.

---

## 11. Déploiement

Le dépôt contient un Dockerfile et un render.yaml.

Le service Web utilise :

- FastAPI / Uvicorn ;
- PostgreSQL pour les données ;
- Render Key Value pour l'accélération de la file IA ;
- /health comme endpoint de liveness ;
- /ready comme endpoint de readiness applicative.

Le worker IA est intégré au processus Web afin de rester compatible avec le modèle de déploiement retenu pour le service.

---

## 12. Principes de conception

### Côté pédagogique

MITARIDALA cherche à aider l'étudiant à comprendre et pratiquer plutôt qu'à simplement consommer du contenu.

### Côté confiance

Une ressource déposée n'est pas automatiquement publiée. Les contrôles serveur et la modération restent centraux.

### Côté IA

L'IA peut expliquer, générer et vérifier, mais elle ne doit pas être présentée comme une autorité infaillible.

### Côté sécurité

Les décisions d'autorisation sont prises côté serveur. Le frontend sert d'interface, pas de frontière de sécurité.

### Côté évolution

Les migrations et les tests doivent rester idempotents et compatibles avec les environnements SQLite et PostgreSQL utilisés par le projet.

---

## 13. Contribuer

Avant de proposer une modification :

1. comprendre le domaine concerné ;
2. vérifier les dépendances entre routes, modèles, templates et migrations ;
3. ajouter ou mettre à jour les tests concernés ;
4. vérifier la compilation et les scripts de contrôle applicables ;
5. vérifier les migrations si le schéma change ;
6. vérifier le comportement mobile, le mode sombre et les préférences de mouvement si l'interface change ;
7. mettre à jour README.md et TODO.md lorsque les capacités ou les priorités évoluent ;
8. ne fusionner ni déployer qu’après réussite de la CI, puis vérifier les contrôles post-déploiement.

Une fonctionnalité n'est considérée comme terminée que lorsque le parcours utilisateur, ses contrôles de sécurité, ses tests et sa documentation sont cohérents.

---

## 14. Vision

MITARIDALA veut progressivement devenir un espace numérique dans lequel un étudiant peut :

- trouver une ressource fiable ;
- pratiquer ;
- comprendre ses erreurs ;
- demander de l'aide ;
- travailler avec d'autres ;
- suivre sa progression ;
- contribuer à la communauté.

> **Trouver. Comprendre. Pratiquer. Progresser. Partager.**

**MITARIDALA — construire ensemble un espace d'apprentissage pour Madagascar.**
