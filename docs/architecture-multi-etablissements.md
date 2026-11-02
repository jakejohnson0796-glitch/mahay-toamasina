# Architecture multiétablissements MITARIDALA

## Principes

Les comptes peuvent appartenir à plusieurs établissements avec
MembreEtablissement. Chaque appartenance porte un rôle indépendant du rôle
global du compte : responsable, professeur ou étudiant. Une appartenance
inactive ne donne aucun accès. Une affectation est créée ou réactivée par un
administrateur de la plateforme.

Un cours institutionnel porte un champ institution_id. La migration reconstitue
les appartenances correspondant aux comptes qui portaient déjà
Utilisateur.institution_id. Elle rattache aussi les cours existants au tenant
de leur professeur lorsque celui-ci possède un seul établissement actif et un
rôle pédagogique explicite. Un cours dont le périmètre reste ambigu conserve
son institution_id nul ; il n'est pas déplacé par supposition.

## Règles d'accès aux cours

- Un administrateur global conserve son accès d'exploitation.
- Un responsable actif voit et gère les cours de son seul établissement.
- Un professeur actif gère ses propres cours dans l'établissement auquel il
  est affecté ; il ne peut pas gérer les cours d'un autre établissement.
- Un étudiant doit avoir une appartenance active de rôle étudiant dans le même
  établissement et une inscription au cours.
- L'appartenance est revérifiée côté serveur pour les codes d'invitation, les
  devoirs, les rendus, les notes, les fiches et les WebSockets.
- Un professeur affecté à plusieurs établissements doit choisir explicitement
  le périmètre lors de la création d'un cours.
- La désactivation d'une appartenance prend effet immédiatement ; le dernier
  responsable actif d'un établissement ne peut pas être désactivé.

Les entités dépendant d'un cours (séances, devoirs, rendus, présences, notes et
fiches de révision) héritent de son périmètre par leur clé étrangère vers Cours.
Les ressources pédagogiques générales et les cercles conservent leurs règles
distinctes : ils ne deviennent pas implicitement des ressources privées d'un
établissement.

## Administration

La console d'administration de la plateforme peut créer un établissement,
importer les étudiants, affecter un compte existant à un rôle institutionnel
et désactiver une appartenance. Les mots de passe provisoires des imports ne
sont pas ajoutés au modèle d'appartenance.

Un responsable dispose de /etablissement/tableau-de-bord, qui ne présente que
des agrégats et les cours de ses établissements actifs. Les données nominatives
des étudiants et les cours d'autres institutions ne sont pas présentés dans
ce tableau de bord.

## Vérifications requises avant fusion

- Exécuter les tests unitaires de séparation des tenants et la suite CI complète.
- Rejouer les migrations PostgreSQL sur une copie représentative de la base.
- Vérifier les cours historiques et les comptes institutionnels préexistants.
- Tester deux établissements en parallèle, y compris les WebSockets et les
  téléchargements de copies.
- Vérifier le comportement de retrait d'un membre et du dernier responsable.
- Vérifier les performances des listes et rapports avec des effectifs réels.
