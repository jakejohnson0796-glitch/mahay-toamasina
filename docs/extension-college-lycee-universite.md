# Extension nationale de MITARIDALA : collège, lycée et université

**Statut : conception technique / plan d'implémentation.** Ce document ne signifie pas que les nouvelles fonctions sont déjà activées. Il sert de contrat avant les changements de schéma et d'interface.

## 1. Objectif produit

À l'arrivée sur MITARIDALA, chaque personne doit pouvoir indiquer son profil puis son parcours réel :

1. **Je suis élève / étudiant** ou **Je suis professeur / enseignant**.
2. **Mon cycle** : collège, lycée ou université / enseignement supérieur.
3. Le niveau réel : 6e, 5e, 4e, 3e, Seconde, Première, Terminale, ou L1–D3 pour l'université.
4. Le cas échéant, la série / option / filière et l'établissement. Un élève sans série définie ne doit pas être obligé de choisir une valeur inventée.
5. Les ressources, quiz, fiches, cercles et cours visibles doivent se caler sur ce profil tout en permettant la recherche de ressources nationales pertinentes.

Ce parcours doit être mobile, accessible, explicite et modifiable dans le profil. Les utilisateurs actuels ne doivent pas perdre leurs informations ni être forcés à recommencer l'inscription.

## 2. Décision de sécurité fondamentale : profil ≠ autorisation

Le choix « professeur » dans un formulaire public est une **demande de profil**, pas une attribution automatique du rôle technique `PROFESSEUR`. Les autorisations actuelles de MITARIDALA reposent sur `Utilisateur.role`; il faut conserver ce mécanisme.

- Un compte demandant à enseigner est enregistré avec `profil_souhaite=professeur` et un statut de validation `en_attente`.
- Les fonctions privilégiées (créer/administrer une classe virtuelle, publier au nom d'un établissement, gérer des élèves) restent bloquées jusqu'à approbation administrative.
- L'approbation, le refus, l'auteur de la décision et la date sont historisés. Un utilisateur ne peut ni envoyer `role=admin` ni s'approuver lui-même via une requête manipulée.
- Les cycles enseignés sont stockés dans une table relationnelle distincte et plusieurs cycles peuvent être déclarés. La granularité classe/série/matière et les justificatifs privés restent une étape suivante ; une déclaration de cycle ne constitue pas une autorisation.
- Les profils déjà existants restent valides. Le profil universitaire actuel est conservé et les nouveaux champs scolaires restent nuls jusqu'à ce que la personne complète son profil.

## 3. Référentiel scolaire : données versionnées et sourcées

Ne pas coder tout le système scolaire en conditions `if/else` ou dans une liste JavaScript. Les classes, séries, matières, options, filières techniques et établissements doivent être des données consultables, administrables et historisées.

### Tables proposées

| Table | Responsabilité |
|---|---|
| `referentielscolaire` | Version du catalogue, année scolaire, source officielle, statut de validation et dates d'effet. |
| `niveauscolaire` | Code stable et libellé d'une classe (6E…3E, 2NDE, 1ERE, TERM), cycle et ordre d'affichage. |
| `optionscolaire` | Séries générales et options, ou filières de l'enseignement technique/professionnel, associées à un niveau et à une version du référentiel. |
| `matierescolaire` | Matières normalisées, libellé français et, si validé, libellé malagasy. |
| `programmematierescolaire` | Association niveau / série-option / matière, caractère obligatoire ou facultatif, année et source. |
| `etablissementscolaire` | Collège, lycée, établissement mixte ou établissement technique : nom, statut public/privé, commune, district, région, source et état de vérification. |
| `cycleenseigne` | Cycles déclarés par un candidat professeur (collège, lycée, université), une ligne par compte et cycle ; ne donne aucun droit sans validation administrative. |
| `demandeverificationenseignant` | Demande, portée d'enseignement, pièces facultatives privées, statut, décision et audit. |

Les codes constituent des identifiants de données ; les libellés peuvent changer sans casser les comptes ou liens. Utiliser des contraintes d'unicité et des clés étrangères, des index pour les recherches, une pagination côté serveur, et des champs `est_actif` / `valide_a_partir_de` / `valide_jusqua` pour ne pas supprimer l'historique.

### Premier inventaire à vérifier

Le Ministère de l'Éducation nationale publie une répartition annuelle par classe, notamment de 6e à 3e et des classes du lycée. Sa page de lycée mentionne les parcours de Seconde à Terminale et le site officiel expose des répartitions pour les séries A, C, D, L, OSE et S. Cet inventaire est un **point de départ**, pas une preuve que chaque série est proposée dans chaque établissement ou reste ouverte partout.

- Programmes officiels par classe : https://www.education.gov.mg/repartition-annuelle-du-programme-scolaire/
- Système éducatif — lycée : https://www.education.gov.mg/systeme-educatif/lycee/
- Enseignement supérieur et établissements habilités : https://www.mesupres.gov.mg/etablissements
- Portail officiel MESUPRES : https://mesupres.gov.mg/

Ne pas confondre le catalogue de l'enseignement général avec les parcours techniques et professionnels. Ceux-ci demandent un inventaire sourcé auprès du ministère compétent et une validation humaine. Une option dont la source ou l'actualité n'est pas vérifiée doit être marquée **à vérifier** et ne doit pas apparaître comme « officielle et actuelle » dans le formulaire public.

### Première tranche déjà ajoutée sur la branche du chantier

Le formulaire permet maintenant à un candidat professeur de choisir un cycle principal et de déclarer d'autres cycles. La table `cycleenseigne` enregistre ces déclarations séparément, avec une contrainte d'unicité par utilisateur et cycle ; la migration reprend aussi le cycle principal des demandes enseignantes déjà enregistrées. Le compte conserve le rôle `ETUDIANT` tant que l'administrateur n'a pas validé la demande. Cette étape ne remplace pas encore une affectation détaillée par classe, série, matière et établissement : ce niveau doit rester dans la feuille de route et être validé avant de restreindre les fonctions professorales.

## 4. Parcours d'inscription cible

### Étape 1 — Qui êtes-vous ?

Choix visuels, sans ambiguïté :
- Élève / étudiant ;
- Professeur / enseignant ;
- Répétiteur / sponsor, si cette catégorie commerciale est conservée.

### Étape 2 — Votre cycle

- Collège : 6e, 5e, 4e, 3e ;
- Lycée : Seconde, Première, Terminale, puis série / option proposée pour ce niveau ;
- Université : parcours universitaire existant (université → composante → mention → niveau → parcours/filière).

La liste affichée doit provenir du backend. Les champs dépendants sont rechargés lorsqu'un choix change et les champs devenus incompatibles sont effacés, pas seulement masqués.

### Étape 3 — Établissement et options

- Recherche d'établissement par région, district, commune et nom, avec possibilité de choisir « non répertorié ».
- Le choix d'établissement ne doit pas être obligatoire tant que son catalogue n'est pas assez complet.
- N'afficher que les séries/options compatibles avec le niveau et la version du programme choisis.
- Le professeur déclare les niveaux et matières enseignés ; plusieurs sélections sont permises et soumises à validation.

### Étape 4 — Confirmation et espace adapté

Une page de confirmation résume le parcours. Les pages d'accueil, de recherche et de création de cercles utilisent ce contexte pour préremplir les filtres ; l'utilisateur peut toujours élargir sa recherche au catalogue national.

## 5. Cercles, documents et cours : même logique de ciblage

Le modèle actuel des cercles et documents est historiquement centré sur le référentiel universitaire. L'ajout de collèges/lycées ne doit pas détourner les champs universitaires pour y stocker une classe scolaire.

### Ciblage pédagogique explicite

Chaque ressource ou cercle doit avoir une portée claire :
- `universitaire` : utilise les relations existantes université / composante / mention / filière / niveau ;
- `scolaire` : référence le niveau scolaire, la série/option si nécessaire, la matière et éventuellement l'établissement ;
- `national` / `transversal` : contenu explicitement partagé entre plusieurs parcours.

Les relations doivent être contrôlées côté serveur, pas seulement par les listes HTML. Une fiche scolaire ne doit jamais avoir besoin d'une fausse filière universitaire pour pouvoir être enregistrée. À terme, `Document.filiere_id` doit être nullable avec une contrainte de cohérence garantissant qu'un document a une cible universitaire ou scolaire valide ; cette migration exige un audit préalable de toutes les requêtes et des écrans d'administration.

Pour les cercles :
- un cercle national scolaire peut réunir les élèves d'un même niveau/série sans les limiter à leur établissement ;
- un cercle local peut être lié à un établissement ;
- la portée, le niveau, la série et le caractère public/privé entrent dans la règle d'unicité, sans réutiliser l'index d'un cercle universitaire ;
- un utilisateur ne peut rejoindre un cercle fermé sans autorisation, et la modification de son profil ne doit pas lui donner accès rétroactivement à des documents réservés.

Pour les documents :
- dépôt avec cycle, niveau, matière, type (cours, annale, corrigé, fiche) et année ; série/option et établissement facultatifs selon le cas ;
- validation administrative identique à celle des documents universitaires ;
- téléchargements privés vérifiés côté serveur, tout particulièrement pour les documents de cercle ou de classe ;
- fiches de révision, quiz et Tuteur IA héritent de la cible réelle du cours, pas d'une valeur globale ou d'un niveau inventé.

## 6. Migration sans régression

1. Inspecter les données actuelles et relever les comptes, cercles, documents, classes virtuelles et filtres qui supposent une filière universitaire obligatoire.
2. Ajouter les nouvelles tables en tables séparées et les nouveaux champs utilisateur comme nullable. Ne pas réécrire le profil universitaire existant.
3. Importer les classes officielles et les options confirmées avec source, année de référence et état de validation. Rendre l'import idempotent (relançable sans doublons).
4. Ajouter les liens scolaires aux documents et cercles, puis convertir le parcours de dépôt et les requêtes une zone à la fois.
5. Ne rendre `filiere_id` nullable qu'après adaptation et tests de toutes les requêtes, formulaires, notifications, exports et vues admin.
6. Fournir un rapport de migration : nombre de profils migrés, documents sans cible cohérente, cercles en conflit, et options dont la source nécessite une validation manuelle.
7. Backfill uniquement quand la relation est certaine. En cas d'ambiguïté, conserver `NULL` et faire apparaître une tâche de revue, jamais deviner une série ou une filière.

Les migrations doivent fonctionner sur SQLite de test et PostgreSQL de production, respecter la chaîne Alembic existante et être testées sur une copie / une base de test avant toute application sur Supabase production.

## 7. Sécurité, vie privée et mineurs

- Garder l'accès aux documents téléchargeables derrière une vérification serveur de session, d'approbation et de portée.
- Ne jamais se fier à `user_metadata` ou à des champs envoyés par le navigateur pour accorder le rôle enseignant.
- Les justificatifs de professeur, lorsqu'ils sont demandés, restent privés, avec accès limité aux administrateurs autorisés et durée de conservation définie.
- Minimiser les renseignements de profil d'élèves mineurs : ne pas rendre publique la date de naissance, les coordonnées ou l'établissement exact par défaut.
- Modération et signalement adaptés à des utilisateurs mineurs ; paramètres de confidentialité des cercles explicités.
- RLS Supabase uniquement si les tables sont exposées via l'API Data : sinon l'accès passe par l'application backend, mais les contrôles d'autorisation du serveur restent obligatoires.

## 8. Tests d'acceptation obligatoires

### Inscription et profils
- Chaque combinaison valide (élève collège, élève lycée, étudiant universitaire, enseignant des trois cycles) peut compléter son profil.
- Une série incompatible ou inactive est refusée côté serveur ; une valeur modifiée dans le navigateur ne contourne pas la validation.
- Un compte demandant le profil enseignant ne reçoit jamais automatiquement le rôle `PROFESSEUR` ou `ADMIN`.
- Les comptes universitaires existants se connectent sans modification et conservent leurs rattachements.

### Données et ressources
- L'import du référentiel peut être relancé sans doublons.
- Un document scolaire est classable sans fausse filière universitaire.
- Les documents en attente ou rejetés ne sont pas téléchargeables ; un autre compte ne peut pas télécharger une ressource privée par modification d'ID.
- Un cercle scolaire ne rentre pas en conflit avec un cercle universitaire ayant un niveau de même libellé.
- Les filtres et exports couvrent niveau, série/option, matière, année et type, en français et en malagasy là où les libellés ont été vérifiés.

### Livraison
- Tests unitaires et d'intégration, migration SQLite, smoke PostgreSQL, contrôle d'accès et tests navigateur mobile.
- CI verte avant fusion. Après déploiement seulement : migration vérifiée, `/health` et `/ready`, journaux, inscription des trois cycles, recherche et téléchargement d'un document autorisé.
- Ne pas déployer les données scolaires incomplètes en les présentant comme exhaustives.

## 9. Ordre de réalisation recommandé

**Lot A — Référentiel et profil** : tables, import versionné, sélecteur de profil, niveaux collège/lycée et préservation du parcours universitaire.

**Lot B — Professeurs** : demandes de validation, écran administratif de décision, niveaux/matières enseignés multiples, puis activation des permissions après approbation.

**Lot C — Documents et cercles** : portée scolaire, migration de `filiere_id`, recherche, dépôt, modération, sécurité et documents téléchargeables.

**Lot D — Apprentissage** : programmes matière par matière, quiz et fiches alignés sur le programme, Tuteur IA informé du niveau sans surinterpréter les contenus, progression et révisions distinctes par utilisateur.

**Lot E — Assurance qualité** : tests complets, performance sur mobile, accessibilité, vérification des sources du référentiel, CI, puis déploiement contrôlé.

La règle principale : **la base de données décrit fidèlement les programmes réels ; l'IA et l'interface consomment ce référentiel, elles ne l'inventent pas.**
