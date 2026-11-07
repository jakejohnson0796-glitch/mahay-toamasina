# Runbook de sauvegarde et de retour arrière — PR #326

## Périmètre et limites

Ce runbook couvre le code de la PR multiétablissements et la migration Alembic
`h1c7e9a2b4d6`. Une branche GitHub protège le code ; elle ne sauvegarde ni la
base PostgreSQL externe ni les objets Supabase Storage.

Les sauvegardes de code préparées le 7 novembre 2026 sont :

- Avant fusion (état actuel de `main`) :
  `backup/pre-merge-pr-326-main-20261107`
  — commit `3691b430ddd4fca69457c44ab32ed5dad89bdc75`.
- Candidat de la PR :
  `backup/pr-326-candidate-20261107`
  — commit `8e8daf20fac9a0bf72c41117bdbf0ba866f084fd`.

Ces références sont des points de restauration du dépôt, pas des sauvegardes de
données ou des images Render.

## Conditions obligatoires avant une migration de production

Un opérateur adulte autorisé doit, dans les consoles privées du fournisseur de
base et du stockage :

1. Identifier les bases réellement utilisées par les deux services Render et
   confirmer si elles sont distinctes ou partagées.
2. Créer une sauvegarde PostgreSQL exploitable ou confirmer le PITR disponible,
   noter l'heure exacte et la révision Alembic, puis vérifier la procédure de
   restauration sur un environnement séparé. Ne jamais restaurer une sauvegarde
   de test sur la production.
3. Sauvegarder séparément les objets Supabase Storage si la politique de
   continuité l'exige. Une sauvegarde SQL ne contient pas nécessairement les
   fichiers du bucket.
4. Vérifier, sans partager de secret, que le rôle effectif de l'application
   peut lire et écrire dans `membre_etablissement`. La même variable
   `DATABASE_URL` est utilisée par l'engine applicatif pour les migrations et
   les requêtes. Le rôle qui crée la table en devient propriétaire ; PostgreSQL
   laisse le propriétaire contourner RLS sauf si `FORCE ROW LEVEL SECURITY`
   est activé. Vérifier le propriétaire réel et `relforcerowsecurity`, pas
   seulement `rolbypassrls`.
5. Vérifier les migrations et les parcours de l'application dans un
   environnement de préproduction avant toute activation pour les utilisateurs.

Aucune chaîne de connexion, donnée personnelle, sauvegarde ou clé ne doit être
placée dans GitHub, les journaux ou cette conversation.

## Contrôle SQL privé, en lecture seule

À exécuter uniquement par l'opérateur autorisé dans la console SQL privée de
chaque base concernée, après que la table existe :

```sql
SELECT
    current_user AS role_effectif,
    r.rolsuper,
    r.rolbypassrls,
    pg_get_userbyid(c.relowner) AS proprietaire_table,
    (c.relowner = r.oid) AS role_est_proprietaire,
    c.relrowsecurity AS rls_active,
    c.relforcerowsecurity AS rls_forcee,
    (SELECT COUNT(*)
       FROM pg_policies p
      WHERE p.schemaname = n.nspname
        AND p.tablename = c.relname) AS nombre_politiques
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_roles r ON r.rolname = current_user
WHERE n.nspname = current_schema()
  AND c.relname = 'membre_etablissement';
```

Pour la configuration actuelle (RLS actif, aucune politique, RLS non forcé),
le compte applicatif doit être le propriétaire de la table, ou avoir
`rolbypassrls`/`rolsuper`. Confirmer également que ce même rôle possède les
droits SQL nécessaires. Ne transmettre que les indicateurs booléens et le
nombre de politiques, sans nom de rôle ni nom de base.

## Stratégie de retour arrière

### Incident applicatif sans défaut de migration

Privilégier un correctif en avant (« forward fix »). Ne pas revenir directement
à l'image Render pré-PR : elle ne contient pas la révision Alembic
`h1c7e9a2b4d6`, alors que la base peut déjà l'avoir enregistrée. Son démarrage
peut échouer avec une révision inconnue.

Un retour arrière du seul code vers l'ancienne application n'est pas déclaré
sûr : l'ancien code ne connaît pas les nouveaux contrôles de cloisonnement.
Il pourrait ignorer les rattachements institutionnels et ne plus appliquer les
restrictions d'accès introduites par la PR.

### Retour complet à la version précédente

À décider et exécuter par l'opérateur adulte autorisé, avec les services en
maintenance et les écritures arrêtées :

1. Confirmer le dernier point de sauvegarde PostgreSQL cohérent et la stratégie
   de conservation des écritures intervenues depuis ce point.
2. Si des fichiers ont changé, restaurer aussi le stockage concerné selon sa
   propre procédure.
3. Restaurer la base vers le point antérieur à la migration au moyen du
   mécanisme validé du fournisseur. Ne pas exécuter aveuglément
   `alembic downgrade` : la migration supprime notamment des colonnes et des
   structures ajoutées.
4. Déployer le code correspondant exactement au commit sauvegardé
   `3691b430ddd4fca69457c44ab32ed5dad89bdc75`, puis confirmer que la révision
   Alembic et l'application correspondent à cet état.
5. Vérifier les contrôles de santé, la connexion, les parcours essentiels, les
   journaux et les métriques avant de sortir du mode maintenance.

Ne jamais utiliser un simple retour Render vers l'ancienne image lorsque la
base a déjà migré. Ne jamais déplacer de force `main` vers une ancienne
révision : utiliser une restauration contrôlée et traçable.

## État de préparation connu au 7 novembre 2026

- Les deux sauvegardes GitHub ci-dessus ont été créées et relues.
- Le run GitHub Actions `42389989860` a réussi sur le commit candidat
  `8e8daf20fac9a0bf72c41117bdbf0ba866f084fd`.
- Aucune sauvegarde de la base externe, aucun test de restauration et aucune
  vérification du rôle PostgreSQL des services Render n'ont été réalisés par
  cet outil.
- La fusion et le déploiement de la PR #326 restent donc bloqués tant que les
  vérifications privées ci-dessus n'ont pas été confirmées.
