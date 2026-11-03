# MITARIDALA — Priorités d’amélioration

*Mise à jour : 2 novembre 2026*

Cette feuille de route présente les améliorations attendues du point de vue des apprenants, des enseignants et des établissements. Une tâche ne doit être déclarée terminée qu’après vérification de son fonctionnement réel.

## Chantier multiétablissements

Le socle d'appartenance institutionnelle et le rattachement des cours sont
implémentés dans la branche de travail dédiée. Les appartenances sont
distinctes des rôles globaux ; les cours institutionnels contrôlent le tenant
au niveau serveur. Les vérifications de migration et de production restent
obligatoires avant de déclarer ce chantier terminé.

- [ ] Exécuter la migration multiétablissement sur une copie PostgreSQL représentative.
- [ ] Tester en production-like deux établissements séparés, y compris les WebSockets, fichiers de copies et fiches de révision.
- [ ] Vérifier l'affectation des professeurs et responsables, le retrait d'un membre et la conservation du dernier responsable.
- [ ] Vérifier que les notifications de devoir, note, présence, rappel et fiche restent invisibles après retrait de l'inscription.
- [ ] Vérifier les cours historiques à affectation ambiguë : aucun étudiant ne doit y accéder avant l'arbitrage de l'administrateur.
- [ ] Vérifier l'écran d'affectation admin avec des professeurs multiétablissements et des établissements suspendus.
- [ ] Permettre aux responsables d'établissement autorisés de gérer eux-mêmes l'import de leurs listes d'étudiants, sans accès aux autres établissements.
- [ ] Définir les documents privés d'établissement et leurs règles sur la bibliothèque, le téléchargement, le Tuteur IA, les quiz et les fiches de révision.
- [ ] Ajouter les périmètres institutionnels aux autres ressources qui doivent être privées ; les documents généraux et cercles conservent leurs règles actuelles.
- [ ] Tester les listes, imports et rapports avec plusieurs centaines puis plusieurs milliers de comptes.

## Chantier de suivi académique

Le dépôt comprend désormais le carnet de notes pondéré par cours, les moyennes par période, le registre pédagogique des présences, les notifications de devoir/note/pointage, les rapports par cours et un rapport global agrégé réservé à l'administration. Les notes faibles ouvrent aussi un parcours d'aide au Tuteur IA sans modifier artificiellement la progression mesurée par les quiz.
- [ ] Vérifier en environnement de test les parcours complets professeur → devoir → rendu → correction → carnet → notification étudiant.
- [ ] Vérifier en environnement de test le pointage présent / absent / retard / excusé, les justificatifs et l'historique étudiant.
- [ ] Vérifier le rapport global avec des cours scolaires et universitaires, des classes vides et des évaluations non corrigées.
- [ ] Vérifier l'export CSV du rapport et la neutralisation des cellules pouvant être interprétées comme formules.

## Priorité 1 — Fiabilité et confiance

- [ ] Vérifier les parcours essentiels : inscription, connexion, récupération de compte, profil, navigation et déconnexion.
- [ ] Clarifier les règles d’accès aux ressources selon le statut du document, le compte de l’utilisateur et les règles des espaces collaboratifs.
- [ ] Vérifier qu’un document en attente ou rejeté n’est pas présenté comme une ressource publiée.
- [ ] Contrôler les droits des apprenants, enseignants et responsables d’établissement sur les actions qui leur sont destinées.
- [ ] Rendre les états des traitements assistés par IA compréhensibles : en attente, disponible, à reprendre ou en échec.
- [ ] Améliorer les messages d’aide afin qu’un utilisateur sache quoi faire lorsqu’une action échoue.

## Priorité 2 — Référentiel scolaire et universitaire

- [ ] **Université de Toamasina :** confirmer les composantes, mentions, parcours et niveaux à partir des documents officiels les plus récents.
- [ ] Vérifier individuellement les habilitations et accréditations auprès des autorités compétentes ; conserver la référence et la période de validité du document officiel.
- [ ] Distinguer clairement un établissement répertorié, un programme documenté, une formation autorisée et une admission effectivement ouverte pour l’année concernée.
- [ ] Vérifier les informations d’admission 2026–2027 auprès des composantes concernées avant toute présentation comme offre ouverte.
- [ ] **Collège :** vérifier les classes de 6e à 3e, les matières et les programmes applicables.
- [ ] **Lycée :** vérifier les classes, séries ou options, matières et programmes applicables.
- [ ] **ETFP :** poursuivre la comparaison des établissements et formations avec les sources officielles du ministère compétent, région par région.
- [ ] Signaler les informations non confirmées au lieu de compléter les données par supposition.

## Priorité 3 — Qualité pédagogique

- [ ] Réduire la répétition des questions dans les quiz et les jeux, tout en conservant leur cohérence avec les notions étudiées.
- [ ] Relier les erreurs observées aux ressources, explications et exercices qui aident réellement à progresser.
- [ ] Vérifier que les fiches de révision sont fondées sur des documents approuvés et sur des informations réellement disponibles.
- [ ] Mieux expliquer les états des fiches en préparation ou en échec, et faciliter leur reprise.
- [ ] Vérifier que les résumés de séances virtuelles s’appuient sur des notes ou contenus réellement disponibles.
- [ ] Améliorer la continuité entre les quiz, les révisions, le Tuteur IA et les activités de l’apprenant.

## Priorité 4 — Expérience utilisateur

- [ ] Compléter les traductions françaises, malgaches et anglaises sur toutes les pages, les formulaires et les messages.
- [ ] Vérifier l’affichage sur téléphone, tablette et ordinateur, y compris les écrans étroits.
- [ ] Améliorer la lisibilité des thèmes clair et sombre, la navigation au clavier et les libellés accessibles.
- [ ] Respecter les préférences de réduction des animations et faciliter les actions courantes.
- [ ] Simplifier les parcours des enseignants et des établissements qui accompagnent plusieurs centaines d’apprenants.

## Priorité 5 — Exploitation et continuité

- [ ] Mesurer les temps de chargement et la stabilité des pages les plus utilisées avant d’optimiser.
- [ ] Vérifier périodiquement la sauvegarde et la restauration des données et des ressources.
- [ ] Améliorer les informations destinées aux responsables lorsqu’un service ou une fonctionnalité est temporairement indisponible.
- [ ] Vérifier le bon déroulement des parcours importants après chaque mise à jour publiée.

## Conditions de clôture

Une amélioration est considérée comme terminée lorsque :

- [ ] le comportement attendu est vérifié dans le parcours concerné ;
- [ ] les tests associés réussissent ;
- [ ] les informations académiques disposent de sources officielles et d’une date de vérification ;
- [ ] les règles d’accès et la confidentialité sont respectées ;
- [ ] l’interface reste utilisable sur mobile et ordinateur ;
- [ ] aucune régression n’est introduite dans les parcours existants.
