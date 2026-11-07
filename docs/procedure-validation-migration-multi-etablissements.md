# Validation de la migration multiétablissements sur une copie anonymisée

> **Réservé au responsable autorisé de la base de données.**
> Ne jamais exécuter cette procédure sur la base de production. Ne jamais
> déposer une sauvegarde réelle, des identifiants, des secrets ou des données
> personnelles dans GitHub, ChatGPT, les journaux CI ou un ticket.

## Objectif

Vérifier le backfill de la migration `h1c7e9a2b4d6` sur une copie PostgreSQL
représentative, sans exposer les données des apprenants et sans modifier la
production.

Le test synthétique `tests/test_postgres_multi_tenant_migration.py` complète
cette validation, mais ne la remplace pas : il reproduit un sous-ensemble
contrôlé du schéma historique.

## Préparation par le responsable de la base

1. Autoriser explicitement l'opération et identifier un opérateur adulte
   responsable de la sauvegarde et de son traitement.
2. Créer un environnement PostgreSQL temporaire, isolé du réseau applicatif
   et sans accès aux services de production.
3. Restaurer la sauvegarde dans cet environnement restreint. Ne donner aucun
   accès développeur à cette copie tant que l'anonymisation n'est pas terminée.
4. Anonymiser de manière irréversible les identifiants directs et indirects :
   noms, prénoms, adresses e-mail, téléphones, adresses, numéros d'élève,
   identifiants externes, contenus libres et pièces jointes.
5. Supprimer ou neutraliser les secrets, jetons de session, clés API,
   identifiants OAuth et données d'authentification qui ne sont pas nécessaires.
6. Préserver uniquement les relations et distributions nécessaires au test :
   utilisateurs fictifs, rôles, établissements actifs/inactifs, appartenances,
   cours, notifications, inscriptions et cas ambigus.
7. Vérifier qu'aucune donnée permettant de réidentifier une personne ne
   subsiste. Si cette vérification échoue, ne pas partager la copie.

## Contrôles avant migration

- [ ] Le responsable a autorisé la copie et son usage de test.
- [ ] La base temporaire n'est pas la base de production.
- [ ] Les intégrations sortantes (e-mails, SMS, paiements, webhooks) sont désactivées.
- [ ] Les secrets et données personnelles ont été supprimés ou anonymisés.
- [ ] Les relations nécessaires au backfill sont conservées.
- [ ] Un point de restauration de l'environnement temporaire est disponible.
- [ ] La version du schéma et la révision Alembic initiale sont consignées.

## Exécution contrôlée

Depuis le pipeline CI privé ou l'environnement de test approuvé, définir
`DATABASE_URL` uniquement comme secret d'environnement, jamais dans le code,
la ligne de commande partagée ou les journaux. Vérifier d'abord que l'URL
désigne bien la base temporaire anonymisée.

Exécuter ensuite, dans cet ordre :

1. Vérifier le graphe Alembic : `python scripts/verify_migrations.py`.
2. Consigner la révision initiale avec `alembic current`.
3. Appliquer la migration jusqu'à la tête : `alembic upgrade head`.
4. Vérifier à nouveau la révision : `alembic current`.
5. Rejouer `alembic upgrade head` pour contrôler l'idempotence.
6. Exécuter les tests de backfill et de cloisonnement disponibles.
7. Contrôler les cas ci-dessous avec des résultats agrégés, sans exporter de
   lignes nominatives.

## Résultats à vérifier

- Les appartenances historiques sont reconstituées sans doublons.
- Les rôles globaux ne sont pas transformés en privilèges excessifs.
- Un cours d'un professeur rattaché à un seul établissement actif est affecté
  au bon établissement.
- Un cours lié à un établissement inactif ou à plusieurs établissements est
  mis en quarantaine et n'est pas attribué arbitrairement.
- Les cours historiques indépendants conservent leur périmètre prévu.
- Les notifications et leurs liens utiles sont conservés.
- Les inscriptions, fichiers, révisions, tâches asynchrones et autres données
  dépendantes restent cohérents.
- Les contrôles d'accès interétablissements refusent les accès croisés.
- Les migrations peuvent être rejouées sans doublons ni perte de données.

## Rapport de validation

Le responsable consigne uniquement :

- identifiant de l'environnement temporaire (sans URL ni secret) ;
- révision Alembic avant et après ;
- date et version du commit testé ;
- nombres agrégés de lignes traitées par catégorie ;
- résultats réussite/échec des scénarios ;
- anomalies et mesures correctives ;
- nom/fonction du responsable ayant approuvé le rapport.

Ne joindre aucune ligne de données, capture contenant des informations
personnelles, sauvegarde, chaîne de connexion ou secret.

## Décision de fusion et de déploiement

La PR #326 ne doit être fusionnée qu'après :
1. CI complète verte sur le commit candidat ;
2. validation documentée sur la copie anonymisée ;
3. vérification des parcours d'accès et de non-régression ;
4. approbation explicite du responsable du projet et du responsable de la base.

La CI PostgreSQL sur base neuve et le test synthétique ne constituent pas,
à eux seuls, une autorisation de migration en production.
