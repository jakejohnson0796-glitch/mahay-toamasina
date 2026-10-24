# TODO — Feuille de route MITARIDALA

**Mise à jour : 23 octobre 2026**  
**Référence :** branche principale après les améliorations des fiches de révision, de la file IA et de l’interface globale.

Ce document est le backlog de référence du dépôt. Les cases cochées correspondent à des travaux déjà intégrés et couverts par les contrôles indiqués. Les cases ouvertes décrivent des améliorations à réaliser ou à approfondir ; elles ne signifient pas automatiquement qu’une régression est actuellement observée.

## 1. Livré et vérifié

- [x] Génération asynchrone des fiches de révision depuis les documents de cours approuvés, avec accès depuis le hub d’apprentissage.
- [x] Génération de fiches individuelles après une séance de classe virtuelle, avec téléchargement PDF et DOCX et contrôle d’accès côté serveur.
- [x] Amélioration du suivi des tâches IA : PostgreSQL reste la source durable, avec voie de récupération lorsque la notification Redis ne suffit pas.
- [x] Clarification des états et actions liés aux fiches de révision pour éviter de confondre une fiche en attente avec une fiche téléchargeable.
- [x] Ajout d’une couche globale de finition visuelle après les styles métier ; harmonisation des contrôles, du focus clavier, des états, du mode sombre et des préférences de mouvement réduit.
- [x] Smoke test responsive sur sept familles de pages, onze largeurs d’écran de 265 à 1440 px et thèmes clair/sombre.
- [x] Couverture navigateur des principaux contrats du rendu IA, du sélecteur de langue, de la hiérarchie des cercles et de la voix du Tuteur.
- [x] CI avec tests applicatifs isolés par fichier et job PostgreSQL dédié aux migrations et au démarrage.
- [x] Possibilité pour l’administration de corriger les métadonnées d’un document, avec revalidation des éléments pédagogiques concernés.

**Références de livraison :** PR [#247](https://github.com/jakejohnson0796-glitch/mahay-toamasina/pull/247), [#248](https://github.com/jakejohnson0796-glitch/mahay-toamasina/pull/248) et [#249](https://github.com/jakejohnson0796-glitch/mahay-toamasina/pull/249). La dernière amélioration globale d’interface correspond au commit 07c8dd117bd26d1528af1c8ffd07c7329f09b3d8.

## 2. Priorité P0 — Fiabilité des parcours critiques

Ces tâches doivent passer avant les nouvelles fonctionnalités ambitieuses.

- [ ] **Ajouter un scénario d’intégration complet pour les fiches de cours.** Dans un environnement PostgreSQL de test, couvrir : dépôt du document → approbation administrative → création/idempotence de la tâche → traitement par le worker → état visible dans l’interface → téléchargement PDF et DOCX.
- [ ] **Étendre ce scénario aux cas limites de sécurité et de reprise.** Vérifier qu’un document en attente ou rejeté ne produit pas de fiche visible, qu’un autre étudiant ne peut pas télécharger une fiche non autorisée, que des tâches doublonnées ne créent pas de résultats incohérents et que les métadonnées modifiées invalident la bonne fiche.
- [ ] **Auditer la visibilité opérationnelle de la file IA.** Vérifier que les diagnostics permettent de repérer une tâche trop ancienne, ses tentatives, son dernier état et une erreur exploitable sans exposer de secrets ; compléter l’interface ou les alertes là où il manque une information.
- [ ] **Standardiser le contrôle après déploiement.** Vérifier les endpoints /health et /ready, les migrations, le démarrage du worker, les erreurs récentes et le téléchargement d’une fiche depuis un vrai navigateur ; consigner le SHA déployé et garder le commit de retour arrière disponible.
- [ ] **Stabiliser les scénarios de vérification IA qui échouent à juste titre.** Construire des tests déterministes pour séparer une erreur réelle de correction, une sortie JSON invalide, des choix de quiz identiques et un seuil de confiance trop strict. Ne pas masquer une erreur pédagogique pour faire passer le test.
- [ ] **Valider en CI les fiches documentaires personnalisées par étudiant.** Vérifier que les priorités viennent uniquement des quiz, progressions et échanges du compte connecté, que la fiche source commune ne change pas et que l'affichage ainsi que les exports PDF/DOCX contiennent le même plan personnalisé.

## 3. Priorité P1 — Qualité pédagogique, mobile et cohérence des données

- [ ] **Créer une matrice de régression du rendu scientifique.** Inclure mathématiques, physique, chimie, informatique et comptabilité : fractions, racines, exposants, matrices, unités, réactions chimiques, tableaux et écritures comptables. Tester le LaTeX brut, les délimiteurs mal formés, les retours à la ligne et les textes mêlant explications et formules.
- [ ] **Élargir les tests navigateur de parcours complets.** Couvrir connexion, recherche, dépôt/modération, accès à une fiche, quiz/correction, Tuteur IA, cercles/chat et classe virtuelle sur des largeurs mobiles et de bureau. Vérifier aussi les actions tactiles et les libellés des boutons.
- [ ] **Faire une revue fonctionnelle du jeu cérébral.** Contrôler que les illustrations correspondent au thème de la question, que les animations ne masquent pas la consigne, que la pause et le choix de réduire les mouvements fonctionnent et que le jeu reste utilisable au clavier et sur petit écran.
- [ ] **Recalculer l’audit du référentiel académique et des cercles sans offre active.** Classer les cas (données de référentiel manquantes, offre ancienne, cercle volontairement communautaire) avant toute désactivation en masse ; privilégier un rapport de revue et une validation humaine.
- [ ] **Valider le parcours complet OTP par e-mail.** Tester configuration, saisie du code, expiration, usage unique, limite de tentatives, erreur d’adresse ou SMTP indisponible et récupération utilisateur, sans recourir aux SMS payants.
- [ ] **Vérifier la cohérence de la localisation.** Pour chaque page principale, contrôler la langue choisie, les messages d’erreur, les menus, les états vides et les dialogues. Conserver en français les éléments du référentiel qui doivent rester officiels.

## 4. Priorité P2 — Accessibilité, performances et exploitation

- [ ] **Faire une passe d’accessibilité.** Contraste des thèmes clair/sombre, focus visible, ordre clavier, noms accessibles, annonces de statut, zoom et mode de contraste renforcé.
- [ ] **Mesurer les performances sur mobile.** Examiner le poids CSS/JavaScript, les bibliothèques du rendu IA, les images du jeu cérébral, les requêtes répétées et le temps d’affichage des pages les plus fréquentées avant d’optimiser.
- [ ] **Répéter une restauration de sauvegarde hors production.** Documenter la restauration PostgreSQL, la vérification des fichiers documentaires et les contrôles de cohérence avant de considérer le plan de reprise comme validé.
- [ ] **Éviter les régressions de documentation.** Faire correspondre le README, le fichier .env.example, la configuration Render et la checklist de release ; toute variable retirée ou renommée doit être documentée.
- [ ] **Organiser une revue périodique des dépendances.** Mettre à jour avec tests, vérifier les changements incompatibles et conserver un chemin de retour arrière plutôt que de mettre à jour toutes les dépendances sans validation.

## Nouveau chantier structurant — collège, lycée et université

Le cahier des charges technique est consigné dans [docs/extension-college-lycee-universite.md](docs/extension-college-lycee-universite.md). Ce chantier est une extension majeure du référentiel, pas une simple option du formulaire.

- [ ] **Lot A — Référentiel scolaire sourcé et versionné.** Créer les tables niveaux, séries/options, matières/programmes et établissements; importer d'abord les classes et séries explicitement documentées par le ministère; rendre l'import idempotent et conserver la source, l'année de référence et le statut de vérification.
- [ ] **Lot A — Parcours d'inscription adapté.** Proposer élève/étudiant, professeur/enseignant ou sponsor, puis collège/lycée/université. L'inscription collège/lycée ne doit plus demander une université; le parcours universitaire actuel doit rester intact.
- [ ] **Lot B — Demandes de profil enseignant.** Enregistrer une demande et sa portée d'enseignement sans attribuer automatiquement le rôle PROFESSEUR. Ajouter le traitement admin et la trace de décision avant d'ouvrir les outils réservés.
- [ ] **Lot C — Documents multi-référentiels.** Classer les documents scolaires sans fausse filière universitaire; adapter upload, filtres, modération, détails et téléchargements privés avant de rendre `Document.filiere_id` nullable.
- [ ] **Lot C — Cercles collège/lycée.** Ajouter les cercles nationaux par classe/série et les cercles locaux par établissement, sans collision avec les identifiants et index des cercles universitaires.
- [ ] **Lot D — Apprentissage par programme.** Relier matières, quiz, fiches de révision et Tuteur IA au niveau / à la série appropriés, avec tests de qualité et sans mélanger les résultats entre comptes.
- [ ] **Lot E — Validation avant mise en ligne.** Tests de migration SQLite et PostgreSQL, tests de sécurité document/cercle, tests navigateur pour chaque cycle, vérification des sources du catalogue, CI verte, puis contrôle santé et parcours après déploiement.

**Règle de données :** ne pas prétendre que le catalogue technique/professionnel est exhaustif tant qu'il n'a pas été comparé aux sources officielles du ministère compétent. Une donnée ambiguë reste « à vérifier » au lieu d'être devinée.

## 5. Ordre recommandé pour la prochaine itération

1. Scénario PostgreSQL de bout en bout pour une fiche de cours, y compris les contrôles d’accès et les formats exportés.
2. Diagnostic des tâches IA anciennes et validation post-déploiement reproductible.
3. Matrice de régression du rendu mathématique et de la qualité des quiz.
4. Conception puis implémentation progressive du référentiel collège/lycée et du profil d'inscription (cahier des charges lié ci-dessus), sans casser l'université existante.
5. Parcours navigateur mobile sur les fonctions les plus utilisées.
6. Revue du référentiel académique, du jeu cérébral et de l’accessibilité.

## 6. Critères de clôture d’une tâche

Une tâche ne passe à « terminée » que lorsque :

- [ ] les tests liés au changement passent localement et en CI ;
- [ ] les migrations, si présentes, peuvent être appliquées deux fois sans effet indésirable et le smoke PostgreSQL passe ;
- [ ] les contrôles d’autorisation sont réalisés côté serveur lorsque des données privées sont impliquées ;
- [ ] l’interface reste lisible en petit écran et dans les thèmes pris en charge ;
- [ ] README, TODO et configuration sont mis à jour si leur contenu devient obsolète ;
- [ ] la CI est verte avant toute fusion ou tout déploiement ;
- [ ] après un déploiement, les contrôles de santé, les logs et le parcours modifié sont vérifiés.

> **Règle de livraison :** aucun changement applicatif ne doit être fusionné ou déployé avec une CI rouge. Pour les changements documentaires, exécuter également la CI avant fusion afin de s’assurer que les liens et les consignes restent cohérents avec le dépôt.
