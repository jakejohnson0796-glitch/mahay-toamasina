# Gasy Mahay — plateforme d'apprentissage pour les étudiants de Madagascar

Gasy Mahay est une plateforme web d'apprentissage et d'entraide conçue pour les étudiants de Madagascar.

Elle rassemble dans un même espace :

- les ressources académiques et documents de révision ;
- les quiz et révisions assistés par IA ;
- le Tuteur IA ;
- les cercles d'étude et la messagerie ;
- la classe virtuelle ;
- le suivi des activités, notifications et progression ;
- un référentiel académique structuré par université, composante, mention, filière et niveau.

> **Idée centrale :** aider un étudiant à passer de « je cherche » à « je comprends », puis à « je pratique » et « je progresse ».

---

## 1. Ce que Gasy Mahay apporte

### Ressources académiques

La bibliothèque permet de retrouver des annales, corrigés, fiches et cours classés selon le référentiel académique.

Le dépôt d'un document passe par un processus de validation avant sa publication. Le système peut également analyser le document déposé afin d'aider à identifier automatiquement son type et sa matière.

### Apprentissage actif

Le projet ne se limite pas à afficher des documents. Les ressources peuvent servir de point de départ pour :

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

Le projet inclut également :

- notifications internes ;
- rappel d'inactivité après plusieurs jours sans utilisation ;
- suivi de progression ;
- défis et gamification ;
- révisions adaptatives ;
- historique des quiz et activités.

Les nouveaux comptes étudiants disposent d'un **essai gratuit de 60 jours** pour les fonctionnalités Premium prévues par le projet.

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

Le projet peut fonctionner avec :

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
- interfaces responsive pour ordinateur et mobile.

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

Le référentiel structure progressivement :

~~~text
Université
   ↓
Composante / Faculté
   ↓
Mention
   ↓
Filière / parcours
   ↓
Niveau
~~~

Le projet évite autant que possible de déduire automatiquement une classification académique lorsqu'elle est ambiguë.

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
SMTP_HOTE=
SMTP_PORT=587
SMTP_UTILISATEUR=
SMTP_MOT_DE_PASSE=
SMTP_FROM_EMAIL=
~~~

### Administration

~~~text
ADMIN_PHONE=
ADMIN_INITIAL_PASSWORD=
~~~

Ne committez jamais un fichier .env réel ou un secret.

---

## 10. Tests et qualité

La CI du projet contrôle plusieurs niveaux de qualité :

1. validation du graphe Alembic ;
2. compilation Python de l'application et des tests ;
3. vérification du contrat de déploiement Render ;
4. exécution des tests automatisés ;
5. smoke test PostgreSQL avec migrations et démarrage réel.

Pour reproduire les contrôles localement :

~~~powershell
python scripts/verify_migrations.py
python -m compileall -q app tests
python scripts/verify_deployment_contract.py
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

Gasy Mahay cherche à aider l'étudiant à comprendre et pratiquer plutôt qu'à simplement consommer du contenu.

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
4. vérifier la compilation ;
5. vérifier les migrations si le schéma change ;
6. vérifier le comportement mobile si l'interface est modifiée.

Une fonctionnalité n'est considérée comme terminée que lorsqu'elle est cohérente avec le reste du parcours.

---

## 14. Vision

Gasy Mahay veut progressivement devenir un espace numérique dans lequel un étudiant peut :

- trouver une ressource fiable ;
- pratiquer ;
- comprendre ses erreurs ;
- demander de l'aide ;
- travailler avec d'autres ;
- suivre sa progression ;
- contribuer à la communauté.

> **Trouver. Comprendre. Pratiquer. Progresser. Partager.**

**Gasy Mahay — construire ensemble un espace d'apprentissage pour Madagascar.**
