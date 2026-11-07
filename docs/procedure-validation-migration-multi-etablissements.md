# Validation de la migration multiétablissements sans copie de données réelles

## Principe

La validation de la migration `h1c7e9a2b4d6` ne requiert pas de restaurer, anonymiser ou partager une sauvegarde de la base Mahay.

La preuve de validation du code repose sur des données entièrement synthétiques et reproductibles dans GitHub Actions :

- un schéma historique PostgreSQL minimal qui reproduit les colonnes utiles au backfill ;
- des établissements actifs et inactifs fictifs ;
- des comptes fictifs avec les rôles étudiant, professeur, administrateur et sponsor ;
- des cours et notifications fictifs ;
- des cas d'affiliation unique, inactive, multiple et indépendante ;
- l'application de la migration, puis sa réexécution pour vérifier l'idempotence ;
- le contrôle de RLS, des contraintes et des compteurs agrégés.

Aucune sauvegarde de production n'est utilisée. Aucun nom, e-mail, téléphone, identifiant réel, contenu libre, fichier d'élève ou secret n'est requis.

## Vérifications automatisées

Les contrôles doivent être exécutés par GitHub Actions sur le PostgreSQL éphémère du job `postgres-smoke` :

1. Appliquer le graphe Alembic jusqu'à `g2a7f5d9c1e3`, la révision précédant la migration multiétablissements.
2. Exécuter `scripts/preflight_multi_tenant_migration.py` : le préflight est strictement en lecture seule et ne renvoie que des nombres et indicateurs techniques.
3. Appliquer `alembic upgrade head`.
4. Réexécuter le préflight et vérifier que les colonnes et la table multiétablissements sont présentes.
5. Rejouer `alembic upgrade head` et vérifier que la migration est idempotente.
6. Exécuter `tests/test_postgres_multi_tenant_migration.py`, qui construit un schéma historique synthétique séparé, applique deux fois la migration et vérifie le backfill.
7. Exécuter les tests d'accès interétablissements, de rôles, de désactivation, de quarantaine et de parcours HTTP.

Le préflight ne doit jamais être configuré avec une URL de production dans GitHub Actions. Le job CI doit exclusivement utiliser son service PostgreSQL jetable local.

## Contrôles attendus

- Les rôles reconnus sont repris sans transformer implicitement un rôle inconnu en privilège.
- Un professeur avec une seule affiliation pédagogique active peut être rattaché au bon établissement.
- Un établissement inactif ou une situation ambiguë ne provoque pas d'affectation arbitraire.
- Les cours historiques indépendants conservent leur périmètre.
- Les codes d'invitation et les notifications sont préservés par les scénarios de test.
- La migration peut être rejouée sans doublons.
- Les contrôles applicatifs refusent les accès interétablissements non autorisés.
- Le schéma PostgreSQL active RLS sur `membre_etablissement`.

Le rôle PostgreSQL utilisé par le job CI peut différer de celui utilisé par l'application en production. Le résultat RLS du job CI vérifie la migration et le rôle de test ; il ne prouve pas à lui seul les privilèges du rôle de production. Ceux-ci doivent être confirmés dans la configuration de déploiement par l'opérateur autorisé, sans publier de chaîne de connexion ou de secret.

## Rapport CI

Le rapport de CI peut conserver uniquement :

- SHA du commit testé ;
- identifiants et conclusions des jobs GitHub Actions ;
- révisions Alembic avant et après ;
- état des colonnes, contraintes et RLS ;
- compteurs agrégés produits depuis les fixtures synthétiques ;
- résultats PASS/FAIL des scénarios et anomalies techniques.

Ne pas joindre de sauvegarde, export de table, ligne utilisateur, donnée personnelle, capture d'écran contenant des informations confidentielles, identifiant d'accès, jeton, clé ou chaîne de connexion.

## Déploiement

La CI synthétique constitue la preuve reproductible que la migration fonctionne sur les scénarios modélisés. Elle réduit le besoin d'une validation manuelle sur copie de données réelles, mais ne transforme pas la CI en autorisation de déploiement.

Avant une migration de production, l'opérateur adulte autorisé doit suivre la procédure de déploiement approuvée, vérifier le rôle PostgreSQL réel et disposer d'un plan de sauvegarde/restauration géré hors de GitHub et de ChatGPT. Après déploiement, vérifier la révision Alembic, la santé du service, les erreurs applicatives et les métriques agrégées. Ne jamais tester en écriture sur la base de production ni partager ses données.
