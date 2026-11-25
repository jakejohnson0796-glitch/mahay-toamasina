# Sauvegarde et restauration de la base Mahay

## État et périmètre

Le workflow `.github/workflows/database-backup.yml` permet de produire, à la demande, une sauvegarde PostgreSQL chiffrée avec [age](https://age-encryption.org/).

Il exporte uniquement le schéma applicatif `public` avec le client PostgreSQL 17, puis vérifie l'archive avec `pg_restore --list` avant chiffrement. **Seul le fichier `.dump.age` est publié comme artefact GitHub.** Le dump en clair est supprimé avant l'envoi de l'artefact et le répertoire temporaire est supprimé à la fin de l'étape.

Ce workflow est volontairement manuel pour l'instant. Il ne constitue pas encore une sauvegarde automatique tant que les secrets GitHub ne sont pas installés et qu'un déclenchement planifié n'a pas été activé.

## Configuration initiale

### 1. Créer et conserver la clé privée age

Sur un ordinateur de confiance, avec age installé :

```bash
age-keygen -o mahay-backup-key.txt
age-keygen -y mahay-backup-key.txt
```

La deuxième commande affiche la clé publique commençant par `age1`. La clé privée contenue dans `mahay-backup-key.txt` doit rester hors du dépôt et hors de GitHub. Conserve-en une copie protégée et accessible en cas de restauration. Ne la partage pas dans une conversation ou un ticket.

### 2. Ajouter les secrets GitHub

Dans le dépôt GitHub, ouvre **Settings → Secrets and variables → Actions → New repository secret** et crée :

- `BACKUP_DATABASE_URL` : chaîne PostgreSQL du projet Supabase. Utilise de préférence la connexion directe. Si le réseau du runner ne prend pas en charge IPv6, utilise le **Session pooler**. N'utilise pas le Transaction pooler pour `pg_dump`.
- `BACKUP_AGE_RECIPIENT` : la clé publique `age1...` obtenue à l'étape précédente. Il s'agit d'une clé de chiffrement publique ; seule la clé privée doit rester secrète.

La chaîne de connexion doit viser le bon projet et comporter le paramètre SSL fourni par Supabase. Ne colle jamais le mot de passe de la base dans un fichier du dépôt.

### 3. Lancer une sauvegarde

Après fusion de ce changement dans `main) :

1. Ouvre l'onglet **Actions** du dépôt.
2. Sélectionne **Sauvegarde chiffrée de la base Postgres**.
3. Clique sur **Run workflow** en sélectionnant `main`.
4. Vérifie que l'exécution est verte, puis récupère l'artefact `mahay-postgres-public-...`.

Le dépôt étant public, ses lecteurs peuvent télécharger les artefacts. L'artefact ne contient donc que des données chiffrées avec la clé publique age. Sans la clé privée conservée hors de GitHub, son contenu n'est pas lisible.

Les artefacts GitHub expirent après 30 jours. Ce mécanisme est une première protection, pas une politique d'archivage longue durée. Il faudra ajouter une destination de sauvegarde externe privée et une exécution planifiée pour obtenir une véritable stratégie de sauvegarde quotidienne.

## Restaurer dans un environnement de test

Télécharge l'artefact, puis déchiffre-le avec la clé privée conservée hors de GitHub :

```bash
age --decrypt --identity mahay-backup-key.txt --output mahay-public.dump mahay-public.dump.age
pg_restore --list mahay-public.dump
```

Pour tester la restauration, crée d'abord une base ou un projet Supabase de test vide, puis restaure l'archive avec les outils PostgreSQL 17 :

```bash
pg_restore --no-owner --no-acl --dbname="$RESTORE_DATABASE_URL" mahay-public.dump
```

N'exécute pas cette commande sur la base de production pour un simple test. Vérifie ensuite les tables, les volumes de lignes et les parcours principaux sur l'environnement de test.

## Limites importantes

Cette sauvegarde **ne couvre pas** :

- les fichiers binaires stockés dans Supabase Storage (PDF, images, documents) ; `pg_dump` ne sauvegarde pas le contenu objet du bucket ;
- les schémas gérés par Supabase qui ne font pas partie de `public`, les rôles du projet et les paramètres du Dashboard ;
- les secrets Render, les clés API, les variables d'environnement et les services externes ;
- une rétention au-delà des 30 jours de l'artefact GitHub.

Le résultat ne doit donc pas être présenté comme une sauvegarde complète de reprise après sinistre. Une seconde étape doit protéger séparément les objets du bucket privé `documents` et stocker les archives chiffrées dans un emplacement externe indépendant.

## Références techniques

- [Connexion PostgreSQL Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres) : la connexion directe est recommandée pour les opérations `pg_dump`; le Session pooler est l'alternative IPv4.
- [Télécharger les artefacts GitHub Actions](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts) : un utilisateur doit disposer d'un accès en lecture au dépôt pour télécharger un artefact.
- [Render - Health checks](https://render.com/docs/health-checks) : les contrôles de disponibilité doivent rester rapides ; cette PR ne modifie pas les routes de santé utilisées par les services.
