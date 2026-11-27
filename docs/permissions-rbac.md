# Politique centralisée des rôles et permissions (RBAC)

## Objectif

Le module `app/permissions.py` centralise les décisions d'autorisation côté serveur. Les gabarits et éléments de navigation ne sont jamais considérés comme des contrôles de sécurité.

La politique combine :
- le rôle global du compte ;
- l'approbation effective du profil professionnel ou familial ;
- la propriété ou l'appartenance à une ressource ;
- le périmètre institutionnel ou familial.

## Règles en vigueur dans cette première phase

| Profil / autorité | Autorisations centrales | Limite de portée |
|---|---|---|
| Administrateur global | Permissions de plateforme, supervision, administration, actions globales | Compte non banni ; MFA et confirmation admin continuent d'être appliquées par les mécanismes existants |
| Professeur approuvé | Outils pédagogiques, contribution à l'harmonisation, gestion de cours | Uniquement ses cours et les espaces pédagogiques qui lui sont attribués |
| Élève / étudiant | Accès aux cours auxquels il est inscrit | Ses inscriptions et ses propres données |
| Responsable légal approuvé | Accès au portail famille | Uniquement les enfants ayant un lien actif vérifié |
| Répétiteur approuvé | Gestion de son profil et réponses à ses demandes | Uniquement les demandes qui lui sont adressées |
| Sponsor approuvé | Gestion de son profil et demande de partenariat | Son propre compte et ses propositions |
| Responsable d'établissement | Gestion locale des membres | Uniquement son établissement et les rôles de rang inférieur |
| Gestionnaire d'établissement | Gestion locale restreinte | Uniquement son établissement et les rôles enseignant / apprenant |
| Enseignant / apprenant d'établissement | Appartenance institutionnelle | Aucun pouvoir de gestion des membres par cette appartenance seule |

## Points de contrôle migrés vers la politique centrale

- Espace professionnel enseignant et gestion des cours.
- Outils de séance et droits de gestion du cours.
- Carnet de notes et rapports académiques.
- Harmonisation pédagogique : contribution professeur / décision admin.
- Gestion des membres et hiérarchie des rôles institutionnels.
- Accès aux cercles d'étude et à leur gestion.
- Portail famille et téléchargement des bulletins.

Les routes conservent leurs contrôles métier complémentaires (statut de séance, statut de publication, abonnement, CSRF, appartenance réelle, etc.). La politique centrale ne les remplace pas.

## Séparation entre appartenance et autorisation

Un rôle local `responsable`, `gestionnaire`, `enseignant` ou `etudiant` n'accorde jamais le rôle global `admin`. Un compte peut appartenir à plusieurs établissements, mais la gestion locale est recalculée dans le périmètre de l'établissement demandé.

## État des administrateurs spécialisés

Dans cette première phase, le rôle `admin` reste l'administrateur global existant. Aucun rôle délégué tel que « modérateur », « administrateur pédagogique » ou « gestionnaire financier » n'est créé tant que tous les points d'entrée de chaque domaine ne sont pas migrés vers des permissions explicites. Donner un rôle partiellement limité avant cette migration pourrait laisser une route historique accessible.

La prochaine phase doit introduire des attributions persistantes de permissions par domaine et par périmètre, avec une interface d'administration et une journalisation obligatoire des attributions / révocations.

## Principes non négociables

1. Refus par défaut pour une permission inconnue.
2. Vérification côté serveur pour chaque opération sensible.
3. Vérification de la propriété / appartenance à la ressource demandée.
4. Aucun utilisateur ne peut s'attribuer un rôle supérieur.
5. Une approbation de profil et une appartenance familiale sont deux contrôles distincts.
6. Les journaux, tests et vérifications CI doivent accompagner toute évolution des autorisations.

## Vérifications à effectuer avant déploiement

- Tests unitaires de la politique RBAC et des périmètres.
- Tests HTTP des opérations qui mutent les cours, les bulletins, les membres institutionnels et les cercles.
- Tests WebSocket pour les classes et cercles, y compris les comptes révoqués / bannis.
- Vérification que les refus sont appliqués par les routes API, même quand une URL est appelée directement.
- Validation des jobs CI requis et revue du diff avant fusion.
