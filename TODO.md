# TODO — MITARIDALA

**Mise à jour : 20 octobre 2026**
**Référence :** feuille de route de travail. Les cases cochées décrivent des éléments présents dans le code et/ou couverts par des tests repérés dans le dépôt ; elles ne signifient pas que chaque scénario a été validé en production.

## Priorité P0 — validation du jeu cérébral avant release

### Fonctionnalités présentes dans le code

- [x] Cinq thèmes : logique, calcul mental, suites, langage et observation.
- [x] Banque locale de questions en français et en malgache.
- [x] Génération assistée par IA avec solution de repli locale si elle échoue ou n’est pas disponible.
- [x] Cinq questions par session et difficulté adaptative.
- [x] Enregistrement des sessions, résultats, corrections et recommandations.
- [x] Illustrations locales : visuel principal, cinq illustrations thématiques, mascotte et trophée.
- [x] Animations de transition et réactions visuelles à la validation.
- [x] Barre de progression et navigation question par question.
- [x] Pause et chronomètre facultatif ; le temps écoulé ne retire pas de points.
- [x] Réglage de réduction des animations et prise en compte de `prefers-reduced-motion`.
- [x] Adaptations CSS pour les écrans mobiles et les petits écrans.
- [x] Contrat de rendu scientifique appliqué aux questions, propositions et corrections du jeu.
- [x] Tests automatisés dédiés à la banque bilingue, à la difficulté, aux sessions, aux illustrations et au rendu des formules.

### Tests restant à réaliser

- [ ] Exécuter toute la CI depuis le commit candidat : migrations, compilation Python, tests et smoke tests PostgreSQL.
- [ ] Tester le parcours complet en navigateur : accueil, sélection de chaque thème, réponse correcte/incorrecte, question suivante, fin de partie, corrections, recommandations et nouvelle partie.
- [ ] Vérifier sur ordinateur, tablette, Android et une largeur mobile très étroite ; confirmer l’absence de débordement horizontal, de texte coupé et de boutons difficiles à toucher.
- [ ] Tester pause/reprise avec et sans chronomètre, rechargement de page, retour depuis un autre onglet et expiration du temps cible.
- [ ] Vérifier le réglage « réduire les animations » et la préférence système, y compris après navigation entre accueil, session et résultat.
- [ ] Contrôler contraste, navigation clavier, focus visible, libellés des boutons, annonce de la progression et retour aux lecteurs d’écran.
- [ ] Simuler l’absence d’une illustration, une erreur de chargement et un réseau lent ; vérifier que le contenu et les réponses restent utilisables.
- [ ] Vérifier chaque banque de questions FR/MG : exactitude du résultat, distracteurs distincts, explication cohérente, niveau annoncé et traduction naturelle.
- [ ] Tester la génération IA avec délai dépassé, quota atteint, clé absente, JSON invalide et banque incomplète ; le repli local doit fonctionner sans exposer d’erreur technique à l’étudiant.
- [ ] Confirmer que le jeu n’affiche aucun diagnostic trompeur sur « l’intelligence » de l’étudiant et que les recommandations restent encourageantes.
- [ ] Faire un smoke test sur une instance de prévisualisation Render, puis vérifier les logs et les endpoints de santé avant toute mise en production.

## Priorité P0 — rendu scientifique fiable dans toute la plateforme

- [x] Moteur commun `app/static/js/rendu_ia.js` pour le Markdown, les expressions mathématiques, la chimie et le code.
- [x] Dépendances navigateur locales prévues pour KaTeX, mhchem, Marked, DOMPurify et Highlight.js.
- [x] Contrat de rendu des formules couvert par des tests automatisés.
- [ ] Tester un corpus représentatif en mathématiques : fractions, racines, puissances, indices, matrices, systèmes, limites, dérivées, intégrales, vecteurs, symboles grecs et expressions longues.
- [ ] Tester physique : unités, notations vectorielles, indices, exposants, conversions et symboles spéciaux.
- [ ] Tester chimie : formules avec indices, ions, charges, états physiques, réactions et flèches d’équilibre.
- [ ] Tester informatique : blocs de code, indentation, caractères d’échappement, exemples HTML/JSON et chaînes contenant des symboles ressemblant à des commandes LaTeX.
- [ ] Tester comptabilité : montants en Ar, séparateurs de milliers, nombres négatifs, tableaux, bilans et comptes en T sans reformater ni altérer les données.
- [ ] Vérifier les délimiteurs absents ou mal formés, les antislashs perdus pendant le transport JSON, le contenu vide, Unicode et les réponses très longues.
- [ ] S’assurer qu’une erreur de rendu ne masque pas le texte source et que la correction automatique ne modifie ni les blocs de code ni les données comptables.
- [ ] Contrôler les débordements horizontaux et la lisibilité des formules sur téléphone, thème clair et thème sombre.
- [ ] Tester l’assainissement DOMPurify avec des sorties malformées et des tentatives d’injection ; aucune sortie IA ne doit être considérée comme HTML fiable par défaut.

## Priorité P1 — qualité pédagogique et expérience étudiante

- [ ] Relire régulièrement les contenus IA générés et le corpus local avec des critères de justesse, clarté, niveau et qualité des corrections.
- [ ] Vérifier que les erreurs d’un quiz peuvent conduire à une révision ciblée sans rupture de parcours entre Quiz IA, Tuteur IA et exercices.
- [ ] Contrôler que les résumés des documents déposés précisent le sujet, le cours concerné et le type de cours, et signalent les métadonnées incertaines.
- [ ] Confirmer qu’un document soumis à modération n’est pas publiquement accessible avant validation.
- [ ] Compléter les traductions françaises/malgaches dans les écrans concernés ; conserver le référentiel académique en français.
- [ ] Tester les parcours sur connexion lente et appareils peu puissants, notamment chargement des images, appels IA et états de chargement.
- [ ] Vérifier que les notifications, rappels, historique et progression évitent les doublons et respectent les autorisations du compte.

## Priorité P1 — sécurité et fiabilité

- [ ] Rejouer les scénarios d’accès interdit entre utilisateurs pour sessions de jeu, documents, quiz, cercles, fichiers et fonctions d’administration.
- [ ] Vérifier CSRF, limitation de débit, expiration de session et reprises après erreur sur les routes modifiant l’état.
- [ ] Vérifier que les secrets de production ne sont ni dans Git ni dans le navigateur, et que les dépendances servies localement sont versionnées de façon contrôlée.
- [ ] Repasser la checklist [`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md), les migrations Alembic et les tests sur PostgreSQL.
- [ ] Vérifier les sauvegardes et tester la restauration sur un environnement non productif.

## Priorité P2 — évolutions après stabilisation

- [ ] Ajouter des tests de bout en bout automatisés pour les principaux parcours mobile et desktop.
- [ ] Mesurer les temps de préparation des questions, le taux de recours au mode local et les erreurs de rendu sans collecter inutilement de données personnelles.
- [ ] Enrichir progressivement le corpus local en maintenant la validation des réponses et un équilibre des niveaux.
- [ ] Améliorer les recommandations de révision à partir de résultats observés, en expliquant clairement pourquoi une notion est suggérée.
- [ ] Documenter les procédures de diagnostic pour un problème d’illustration, un échec de génération IA et un défaut de rendu scientifique.

## Règle de validation et de déploiement

1. Reproduire les contrôles localement avant de proposer un changement.
2. Ajouter ou adapter les tests qui couvrent la régression.
3. Ne pas fusionner ni déployer si la CI est rouge ou si le smoke test échoue.
4. Après un déploiement approuvé, vérifier les endpoints de santé, les logs, les parcours concernés et le rendu réel dans le navigateur.
5. Ne cocher une tâche de validation manuelle qu’après avoir effectué le contrôle correspondant.
