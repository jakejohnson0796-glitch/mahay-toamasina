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
- Les notifications liées à un devoir, une note, une présence, un rappel ou une fiche
  de cours portent leur cours d'origine ; leur affichage, ouverture et marquage
  comme lu revérifient l'inscription active. Les alertes historiques sans cours
  identifiable sont masquées par prudence ; les notifications générales restent visibles.
- Les anciens cours dont le professeur a une seule appartenance pédagogique
  active sont rattachés automatiquement. Les cours avec plusieurs appartenances,
  ou uniquement des appartenances suspendues, sont placés en quarantaine :
  pas d'accès étudiant ni de code d'invitation jusqu'à l'affectation explicite
  par un administrateur dans « Cours à affecter ».

Les entités dépendant d'un cours (séances, devoirs, rendus, présences, notes et
fiches de révision) héritent de son périmètre par leur clé étrangère vers Cours.
Les ressources pédagogiques générales et les cercles conservent leurs règles
distinctes : ils ne deviennent pas implicitement des ressources privées d'un
établissement.

## Administration

La console d'administration de la plateforme peut créer un établissement,
nommer les responsables, affecter tout rôle institutionnel et désactiver une
appartenance. Elle conserve les droits d'exploitation globaux.

Un responsable dispose de /etablissement/tableau-de-bord, limité aux
établissements où son appartenance responsable est active. Il peut consulter la
liste des membres de son périmètre, importer jusqu'à 500 étudiants par fichier
CSV/XLSX, rattacher un compte existant comme professeur ou étudiant, et
désactiver les appartenances professeur/étudiant de son établissement. Il ne
peut pas nommer un autre responsable, modifier les rôles globaux, agir sur un
autre établissement ni consulter ses effectifs nominatifs.

Les mots de passe provisoires des imports sont affichés une seule fois dans une
réponse sans cache ; les comptes doivent les remplacer à la première connexion.
Les affectations et désactivations revérifient le rôle responsable et le tenant
côté serveur à chaque requête.

## Vérifications requises avant fusion

- Exécuter les tests unitaires de séparation des tenants et la suite CI complète.
- Rejouer les migrations PostgreSQL sur une copie représentative de la base.
- Vérifier les cours historiques et les comptes institutionnels préexistants.
- Tester deux établissements en parallèle, y compris les WebSockets et les
  téléchargements de copies.
- Vérifier le comportement de retrait d'un membre et du dernier responsable.
- Vérifier les performances des listes et rapports avec des effectifs réels.
