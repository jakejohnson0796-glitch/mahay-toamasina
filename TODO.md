# TODO — Feuille de route MITARIDALA

**Dernière revue : 27 octobre 2026**  
**Référence de sécurité livrée :** commit applicatif 19efd4cf1b06ac35722373784b6325a2b4ebd94e  
**CI correspondante :** [GitHub Actions — résultats sur main](https://github.com/jakejohnson0796-glitch/mahay-toamasina/actions/runs/40558855645)  
**Production :** [service MITARIDALA sur Render](https://dashboard.render.com/web/srv-db9d7q5g1s2s7389bspg)

Ce fichier est le backlog de travail. Les cases cochées indiquent les changements déjà livrés et les vérifications observées. Les cases ouvertes représentent les prochains contrôles ou améliorations ; elles ne signifient pas nécessairement qu'un défaut est actuellement reproduit.

## 1. Livré et vérifié

- [x] **Limites des requêtes HTTP.** Middleware exécuté avant le parsing des formulaires : 2 MiB par défaut, 21 MiB pour un document ou devoir unique, 102 MiB pour le dépôt multiple prévu et 6 MiB pour une photo de profil. Les limites incluent une marge multipart et complètent les limites de taille des fichiers.
- [x] **Lectures de fichiers bornées.** Lecture limitée à la taille maximale autorisée plus un octet afin de détecter un dépassement sans charger un fichier arbitrairement volumineux en mémoire.
- [x] **Mode de production plus strict.** Sur Render, la configuration doit être explicitement en production ; le démarrage refuse la clé de session de démonstration.
- [x] **Helper commun d'adresse IP anti-abus.** Les routes sensibles ont été regroupées autour d'une fonction de validation d'adresse IP. La confiance accordée aux en-têtes de proxy doit encore être confirmée dans l'environnement réel (voir P0).
- [x] **Tests de régression de sécurité.** Tests des limites du corps HTTP, des en-têtes IP et du garde-fou de configuration.
- [x] **CI complète verte pour le code fusionné.** Les jobs **test** et **postgres-smoke** ont réussi, y compris compilation, vérification du contrat Render, smoke tests navigateur et migrations PostgreSQL rejouées.
- [x] **Déploiement Render du commit applicatif de sécurité.** Déploiement marqué live ; l'application a démarré, les migrations PostgreSQL étaient appliquées et /health a répondu 200 OK.
- [x] **Fiches de révision persistées et personnalisées.** Le carnet source lié au cours ne doit pas être muté par la personnalisation d'un étudiant ; les exports et téléchargements doivent rester soumis aux contrôles d'accès.
- [x] **Documentation actualisée.** Le README décrit les fonctionnalités, l'architecture, le démarrage, la configuration, les contrôles, le déploiement et les limites du catalogue. Ce TODO distingue les travaux livrés des chantiers encore ouverts.

**Historique de la livraison de sécurité :**
- [PR #301](https://github.com/jakejohnson0796-glitch/mahay-toamasina/pull/301)
- [CI de la PR avant fusion](https://github.com/jakejohnson0796-glitch/mahay-toamasina/actions/runs/40556724055)
- [CI du commit fusionné](https://github.com/jakejohnson0796-glitch/mahay-toamasina/actions/runs/40558855645)

## 2. Priorité P0 — Sécurité et fiabilité en production

Ces points passent avant les nouvelles fonctionnalités visibles.

- [ ] **Confirmer la frontière de confiance des IP proxy.** Ne pas considérer un en-tête HTTP tel que CF-Ray ou CF-Connecting-IP comme preuve suffisante à lui seul : un client peut ajouter des en-têtes s'il atteint directement le service. Confirmer quel proxy est réellement devant Render, quels en-têtes il remplace, et quel est le comportement par accès direct au sous-domaine Render. Ajouter un test qui représente cette chaîne réelle ; corriger le helper si l'origine ne peut pas être authentifiée.
- [ ] **Tester les limites HTTP en conditions réalistes.** Couvrir un fichier de taille autorisée, un fichier trop grand, un corps multipart trop grand, un Content-Length mensonger ou absent et un corps transmis en plusieurs fragments. Vérifier une réponse 413 propre, l'absence de traitement partiel et l'absence d'effet de bord sur les formulaires ordinaires.
- [ ] **Verrouiller les téléchargements de documents de bout en bout.** Tester l'accès anonyme, le compte connecté sans permission, le membre autorisé d'un cercle, le non-membre, le document en attente/rejeté, les URL signées expirées et les chemins directs de stockage. Confirmer que les fichiers privés ne sont pas accessibles par une URL publique durable.
- [ ] **Auditer les autorisations sensibles.** Revoir les routes, les API, les WebSockets, les fonctions d'administration, les exports PDF/DOCX et les actions sur les comptes : chaque contrôle doit être fait côté serveur et tester au minimum les rôles non autorisés.
- [ ] **Rendre les tâches IA bloquées visibles.** Exposer dans le diagnostic administratif l'âge de la tâche, le nombre de tentatives, le dernier statut et une erreur exploitable, sans secret ni contenu privé. Tester reprise après redémarrage, doublons, tâche échouée et nouvelle tentative.
- [ ] **Standardiser le contrôle post-déploiement.** Conserver le SHA déployé, vérifier /health et /ready, l'état de la base, les migrations, l'initialisation du référentiel, le worker IA, les journaux récents et au moins un parcours touché depuis un vrai navigateur.
- [ ] **Documenter et tester le retour arrière.** Identifier le dernier déploiement connu comme sain ; vérifier les conséquences d'un retour arrière sur les migrations et les fichiers créés après la release.

## 3. Priorité P1 — Qualité de l'apprentissage

- [ ] **Réduire la répétition des quiz et jeux.** Instrumenter la répétition par compte, document, notion et période ; augmenter la variété des questions et distracteurs ; garder un contrôle pédagogique au lieu de répéter des questions reformulées superficiellement.
- [ ] **Connecter les résultats à la prochaine action pédagogique.** Après un quiz, présenter les notions à retravailler et proposer un parcours court vers la fiche adaptée, le Tuteur IA et un exercice ciblé. Vérifier que l'étudiant, la tentative et le document source restent correctement associés.
- [ ] **Créer une matrice complète LaTeX/KaTeX.** Tester algèbre, fractions, matrices, racines, exposants, limites, intégrales, unités, chimie, tableaux, code et comptabilité ; inclure les formules mêlées à du texte, les retours à la ligne et les délimiteurs invalides. Ne modifier ni le renderer ni les règles scientifiques dans un changement sans rapport.
- [ ] **Durcir les fiches de révision en échec ou en reprise.** Tester document en attente/rejeté, extraction vide, modèle indisponible, limite de fournisseur, doublons de tâches, changement de matière/type et téléchargement par un autre étudiant. Un contenu absent ou incertain doit être signalé plutôt qu'inventé.
- [ ] **Tester les fiches de séance de classe virtuelle.** Vérifier propriétaire, participants, source réelle disponible, personnalisation individuelle et exports PDF/DOCX. Lorsqu'il n'y a ni transcription ni note, la fiche ne doit pas prétendre résumer une séance non documentée.
- [ ] **Achever la matrice des parcours navigateur.** Inscription, connexion, récupération du compte, sélection de langue, recherche, dépôt/modération, téléchargement autorisé, quiz/correction, Tuteur IA, cercles/chat, classe virtuelle, devoirs et fonctions administratives.
- [ ] **Vérifier l'anglais, le français et le malgache sur toutes les vues.** Inclure menus, erreurs, dialogues, états vides, notifications, champs de formulaire et mobile ; garder les libellés officiels du référentiel dans la langue prescrite.

## 4. Priorité P1 — Référentiel, établissements et cercles

Le catalogue collège/lycée/université/ETFP doit rester sourcé et ne pas présenter des données partielles comme exhaustives.

- [ ] **Mettre à jour les sources scolaires officielles.** Contrôler les programmes et répartitions les plus récents disponibles, avec année, URL de preuve et date de vérification. Les documents 2024–2025 ne prouvent pas à eux seuls l'offre scolaire 2026–2027.
- [ ] **Achever la revue nationale ETFP région par région.** Comparer les entrées importées aux sources METFP, repérer doublons et ambiguïtés, et publier un bilan indiquant source, nombre importé, nombre confirmé et éléments restant à vérifier.
- [ ] **Vérifier les offres par établissement et année scolaire.** Distinguer strictement établissement répertorié, filière documentée et offre ouverte cette année. Seules les offres validées par une personne autorisée doivent être visibles comme confirmées.
- [ ] **Tester les profils enseignants multi-cycles.** Collège, lycée et université doivent être sélectionnables sans confondre déclaration et autorisation. Couvrir la demande, les preuves éventuelles, l'approbation administrative et les affectations par classe/série/matière/établissement.
- [ ] **Tester la séparation des cercles scolaires et universitaires.** Vérifier provisionnement idempotent, création, adhésion, filtres matière, héritage de matière dans les documents et archivage prudent des cibles obsolètes. Ne jamais archiver automatiquement un cercle communautaire qui possède des membres ou du contenu important.
- [ ] **Vérifier les API et la page publique de catalogue sur mobile.** Tester filtres, états vides, validation des formulaires, lisibilité, source affichée et exclusion des offres non confirmées.

Références : [docs/extension-college-lycee-universite.md](docs/extension-college-lycee-universite.md), [conception responsive](docs/responsive-design.md).

## 5. Priorité P2 — Accessibilité, performances et exploitation

- [ ] **Faire une passe d'accessibilité.** Contraste clair/sombre, focus visible, ordre clavier, libellés accessibles, annonces des états, zoom, navigation tactile et mode de mouvement réduit.
- [ ] **Mesurer les performances mobiles.** Temps de réponse et d'affichage, poids JavaScript/CSS, images des jeux, requêtes répétées, chargement du tableau de bord et des documents ; optimiser à partir de mesures.
- [ ] **Répéter une restauration de sauvegarde hors production.** Documenter la restauration PostgreSQL, les objets Storage associés et la vérification de cohérence avant de considérer la reprise comme validée.
- [ ] **Ajouter une revue périodique des dépendances.** Vérifier les annonces de sécurité, mettre à jour avec les tests et conserver un chemin de retour arrière ; ne pas mettre à jour en masse sans validation.
- [ ] **Vérifier les notifications et rappels.** S'assurer qu'ils sont utiles, non répétitifs, liés au bon utilisateur et que leur état de lecture est persisté.
- [ ] **Maintenir les documents de référence synchronisés.** README, TODO, .env.example, render.yaml et checklist release doivent utiliser les mêmes noms de variables, endpoints et étapes.

## 6. Ordre conseillé pour la prochaine itération

1. Confirmer la confiance accordée aux adresses IP et tester la limite de taille HTTP en conditions réelles.
2. Compléter les tests d'accès privé aux documents, exports et ressources de cercle.
3. Améliorer la visibilité et la reprise des tâches IA anciennes ou échouées.
4. Ajouter la matrice de régression du renderer scientifique et traiter la répétition des quiz/jeux.
5. Terminer l'exhaustivité vérifiée du catalogue scolaire/ETFP et les parcours navigateur complets.
6. Mesurer l'accessibilité, les performances mobiles et la capacité de restauration.

## 7. Critères de clôture

Une tâche n'est terminée que lorsque :

- [ ] les tests ciblés passent localement et dans la CI ;
- [ ] les migrations, lorsqu'il y en a, sont testées sur PostgreSQL et rejouables sans effet indésirable ;
- [ ] les autorisations privées sont vérifiées côté serveur, y compris par accès direct à l'URL ;
- [ ] l'interface a été vérifiée au clavier, en petit écran et dans les thèmes concernés ;
- [ ] les données du référentiel ont une source et une année vérifiables ;
- [ ] le README et le TODO reflètent le comportement final ;
- [ ] la CI est verte avant toute fusion ou tout déploiement ;
- [ ] après le déploiement, /health, /ready, les logs et le parcours modifié sont vérifiés.

> **Règle de livraison :** ne jamais fusionner ou déployer un changement applicatif avec une CI rouge ou incomplète. Pour un changement documentaire, exécuter aussi la CI afin de détecter des liens cassés et des instructions devenues obsolètes.
