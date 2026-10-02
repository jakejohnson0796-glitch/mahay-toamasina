# Checklist release officielle — Gasy Mahay

Cette checklist doit etre verte avant de rendre une version publique.

## 1. Migrations PostgreSQL

    python scripts/verify_migrations.py
    alembic upgrade head
    alembic upgrade head
    alembic current

La CI execute ces commandes sur PostgreSQL 16. Le second `upgrade head` est
volontaire : une release ne doit pas casser lorsque le serveur redemarre ou
rejoue la commande de migration.

## 2. Demarrage

- `/health` doit repondre `200` ; `/ready` doit passer a `200` apres l'initialisation des donnees.
- Les migrations sont executees avant de servir l'application.
- La maintenance lourde du referentiel est lancee en arriere-plan afin de ne
  pas bloquer le health check.

## 3. Parcours critiques

Verifier au minimum en production-like :

- inscription → connexion → deconnexion ;
- mot de passe oublie ;
- tableau de bord ;
- recherche et adhesion a un cercle ;
- chat et classe virtuelle ;
- depot et telechargement d'un document ;
- quiz / tuteur IA ;
- notifications ;
- fonctions admin.

## 4. Securite

- vraie `SESSION_SECRET_KEY` en production ;
- HTTPS actif ;
- cookies `__Host-session`, `Secure`, `SameSite=Lax` ;
- CSP sans `unsafe-inline` ;
- autorisations admin cote serveur ;
- validation des uploads ;
- limitation de debit sur les actions sensibles ;
- secrets uniquement dans l'environnement de l'hebergeur ;
- aucune cle serveur dans le navigateur ou le depot.

## 5. Exploitation

- verifier les variables Render/Supabase ;
- verifier les sauvegardes PostgreSQL ;
- conserver le commit precedent pour rollback ;
- verifier les logs de demarrage et `/health` apres redeploiement ;
- verifier la restauration d'une sauvegarde sur un environnement de test.

## 6. Publication

Publier seulement apres un run CI vert et un smoke test production-like vert.
