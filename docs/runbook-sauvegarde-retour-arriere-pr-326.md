# Runbook de préparation, sauvegarde et retour arrière — PR #326

## 1. Objet et limites

Ce runbook couvre le changement multiétablissements porté par la PR #326 et la migration Alembic `h1c7e9a2b4d6`.

Il distingue quatre preuves différentes :

1. **CI synthétique** : tests automatisés exécutés sur SQLite et PostgreSQL jetable avec des données fictives.
2. **Audit de production en lecture seule** : état observé du schéma et des rôles PostgreSQL à une date donnée.
3. **Préparation opérationnelle** : sauvegarde/restauration, rôles, privilèges, variables Render et tests de préproduction.
4. **Mise en production** : fusion, migration réelle, contrôle de santé et suivi du déploiement.

La réussite de la CI ne prouve pas que les rôles, les variables ou les sauvegardes de la base réelle sont prêts. Ce runbook ne constitue pas une autorisation de modifier la production.

## 2. Points de restauration du code

Deux branches de sauvegarde ont été créées le 8 novembre 2026 :

| Usage | Branche | Commit figé |
|---|---|---|
| État de la branche cible avant fusion | `backup/pre-merge-main-20261108-audit` | `ca96489d218c57341c6280420aec2b231f13a110` |
| Candidat de la PR #326 | `backup/pr-326-candidate-20261108-audit` | `d300e3672969d45bbb937bf0c471e0f92ef0249d` |

Ces branches protègent les références Git uniquement. Elles ne sont ni une sauvegarde de PostgreSQL, ni une sauvegarde de Supabase Storage, ni une image Render restaurable.

## 3. État vérifié au 8 novembre 2026

### GitHub

- PR #326 : ouverte, non fusionnée.
- Branche candidate : `feat/multi-tenant-institution-foundation`.
- Commit candidat examiné : `d300e3672969d45bbb937bf0c471e0f92ef0249d`.
- Comparaison avec `main` : 72 commits en avance, aucun en retard lors du contrôle.
- CI du commit candidat : workflow `42435329839`, jobs `test` et `postgres-smoke` terminés avec succès.
- Les tests PostgreSQL couvrent la migration/idempotence, les permissions d'un rôle runtime synthétique et les contrôles applicatifs entre deux établissements. Ils ne constituent pas une preuve d'isolation tenant par RLS.
- Les approbations recensées sont antérieures au commit candidat actuel. Une revue du commit exact qui sera fusionné reste nécessaire.

### Supabase — audit en lecture seule

Le contrôle réalisé le 8 novembre 2026 a renvoyé les faits agrégés suivants :

| Contrôle | Résultat |
|---|---:|
| Révision Alembic courante | `g2a7f5d9c1e3` |
| Table `public.membre_etablissement` | Absente |
| Tables publiques | 63 |
| Tables avec RLS activé | 63 |
| Politiques RLS dans `public` | 0 |
| Rôle `mahay_runtime` | Absent |
| `rolbypassrls` du rôle `postgres` | `true` |
| Privilèges SELECT accordés à `anon` | 0 |
| Privilèges SELECT accordés à `authenticated` | 0 |

La migration `h1c7e9a2b4d6` n'a donc pas été appliquée à cette base au moment du contrôle. Le contrôle n'a effectué aucune écriture.

### Render

Les services `mahay-toamasina` et `mitaridala` sont configurés pour déployer depuis `main` après passage des checks. Leur dernier déploiement `live` vérifié correspond au commit `3691b430ddd4fca69457c44ab32ed5dad89bdc75`, pas au candidat de la PR.

L'intégration Render disponible ne permet pas de lire les valeurs des variables d'environnement. La présence et la valeur de `DATABASE_URL`, `MIGRATION_DATABASE_URL`, des secrets de session et des paramètres Supabase ne sont donc pas certifiées ici. Les journaux précédemment examinés indiquaient que le backend se connectait avec le compte PostgreSQL `postgres`; ce constat ne remplace pas un contrôle actuel des deux services et de leurs bases respectives.

## 4. Contrat des connexions PostgreSQL

Le code sépare maintenant les deux connexions :

- `DATABASE_URL` : connexion utilisée par les requêtes de l'application.
- `MIGRATION_DATABASE_URL` : connexion utilisée par Alembic pour les migrations.

`app/main.py` appelle le garde-fou de production avant `executer_migrations()`. `app/database.py` construit un moteur applicatif et un moteur de migration distincts ; `alembic/env.py` utilise le moteur de migration. Si `MIGRATION_DATABASE_URL` est absent/non PostgreSQL, ou si le nom du rôle de `DATABASE_URL` n'est pas exactement `mahay_runtime`, le démarrage en production doit échouer avant la migration.

Le garde-fou vérifie les URL et le nom des rôles uniquement. Il ne se connecte pas à PostgreSQL et ne vérifie pas les attributs réels, propriétaires, GRANT ou ACL par défaut. Ces contrôles doivent être réalisés séparément par un administrateur habilité.

### Contrat visé pour le rôle runtime

Le backend actuel s'appuie sur l'autorisation applicative côté serveur. Le rôle `mahay_runtime` prévu doit respecter les points suivants :

- `LOGIN`, `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`.
- `BYPASSRLS` activé dans l'architecture actuelle, car les tables publiques ont RLS actif sans politique tenant par tenant.
- Droits DML nécessaires (`SELECT`, `INSERT`, `UPDATE`, `DELETE`) sur les tables applicatives existantes et futures, ainsi que les droits d'utilisation nécessaires sur les séquences.
- Aucun privilège DDL et aucune propriété des tables applicatives.
- `USAGE` sur le schéma `public`.

Le rôle de migration est distinct du rôle runtime et dispose des droits de propriétaire/DDL nécessaires à Alembic. Les privilèges par défaut doivent être configurés pour **le rôle qui crée effectivement les nouvelles tables**. Si plusieurs propriétaires créent des objets, chaque jeu d'ACL par défaut doit être audité.

**Important :** `BYPASSRLS` n'est pas une isolation tenant par PostgreSQL. Avec zéro politique RLS, le cloisonnement décrit par cette PR repose sur les contrôles applicatifs. Ne pas passer le runtime à `NOBYPASSRLS` sans avoir d'abord conçu et testé les politiques tenant par tenant pour toutes les tables concernées.

### Vérifications SQL privées

À exécuter uniquement par l'administrateur habilité, dans la console privée de chaque base réellement utilisée. Ces requêtes sont des exemples de contrôle en lecture seule ; ne pas publier le nom de la base, les identifiants ou les chaînes de connexion.

Vérifier les attributs du rôle :

```sql
SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls
FROM pg_roles
WHERE rolname IN ('mahay_runtime', current_user);
```

Après application de la migration sur une base de préproduction, vérifier le propriétaire, RLS, FORCE RLS et le nombre de politiques :

```sql
SELECT
    pg_get_userbyid(c.relowner) AS proprietaire,
    c.relrowsecurity AS rls_active,
    c.relforcerowsecurity AS rls_forcee,
    (SELECT COUNT(*)
       FROM pg_policies p
      WHERE p.schemaname = n.nspname
        AND p.tablename = c.relname) AS nombre_politiques
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname = 'membre_etablissement';
```

Vérifier les droits DML effectifs du rôle runtime sur toutes les tables publiques :

```sql
SELECT
    COUNT(*) FILTER (WHERE NOT has_table_privilege('mahay_runtime', c.oid, 'SELECT')) AS sans_select,
    COUNT(*) FILTER (WHERE NOT has_table_privilege('mahay_runtime', c.oid, 'INSERT')) AS sans_insert,
    COUNT(*) FILTER (WHERE NOT has_table_privilege('mahay_runtime', c.oid, 'UPDATE')) AS sans_update,
    COUNT(*) FILTER (WHERE NOT has_table_privilege('mahay_runtime', c.oid, 'DELETE')) AS sans_delete
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'p');
```

Le même contrôle doit être fait pour les séquences, puis sur les ACL par défaut du ou des rôles créateurs. Une sortie sans erreur sur une seule table ne suffit pas : le contrôle doit couvrir les objets réellement nécessaires à l'application et à ses migrations futures.

## 5. Sauvegarde et préproduction obligatoires

Avant toute migration réelle, l'administrateur habilité doit :

1. Identifier séparément la base réellement utilisée par chacun des deux services Render et confirmer si elles sont partagées ou distinctes.
2. Vérifier l'heure de la dernière sauvegarde PostgreSQL/PITR, sa rétention et le point de restauration disponible.
3. Exécuter un test de restauration sur une base séparée, sans écraser la production, et conserver la preuve datée du résultat.
4. Sauvegarder les objets Supabase Storage séparément lorsque la politique de continuité l'exige ; une sauvegarde SQL ne contient pas les fichiers du bucket.
5. Appliquer la migration sur une préproduction représentative et vérifier les compteurs avant/après, le backfill, la quarantaine et les notifications.
6. Vérifier le rôle de migration, le rôle runtime, les propriétaires, les droits DML, les droits sur séquences et les ACL par défaut.
7. Configurer les deux services Render avec des URL adaptées à leur base respective, sans publier les valeurs. Vérifier que `DATABASE_URL` utilise `mahay_runtime` et que `MIGRATION_DATABASE_URL` est distincte.
8. Tester les parcours complets de deux établissements : création/affectation de cours, inscriptions, désactivation de membre, dernier responsable, notes, présences, devoirs, rendus, notifications, fichiers, WebSockets et tableau blanc.
9. Consigner les résultats sans données personnelles ni secrets, puis obtenir une nouvelle revue du commit candidat exact.

La CI synthétique est déjà verte ; elle ne remplace pas ces contrôles opérationnels.

## 6. Déploiement après validation

Quand et seulement quand les contrôles précédents sont documentés et approuvés :

1. Vérifier que la tête de PR n'a pas changé depuis la dernière revue et que tous les checks du SHA exact sont verts.
2. Confirmer une approbation de revue applicable au SHA courant et les règles de protection de la branche.
3. Fusionner la PR selon la méthode autorisée par le dépôt.
4. Vérifier que Render ne déploie que le nouveau commit `main` après les checks.
5. Contrôler le résultat du déploiement des deux services, les logs de démarrage, `/health`, la révision Alembic et les parcours essentiels.
6. Si l'un des services échoue au démarrage, arrêter la progression et diagnostiquer avant toute autre action. Ne pas modifier les secrets à l'aveugle.

Aucune de ces étapes ne doit être considérée comme réalisée tant que le résultat réel n'a pas été observé.

## 7. Retour arrière

### Incident applicatif après migration

Privilégier un correctif en avant (« forward fix »). Un retour Render à l'ancienne image n'est pas suffisant si la base a déjà enregistré `h1c7e9a2b4d6` : l'ancien code ne connaît pas nécessairement cette révision et ne contient pas les contrôles d'accès introduits par la PR.

### Retour complet à l'état antérieur

À décider et exécuter par un administrateur habilité, avec procédure de maintenance et maîtrise des écritures :

1. Confirmer le point de sauvegarde PostgreSQL cohérent et traiter les écritures intervenues depuis ce point.
2. Restaurer séparément le stockage objet lorsque nécessaire.
3. Restaurer la base à son point antérieur par la procédure validée du fournisseur ; ne pas exécuter aveuglément `alembic downgrade`, qui supprime des colonnes et structures.
4. Déployer le commit de code sauvegardé qui correspond exactement au schéma restauré.
5. Vérifier la révision Alembic, les contrôles de santé, les connexions, les parcours essentiels, les journaux et les métriques avant de sortir de maintenance.

Ne jamais déplacer de force `main` vers une ancienne révision et ne jamais restaurer uniquement l'image applicative si le schéma est déjà migré.

## 8. Décision de préparation au 8 novembre 2026

**État : NON PRÊT POUR FUSION/PRODUCTION.**

La CI du commit `d300e367` est réussie et les snapshots Git du code ont été créés. En revanche, le contrôle Supabase confirme que la table et le rôle runtime requis sont absents et que la base n'a pas encore reçu la migration. Les valeurs Render, le rôle de migration, les ACL, les sauvegardes PostgreSQL, les tests de restauration et la préproduction représentative ne sont pas vérifiés.

Aucune migration de production, création de rôle, modification de privilèges, modification de secret, fusion ou déploiement n'a été exécuté dans le cadre de cette vérification.


---

> **Mise à jour prioritaire :** les sections 3 et 8 ci-dessus décrivent un audit historique sur un ancien candidat. Pour l'état opérationnel le plus récent, utiliser l'addendum ci-dessous. Il prévaut en cas de contradiction.

## 9. Audit opérationnel connecté — 8 novembre 2026

Audit en lecture seule réalisé via les accès connectés Supabase, Render et GitHub. Aucun rôle, privilège, secret, schéma, service ou déploiement n'a été modifié durant cet audit.

### 9.1 GitHub — tête de PR et sauvegardes du code

- PR #326 : ouverte, non fusionnée, non draft, base `main`.
- Tête exacte : `42e7693a6cd5475cd937f81508424263d30d3a98`.
- Comparaison avec `main` : 84 commits en avance, 0 en retard ; 54 fichiers modifiés.
- Workflow CI `42441233275` sur ce SHA : jobs `test` et `postgres-smoke` réussis.
- Approbation fraîche du reviewer présente sur le SHA exact courant (8 novembre 2026, 07:10 UTC).
- Sauvegarde Git `backup/pr-326-candidate-sqlmodel-select-20261108` vérifiée au SHA exact `42e7693a6cd5475cd937f81508424263d30d3a98`.
- Sauvegarde Git de la cible `backup/pre-merge-main-20261108-audit` vérifiée au SHA `ca96489d218c57341c6280420aec2b231f13a110`.

**Portée :** ces références ne sauvegardent ni PostgreSQL, ni Supabase Storage, ni les variables Render.

### 9.2 Supabase — projet MAHAY

Projet `sphkebpvlyieoapkybtu`, statut `ACTIVE_HEALTHY`, organisation au forfait Free, région `eu-central-1`, PostgreSQL 17.6.

Résultat SQL agrégé de la base `postgres` :

| Contrôle | Résultat |
|---|---:|
| Révision Alembic | `g2a7f5d9c1e3` |
| Tables du schéma public | 63 |
| Tables publiques avec RLS activé | 63 |
| Politiques RLS dans public | 0 |
| `public.membre_etablissement` | Absente |
| Rôle `mahay_runtime` | Absent |
| Rôle courant de l'audit | `postgres` |
| Propriétaire observé des tables clés (utilisateur, cours, notification, établissement, alembic_version) | `postgres` |
| `FORCE ROW LEVEL SECURITY` sur ces tables clés | Faux |

Les rôles `anon` et `authenticated` n'ont pas de privilèges de table sur les 63 tables publiques actuellement présentes. Le rôle `service_role` dispose de privilèges étendus sur les tables et séquences existantes et possède `BYPASSRLS`; il ne doit pas être réutilisé comme compte runtime de l'application.

**RLS :** le constat « 63 tables avec RLS et 0 politique » signifie que ce projet ne démontre pas une isolation par établissement imposée par des policies PostgreSQL. Le candidat PR #326 repose sur les contrôles applicatifs FastAPI et sur un compte backend `BYPASSRLS`. Ce modèle doit rester explicitement documenté ; ne pas prétendre que RLS sépare déjà les tenants.

#### ACL par défaut constatées

- Pour les objets créés par `postgres`, les ACL par défaut accordent les droits DML sur les tables et les droits d'utilisation/lecture/mise à jour des séquences à `service_role`, mais ne préparent pas `mahay_runtime`.
- Pour les objets créés par `supabase_admin`, les ACL par défaut observées comprennent des privilèges larges sur les futures tables et séquences pour `anon` et `authenticated`.
- Les ACL des objets futurs s'appliquent selon leur rôle créateur. Il faut confirmer l'identité réellement utilisée par Alembic et cadrer les ACL de ce rôle avant d'autoriser la migration. Ne pas révoquer globalement les privilèges de rôles plateforme sans confirmer leur périmètre.

#### Sauvegarde et restauration

L'organisation est au forfait Free : les sauvegardes quotidiennes automatiques Supabase ne sont pas incluses. Les exports SQL sont à réaliser manuellement et à conserver hors du projet. Les exports de base ne contiennent pas les objets binaires de Supabase Storage ; les fichiers doivent être sauvegardés séparément.

Au moment de cet audit, aucune preuve d'export manuel complet et aucune preuve de restauration sur un projet/base séparé n'ont été fournies par les outils connectés. **La condition de sauvegarde/restauration est donc NON VALIDÉE.**

Pour un futur export manuel avec Supabase CLI v3, vérifier la version et le contrat de la commande avant exécution. Depuis CLI v3 (publiée début novembre 2026), les commandes de base ciblent le local par défaut : l'option `--remote` est nécessaire pour viser le projet hébergé. Un dump de schéma seul n'est pas une sauvegarde complète : exporter aussi les rôles et les données, conserver les trois fichiers de manière chiffrée hors site, puis vérifier leur intégrité et réaliser une restauration complète sur une cible isolée. Ne jamais tester la restauration sur la production.

### 9.3 Render — services réellement présents

Workspace Render : `My Workspace`, région Frankfurt.

| Service | État | Branche | Dernier déploiement live |
|---|---|---|---|
| `mahay-toamasina` | Non suspendu | `main` | `3691b430ddd4fca69457c44ab32ed5dad89bdc75` |
| `mitaridala` | Non suspendu | `main` | `3691b430ddd4fca69457c44ab32ed5dad89bdc75` |

Les deux services utilisent le dépôt `jakejohnson0796-glitch/mahay-toamasina`, avec auto-déploiement après passage des checks CI. Aucun PostgreSQL hébergé directement dans ce workspace Render n'a été listé ; le projet Supabase MAHAY est la seule base Supabase visible dans les accès connectés.

L'API Render consultée ne retourne pas les valeurs des variables d'environnement. La présence, la cible, le nom d'utilisateur et la distinction de `DATABASE_URL` / `MIGRATION_DATABASE_URL` restent donc **non vérifiés** pour chacun des deux services. Le fait que `DATABASE_URL` soit déclaré dans `render.yaml` pour `mahay-toamasina`, mais pas explicitement pour `mitaridala`, ne prouve pas qu'il manque sur le service existant : les variables omises d'un service existant peuvent être conservées par le Blueprint. Vérifier les noms et les empreintes de cible dans le Dashboard sans révéler les secrets.

Les logs d'erreur/avertissement interrogés n'ont retourné aucune entrée dans la fenêtre de contrôle. Les métriques HTTP et les logs de requête `/health` n'ont pas permis de confirmer un code HTTP 2xx/3xx. **Ne pas déclarer /health validé** sur la seule base de l'absence de logs.

### 9.4 Décision et conditions de levée

**État au 8 novembre 2026 : NON PRÊT POUR FUSION / PRODUCTION**, malgré la CI et l'approbation GitHub confirmées.

Les blocages sont :

1. Export manuel PostgreSQL complet non attesté et restauration isolée non testée.
2. Sauvegarde indépendante de Supabase Storage non attestée.
3. `mahay_runtime` absent ; rôle runtime et GRANT réels non préparés.
4. Rôle créateur des objets et ACL par défaut non entièrement cadrés pour les migrations futures.
5. Connexions `DATABASE_URL` et `MIGRATION_DATABASE_URL` des deux services Render non vérifiées.
6. Préproduction représentative et parcours réels entre deux établissements non attestés.
7. Health check HTTP des deux services non confirmé.

Aucune migration de production, création de rôle, modification de privilèges, modification de variables, fusion ou déploiement n'a été réalisée durant cet audit.

## 10. Ordre d'exécution à respecter pour lever les blocages

1. Exporter rôles, schéma et données depuis le projet Supabase MAHAY avec la CLI Supabase v3 ou une méthode officielle vérifiée ; conserver les fichiers hors site dans un espace chiffré et restreint. Exporter séparément les objets Storage nécessaires.
2. Vérifier les empreintes SHA-256 des fichiers, puis restaurer les exports sur une cible isolée sans écraser la base source. Comparer les révisions, les extensions, les contraintes et des compteurs agrégés des principales tables ; consigner le résultat.
3. Confirmer dans le Dashboard Render, pour chacun des deux services, les noms et la cible des variables DB sans publier les valeurs. Identifier explicitement la base cible de chacun.
4. Définir le rôle de migration et le rôle runtime. Le rôle runtime doit être `LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE`, `BYPASSRLS` conformément à l'architecture actuelle, sans propriété ni DDL, avec `USAGE` sur public, DML strictement nécessaire sur les tables, droits nécessaires sur les séquences et ACL par défaut appliquées au rôle créateur réel.
5. Tester l'identité de migration, la création d'objets et les ACL sur une préproduction restaurée. Ne pas essayer de rendre la migration propriétaire de toutes les tables de production par un simple `GRANT` : PostgreSQL exige les droits de propriétaire ou une délégation explicite pour certaines opérations DDL.
6. Configurer les variables Render en conservant les valeurs existantes hors du périmètre demandé. Vérifier après sauvegarde de la configuration et déploiement que chaque service utilise le rôle runtime dédié pour les requêtes et un rôle distinct pour Alembic.
7. Appliquer la migration par Alembic sur la préproduction puis vérifier la table, colonnes, PK, FK, index, RLS, absence de policy non prévue, GRANT, séquences, backfill, quarantaine et idempotence.
8. Exécuter les parcours applicatifs complets sur deux établissements, y compris inscriptions incohérentes, désactivation de membre, dernier responsable, devoirs, notes, présences, rendus, notifications, téléchargements et WebSockets.
9. Réactualiser les checks CI et obtenir une revue portant sur le SHA final exact.
10. Seulement après validation et approbation documentées, planifier la livraison de production, surveiller les deux déploiements Render et contrôler la révision Alembic, `/health`, les logs et les parcours essentiels.

**Arrêt obligatoire :** si une preuve de sauvegarde/restauration, d'identité de base ou de privilège manque, ne pas fusionner et ne pas lancer la migration de production.
