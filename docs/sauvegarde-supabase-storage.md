# Sauvegarde chiffrée de Supabase Storage

## Périmètre

Le workflow `.github/workflows/storage-backup.yml` exporte **tous les buckets présents dans le projet Supabase** au moment de l'exécution, sans se limiter au bucket `documents`.

Il utilise les routes officielles de l'API Storage pour :
- lister les buckets ;
- parcourir récursivement leurs objets par préfixe et pagination ;
- télécharger chaque objet ;
- calculer sa taille réelle et son empreinte SHA-256 ;
- écrire un manifeste avec les noms de buckets, leur visibilité, les chemins, tailles, empreintes, types MIME, règles cache et dates fournies par Storage.

Le script échoue si l'API ne répond pas, si un objet est incomplet, si le chemin retourné est dangereux ou si aucun bucket n'est trouvé. Une exécution incomplète ne produit donc pas d'archive publiable.

Le workflow construit une archive temporaire, vérifie son intégrité, la chiffre avec age, supprime les fichiers en clair, puis publie uniquement `mahay-storage.tar.gz.age`. Le fichier chiffré est téléversé directement, sans ZIP supplémentaire, avec une rétention de 30 jours.

## Configuration GitHub requise

Dans le dépôt, ouvre **Settings → Secrets and variables → Actions → New repository secret** et ajoute :

| Secret | Valeur |
|---|---|
| `BACKUP_SUPABASE_URL` | URL HTTPS de l'API du projet Supabase |
| `BACKUP_STORAGE_SERVICE_KEY` | Clé serveur Supabase de rôle service, utilisée uniquement pour lire les buckets et objets privés |
| `BACKUP_AGE_RECIPIENT` | Clé publique age `age1...` déjà utilisée pour la sauvegarde PostgreSQL |

La clé serveur a des privilèges étendus et contourne les politiques RLS. Elle doit rester exclusivement dans GitHub Secrets et dans les variables serveur de confiance. Ne la place jamais dans le dépôt, un artefact, un ticket ou une conversation.

Le workflow sépare les identifiants : la clé Supabase est disponible uniquement pendant l'étape d'export ; la clé publique age est disponible pendant le chiffrement ; aucune de ces valeurs n'est transmise à l'étape de publication.

## Lancer la sauvegarde

1. Ouvre l'onglet **Actions** du dépôt.
2. Sélectionne **Sauvegarde chiffrée Supabase Storage**.
3. Clique sur **Run workflow** en sélectionnant `main`.
4. Vérifie que les étapes d'export, de vérification et de chiffrement sont réussies.
5. Télécharge l'artefact `mahay-storage-...`.

Le dépôt GitHub étant public, les artefacts sont accessibles aux lecteurs du dépôt. Ils ne contiennent cependant que le flux chiffré age. Conserve la clé privée hors de GitHub, dans un emplacement sûr, séparé des sauvegardes.

## Déchiffrer sous Windows

Après avoir téléchargé le fichier `.age`, ouvre PowerShell dans le dossier qui contient l'archive et ta clé privée age :

```powershell
age.exe --decrypt --identity .\mahay-backup-key.txt --output .\mahay-storage.tar.gz .\mahay-storage.tar.gz.age
tar.exe -xzf .\mahay-storage.tar.gz -C .\mahay-storage-restaure
```

Le dossier restauré contient un répertoire par bucket et `storage-manifest.json`. Le manifeste donne les tailles et empreintes SHA-256 ; tu peux contrôler un fichier avec :

```powershell
Get-FileHash .\mahay-storage-restaure\documents\chemin\fichier.pdf -Algorithm SHA256
```

## Restaurer les objets vers un projet de test

La restauration doit d'abord être répétée dans un **projet Supabase vide de test**, jamais directement dans la production.

1. Crée les buckets listés dans `storage-manifest.json`, en reprenant leur nom, leur visibilité publique/privée et leurs limites.
2. Installe et authentifie la Supabase CLI sur ton poste.
3. Pour chaque bucket, copie son dossier local vers le bucket distant correspondant. Exemple pour le bucket `documents` avec le projet de test déjà lié :

```powershell
supabase storage cp --recursive --experimental --linked .\mahay-storage-restaure\documents ss:///documents/
```

La CLI prend en charge la copie récursive de répertoires vers Storage. Vérifie la syntaxe et le projet distant sélectionné avant d'exécuter la copie. Ne lance pas cette opération contre le projet de production lors d'un exercice de restauration.

La copie recrée les objets et leurs entrées de stockage, avec de nouveaux identifiants internes. Les chemins des fichiers sont conservés, ce qui permet aux enregistrements applicatifs qui référencent ces chemins de continuer à les retrouver. Le manifeste conserve les informations MIME/cache/date disponibles au moment de la sauvegarde, mais une copie CLI récursive ne garantit pas de reproduire à l'identique toutes les métadonnées internes, propriétaires ou identifiants d'origine.

## Limites connues

- Ce workflow est manuel. Il ne constitue pas une sauvegarde quotidienne tant qu'une planification explicite n'est pas ajoutée.
- Les artefacts expirent après 30 jours ; conserve les archives importantes ailleurs, dans un espace privé et chiffré, pour une rétention longue.
- Une liste puis un téléchargement objet par objet n'est pas un instantané transactionnel. Pour un backup important, évite les changements de fichiers pendant l'export et contrôle le manifeste après téléchargement.
- Les paramètres de bucket sont documentés dans le manifeste, mais la restauration des buckets et politiques ne se fait pas automatiquement.
- Les propriétaires, UUID internes et paramètres gérés de Supabase ne sont pas recréés à l'identique par la copie des objets.
- Cette archive ne remplace pas la sauvegarde PostgreSQL décrite dans [sauvegarde-et-restauration.md](./sauvegarde-et-restauration.md). Les deux sauvegardes sont complémentaires.

## Sources techniques

- [API Storage Supabase](https://supabase.github.io/storage/) : routes de listing des buckets, listing des objets et téléchargement.
- [Supabase CLI — storage cp](https://supabase.com/docs/reference/cli/supabase-storage-cp) : copie simple ou récursive d'objets.
- [Téléchargement d'objets](https://supabase.com/docs/guides/storage/management/download-objects) : méthodes officielles de récupération des fichiers.
- [GitHub upload-artifact](https://github.com/actions/upload-artifact/releases/tag/v7.0.2) : prise en charge du téléversement direct sans ZIP supplémentaire.
