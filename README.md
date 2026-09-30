# Gasy Mahay — plateforme d'apprentissage pour les étudiants de Madagascar

Gasy Mahay est un projet éducatif numérique construit autour d'une idée simple :

> **Un étudiant ne devrait pas être obligé d'apprendre seul, ni perdre des heures à chercher la bonne ressource au mauvais endroit.**

La plateforme réunit dans un même écosystème les ressources académiques, l'entraide entre étudiants, les outils de pratique et l'accompagnement assisté par IA.

Le projet est pensé pour **Madagascar** : le lancement initial a servi de point de départ, mais la vision est nationale.

---

## Notre histoire

Gasy Mahay part d'un constat concret : dans la vie universitaire, une ressource utile peut se trouver dans un document, une conversation, un groupe d'étudiants ou auprès d'une personne qui connaît déjà la réponse.

Le problème n'est donc pas seulement de produire plus de contenu. Il faut aussi pouvoir :

- retrouver rapidement une ressource ;
- pratiquer au lieu de seulement lire ;
- demander une explication ;
- travailler avec d'autres étudiants ;
- identifier les notions qui restent difficiles ;
- revenir dessus jusqu'à mieux les maîtriser.

C'est cette logique qui guide l'évolution de Gasy Mahay.

Le premier lancement avait une portée initiale. La plateforme évolue désormais avec une ambition plus large : **structurer progressivement un espace d'apprentissage numérique pour les étudiants de Madagascar**.

---

## Pourquoi Gasy Mahay existe

Le projet cherche à rapprocher quatre éléments qui restent souvent séparés :

1. **Le savoir** — documents, cours, annales, fiches et référentiel académique.
2. **La pratique** — quiz, exercices, corrections et révisions.
3. **L'humain** — cercles d'étude et collaboration entre étudiants.
4. **L'accompagnement** — Tuteur IA et outils adaptatifs.

L'objectif n'est pas de remplacer l'université, les enseignants ou le travail personnel.

L'objectif est de créer **un outil d'appui** qui aide l'étudiant à mieux utiliser ce qu'il a déjà, à identifier ce qui lui manque et à continuer à progresser.

---

## Ce qui est actuellement construit

### Parcours étudiant

- Inscription et connexion
- Parcours de démarrage guidé sur plusieurs jours
- Tableau de bord étudiant
- Notifications
- Suivi des activités et de la progression
- Révisions adaptatives
- Gamification et défis

### Ressources académiques

- Bibliothèque de documents
- Classement par université, mention, niveau et filière
- Dépôt de ressources avec modération
- Référentiel académique national en cours de structuration
- Références documentaires neutres de type `MG-DEG-2025-0147`

### Apprentissage assisté par IA

- **Quiz IA** générés à partir des ressources
- **Tuteur IA** pour expliquer, donner des exemples, proposer des exercices et corriger
- Personnalisation à partir de la progression de l'étudiant
- Révisions ciblées sur les notions faibles
- Validation locale des sorties avant affichage
- Vérification multi-modèles lorsque le scénario le demande

### IA multi-modèles

L'architecture actuelle peut faire intervenir plusieurs modèles autour d'une même réponse :

```text
Étudiant
   ↓
Génération principale
   ↓
Critique / vérification
   ↓
Analyse des désaccords et erreurs
   ↓
Arbitrage si nécessaire
   ↓
Une réponse finale pour l'étudiant
```

La logique est de faire travailler les modèles comme un ensemble coopératif plutôt que d'exposer l'utilisateur à plusieurs réponses contradictoires.

La configuration actuelle prévoit notamment un modèle principal Groq, un modèle critique Qwen et un contrôle Gemini optionnel. Les modèles réellement utilisés dépendent de la configuration de l'environnement et de leur disponibilité.

### Collaboration

- Cercles d'étude
- Chat temps réel WebSocket
- Historisation des messages
- Classe virtuelle avec vidéo, chat et tableau blanc
- Espaces de travail pensés pour les usages étudiants

---

## L'expérience que nous voulons créer

Le parcours cible est simple :

```text
Je cherche
   ↓
Je trouve
   ↓
Je pratique
   ↓
Je me trompe
   ↓
Je comprends
   ↓
Je révise
   ↓
Je progresse
   ↓
J'aide à mon tour
```

Une erreur ne doit pas être seulement enregistrée comme un mauvais résultat.

Elle doit pouvoir devenir un signal pour la suite : une notion à revoir, une explication à demander, un exercice à refaire ou un quiz à cibler.

---

## Une plateforme pensée pour les étudiants, mais soutenue par un écosystème

Le principe économique du projet est de chercher un équilibre entre **accessibilité pour les étudiants** et **soutien de partenaires**.

Les sponsors et partenaires peuvent contribuer au développement de :

- l'infrastructure ;
- l'hébergement ;
- les outils d'intelligence artificielle ;
- la structuration et la modération des ressources ;
- les fonctionnalités pédagogiques ;
- l'accès et la qualité du service à mesure que la communauté grandit.

L'ambition est de construire des partenariats utiles, avec une séparation claire entre le soutien au projet et l'expérience pédagogique proposée aux étudiants.

---

## Une ambition nationale

Gasy Mahay est désormais pensé à l'échelle de Madagascar.

La plateforme travaille autour d'un référentiel pouvant regrouper plusieurs universités publiques, leurs mentions, niveaux et filières, avec une intégration progressive des données pouvant être vérifiées et maintenues.

L'approche est volontairement progressive :

**structurer → vérifier → publier → mesurer → améliorer → élargir**

Cette méthode permet de grandir sans transformer le site en simple catalogue de pages ou de données difficiles à maintenir.

---

## Architecture technique

Le projet reste volontairement léger et principalement Python.

### Backend

- **FastAPI**
- **SQLModel / SQLAlchemy**
- **Jinja2**
- Sessions serveur
- WebSocket natif FastAPI
- Services métier Python séparés par domaine

### Données

- **SQLite** pour un démarrage local simple
- **PostgreSQL / Supabase** pour le déploiement
- Stockage documentaire local ou Supabase Storage selon la configuration
- File de tâches IA durable côté base de données

### IA

- Groq pour la génération
- Modèle critique Qwen configurable
- Gemini optionnel pour la vérification
- Validation de schémas et contrôles locaux
- Mémoire / télémétrie des erreurs du système IA
- File de traitement IA et reprise en cas de notification perdue

### Frontend

- HTML rendu côté serveur
- Jinja2
- CSS maison
- JavaScript vanilla lorsque nécessaire
- PWA installable

---

## Stockage et file IA

Le traitement IA long est séparé du chemin HTTP utilisateur autant que possible.

Flux simplifié :

```text
Requête utilisateur
       ↓
PostgreSQL : tâche durable
       ↓
Redis / Valkey : notification
       ↓
Worker IA embarqué
       ↓
Traitement
       ↓
PostgreSQL : état final
```

La base de données reste la source durable : si une notification Redis est perdue, le système peut retrouver la tâche à traiter.

---

## Démarrer en local (Windows / VS Code)

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Sans configuration distante, le projet peut fonctionner avec :

- SQLite
- stockage local des fichiers
- variables d'environnement locales
- fonctionnalités IA activées seulement lorsque leurs clés sont configurées

---

## Configurer Supabase

1. Créer un projet Supabase.
2. Renseigner `DATABASE_URL` avec l'URI PostgreSQL.
3. Créer un bucket de stockage pour les documents si le stockage Supabase est utilisé.
4. Renseigner `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` et `SUPABASE_BUCKET`.
5. Redémarrer l'application.

La clé `service_role` doit rester côté serveur et ne doit jamais être exposée au navigateur.

---

## Configurer l'IA

La génération de quiz et les fonctions d'accompagnement IA utilisent les variables d'environnement prévues dans `.env.example`.

Variables principales :

```text
GROQ_API_KEY=
GROQ_MODEL=
GROQ_CRITIC_MODEL=
AI_ENSEMBLE_ENABLED=
AI_ENSEMBLE_USE_GEMINI=
GEMINI_API_KEY=
GEMINI_MODEL=
```

Les modèles restent configurables afin de pouvoir faire évoluer l'architecture sans modifier le parcours étudiant.

---

## Modération et confiance

Gasy Mahay cherche à construire un environnement utile sans sacrifier la confiance.

Les ressources passent par un flux de modération avant publication selon le type de contenu.

Les documents et espaces étudiants sont séparés des outils administratifs, et les contrôles importants sont appliqués côté serveur.

Pour l'IA, la plateforme utilise également des validations locales et des mécanismes de suivi des erreurs afin de pouvoir améliorer la qualité dans le temps.

---

## Feuille de route

### Maintenant

- consolider l'expérience étudiant ;
- améliorer le parcours de démarrage ;
- enrichir le référentiel académique national ;
- continuer à améliorer les quiz, les révisions et le Tuteur IA ;
- mesurer les usages réels et les points de friction.

### Prochaine étape

- renforcer la communauté et les cercles d'étude ;
- améliorer les outils de classe virtuelle ;
- développer les partenariats et le sponsoring ;
- renforcer la qualité et la traçabilité des ressources ;
- poursuivre l'évolution de l'ensemble IA à partir des erreurs observées.

### À plus long terme

- couvrir progressivement davantage de parcours universitaires à Madagascar ;
- renforcer les outils d'apprentissage personnalisé ;
- développer des partenariats avec les acteurs de l'éducation et les entreprises qui souhaitent soutenir les étudiants ;
- construire un écosystème durable autour de l'apprentissage et de l'entraide.

---

## Pour les étudiants

Gasy Mahay veut être un endroit où l'on peut commencer simplement :

**une question, une ressource, un quiz, une erreur, une explication, puis un progrès.**

La plateforme grandira avec ses utilisateurs.

Chaque étudiant qui partage une ressource, participe à un cercle, signale un problème ou utilise régulièrement les outils contribue à rendre l'écosystème plus utile pour les suivants.

---

## Pour les sponsors et partenaires

Le projet est ouvert aux partenariats qui peuvent contribuer de manière concrète à son développement.

Un partenariat peut notamment soutenir :

- l'infrastructure ;
- les services IA ;
- la mise à disposition de ressources ;
- l'accompagnement de communautés étudiantes ;
- des actions ou programmes pédagogiques ;
- la croissance du service à l'échelle nationale.

Le sponsoring n'est pas présenté comme une simple visibilité publicitaire : l'objectif est de relier le soutien du partenaire à une contribution identifiable au projet.

Pour échanger avec l'équipe, utilisez la page **Contact** du site.

---

## Contribuer au projet

Le projet évolue par itérations.

Avant d'ajouter une fonctionnalité, il est utile de vérifier qu'elle répond à un besoin réel, qu'elle reste compatible avec l'expérience mobile et qu'elle ne fragilise pas les fonctions déjà disponibles.

Les contributions peuvent porter sur :

- l'UX et l'interface ;
- les données et le référentiel ;
- les parcours pédagogiques ;
- la qualité des ressources ;
- l'IA et sa validation ;
- la performance ;
- la sécurité ;
- les partenariats et usages étudiants.

---

## Message central

> **Gasy Mahay ne cherche pas seulement à mettre des documents en ligne.**
>
> **Le projet cherche à construire un environnement où les étudiants peuvent trouver, comprendre, pratiquer, s'entraider et progresser.**

**Gasy Mahay — construire ensemble un espace d'apprentissage pour Madagascar.**
