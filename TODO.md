# TODO — MITARIDALA

**Mise à jour : 20 octobre 2026**  
**Objet prioritaire :** fiabiliser le Jeu cérébral et le parcours de progression.

> Les cases cochées indiquent qu'une fonctionnalité est présente dans le code ou que le contrôle correspondant existe. Elles ne signifient pas automatiquement qu'elle a été validée en production. Cocher les vérifications manuelles uniquement après les avoir réellement effectuées.

## P0 — Jeu cérébral : tests et qualité avant release

### Fonctionnalités présentes dans le code

- [x] Cinq thèmes : logique et déduction, calcul mental, suites et régularités, mots et analogies, observation et attention.
- [x] Questions en français et en malgache, avec une banque locale de secours si la génération IA est indisponible.
- [x] Sessions de cinq questions et adaptation du niveau selon les réponses.
- [x] Corrections après réponse et bilan avec compétences bien repérées, notions à explorer et suggestions de suite.
- [x] Illustrations locales : accueil, illustrations par thème, mascotte et trophée.
- [x] Animations de transition et récompenses visuelles.
- [x] Pause avec désactivation temporaire des réponses.
- [x] Chronomètre facultatif ; le dépassement du temps cible ne retire pas de points.
- [x] Préférence « Réduire les animations » partagée entre les écrans et respect de `prefers-reduced-motion`.
- [x] Présentation responsive avec règles dédiées aux écrans étroits.
- [x] Rendu scientifique partagé pour les questions, choix et corrections du jeu.
- [x] Tests applicatifs dédiés au profil, aux sessions, aux recommandations, aux templates et aux illustrations.
- [x] Smoke test Playwright ajouté dans `scripts/smoke_jeu_cerebral.mjs` et branché dans la CI.

### Vérifications encore nécessaires

- [ ] Obtenir une CI entièrement verte sur la branche de travail : smoke Playwright, tests Python et smoke PostgreSQL.
- [ ] Corriger les échecs du nouveau smoke test avant toute fusion ; ne pas contourner une assertion uniquement pour faire passer la CI.
- [ ] Vérifier le parcours réel dans le navigateur : démarrage, changement de thème, réponse correcte/incorrecte, question suivante, bilan, corrections, recommandation et nouvelle session.
- [ ] Vérifier l'affichage sur téléphone Android, tablette et ordinateur, dont largeur 320 px, thème clair et thème sombre.
- [ ] Vérifier pause/reprise avec et sans chronomètre, après rechargement de page et après retour depuis un autre onglet.
- [ ] Confirmer que le chronomètre arrivé à zéro laisse toujours l'étudiant terminer la session sans perte de points.
- [ ] Tester la préférence d'animations depuis l'accueil, la session et le résultat, ainsi que la préférence système.
- [ ] Vérifier la navigation clavier, le focus visible, les tailles de cible tactile, les libellés accessibles et les annonces de progression.
- [ ] Vérifier chaque illustration locale dans un vrai navigateur ; un statut HTTP 200 ne suffit pas à confirmer le rendu visuel.
- [ ] Tester une illustration manquante, un échec de chargement, un réseau lent, une clé IA absente, une limite de fournisseur, un timeout et une réponse IA invalide.
- [ ] Revoir l'exactitude des banques FR/MG : calcul de la réponse, choix non ambigus, une seule bonne réponse, explication cohérente et traduction naturelle.
- [ ] Vérifier que les conseils sont encourageants, basés sur les réponses de la session et ne prétendent pas mesurer l'intelligence générale.

## P0 — Rendu scientifique transversal

- [x] Moteur partagé `app/static/js/rendu_ia.js` pour le Markdown, les mathématiques, la chimie, le code et l'assainissement HTML.
- [x] Bibliothèques front-end versionnées via `scripts/vendor_frontend_dependencies.py` et servies localement après vérification d'intégrité.
- [x] Smoke test de navigateur du moteur de rendu déjà présent dans la CI.
- [ ] Étendre/maintenir un corpus de référence pour fractions, racines, puissances, indices, matrices, systèmes, limites, dérivées, intégrales, vecteurs et symboles grecs.
- [ ] Tester physique : unités, conversions, vecteurs, indices, exposants et symboles spéciaux.
- [ ] Tester chimie : indices, charges, ions, états, réactions et flèches.
- [ ] Tester informatique : blocs de code, indentation, HTML/JSON littéral et caractères d'échappement.
- [ ] Tester comptabilité : montants en Ar, séparateurs, tableaux, bilans et comptes en T sans altération des données.
- [ ] Vérifier les antislashs perdus dans les données JSON, formules mal formées, contenus très longs, code et Unicode.
- [ ] Vérifier que les sorties HTML générées sont assainies et qu'un échec de rendu laisse le texte source exploitable.
- [ ] Contrôler le rendu sur téléphone, thème clair et thème sombre.

## P1 — Relier le jeu à l'apprentissage scolaire

- [x] Agréger jusqu'aux 20 dernières sessions terminées par notion, avec filtrage par langue pour les recommandations de génération.
- [x] Afficher les notions à renforcer, les notions souvent réussies et les notions à observer dans l'accueil et le bilan.
- [x] Ne classer une notion comme difficulté répétée qu'après au moins deux réponses ; laisser un seul essai au stade « à observer ».
- [x] Utiliser les notions faibles récurrentes dans le profil IA lorsque la notion correspond réellement au thème choisi.
- [x] Relier une notion faible à un document seulement si le titre ou la matière contient une correspondance explicite ou un synonyme pédagogique contrôlé.
- [x] Filtrer les ressources recommandées par filière, statut approuvé et appartenance à un cercle privé.
- [x] Afficher une solution de repli vers la bibliothèque quand aucun document approuvé ne correspond assez précisément.
- [x] Ajouter un test de parcours des routes : démarrage, cinq réponses, persistance du score et rendu du bilan.
- [ ] Enrichir et valider avec les équipes pédagogiques la liste de synonymes reliant les notions de logique/calcul aux titres des cours réellement utilisés à Madagascar.
- [ ] Proposer un exercice ciblé après une erreur, sans rediriger vers une leçon qui ne traite pas la notion concernée.
- [ ] Ajouter une nouvelle tentative courte après la recommandation, pour mesurer la progression sur la même notion.
- [ ] Permettre de désactiver ou réinitialiser l'historique de jeu selon la politique de confidentialité applicable.
- [ ] Éviter les classements publics qui humilient les élèves ; privilégier des objectifs personnels et des progrès comparés à leurs propres résultats.

## P1 — Documents et qualité pédagogique

- [ ] Vérifier que chaque résumé de document indique le sujet, la matière, le niveau et le type de cours, tout en signalant les éléments incertains.
- [ ] Confirmer que les documents à modérer restent inaccessibles au public avant validation.
- [ ] Relier les questions générées au passage du document source lorsque possible, afin de faciliter la vérification.
- [ ] Tester le parcours Quiz IA → erreurs par notion → Tuteur IA → exercices ciblés → progression.
- [ ] Relire les traductions françaises et malgaches des pages et messages pédagogiques.

## P1 — Sécurité et fiabilité

- [ ] Retester l'accès propriétaire sur les sessions de jeu, documents, quiz, cercles, fichiers et outils d'administration.
- [ ] Vérifier CSRF, limitation de débit, expiration de session et reprise après erreur sur les routes modifiant les données.
- [ ] Vérifier les secrets de production, les journaux et les données personnelles collectées.
- [ ] Exécuter les migrations et les tests PostgreSQL avant la release.
- [ ] Vérifier les sauvegardes et effectuer un test de restauration hors production.

## Règle de validation et déploiement

1. Reproduire les contrôles localement ou dans la CI avant de proposer une fusion.
2. Ajouter des tests ciblés pour toute correction de régression.
3. Ne pas fusionner ni déployer tant que la CI complète n'est pas verte.
4. Après la fusion approuvée, vérifier la santé du service, les logs et le parcours réel sur l'instance de prévisualisation avant la production.
5. Cocher une vérification manuelle seulement après son exécution réelle.
