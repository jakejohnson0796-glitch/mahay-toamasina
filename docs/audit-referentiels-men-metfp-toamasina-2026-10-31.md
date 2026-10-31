# Audit des référentiels MEN, METFP et Toamasina

**Date de contrôle : 31 octobre 2026**  
**Périmètre : collège (6e à 3e), lycée (Seconde à Terminale), ETFP Atsinanana et référentiel universitaire de Toamasina.**  
**Statut : audit en cours ; les données dont la source ne permet pas de certifier l'actualité restent explicitement historiques ou à vérifier.**

## 1. Décision de publication

MITARIDALA doit distinguer trois notions qui ne sont pas interchangeables :

1. **Programme national** : matières et programmes liés à une édition et à une année scolaire précises.
2. **Présence d'un établissement ou d'un métier dans une cartographie ministérielle** : preuve de référencement, pas preuve d'ouverture d'une classe ou d'une session d'inscription.
3. **Offre réelle d'un établissement pendant une année donnée** : ne peut être confirmée qu'avec une preuve datée de l'établissement ou du ministère, puis validation administrative.

Un PDF du MEN intitulé « édition 2024 » et qui couvre explicitement 2024-2025 ne doit pas être présenté comme le programme 2026-2027. Les identifiants de version sont conservés et les versions historiques ne doivent pas être proposées comme versions courantes aux nouveaux profils.

## 2. MEN — programmes RAPE 2024-2025 vérifiés

Les onze PDF ci-dessous ont été contrôlés à partir de leurs sommaires, avec inspection visuelle des pages de table des matières. Ils indiquent l'édition 2024 et la répartition des contenus en cinq périodes pour 2024-2025.

| Classe | Source officielle | Matières du sommaire |
|---|---|---|
| T6 / 6e | [RAPE T6 2024-2025](https://www.education.gov.mg/wp-content/uploads/2024/09/RAPE-T6_2024_2025.pdf) | Malagasy, Français, Anglais, Éducation à la citoyenneté, Mathématiques, Sciences et technologie, Géographie, Histoire, Arts, EPS |
| T7 / 5e | [RAPE T7 2024-2025](https://www.education.gov.mg/wp-content/uploads/2024/09/RAPE-T7_2024_2025.pdf) | Malagasy, Français, Anglais, Éducation à la citoyenneté, Mathématiques, Sciences physiques, SVT, Géographie, Histoire, Monde du travail, Arts, EPS |
| T8 / 4e | [RAPE T8 2024-2025](https://www.education.gov.mg/wp-content/uploads/2024/09/RAPE-T8_2024_2025.pdf) | Malagasy, Français, Anglais, Éducation à la citoyenneté, Mathématiques, Sciences physiques, SVT, Géographie, Histoire, Monde du travail, Arts, EPS |
| T9 / 3e | [RAPE T9 2024-2025](https://www.education.gov.mg/wp-content/uploads/2024/09/RAPE-T9_2024_2025.pdf) | Malagasy, Français, Anglais, Éducation à la citoyenneté, Mathématiques, Sciences physiques, SVT, Géographie, Histoire, Monde du travail, Arts, EPS |
| T10 / Seconde | [RAPE T10 2024-2025](https://www.education.gov.mg/wp-content/uploads/2024/09/RAPE-T10_2024_2025.pdf) | Malagasy, Français, Anglais, Histoire, Géographie, Mathématiques, Sciences physiques et chimiques, SVT, Sciences économiques et sociales, Éducation à la citoyenneté, EPS, TICE |
| T11 / Première L | [RAPE T11 L 2024-2025](https://www.education.gov.mg/wp-content/uploads/2024/09/RAPE-T11-L_2024_2025.pdf) | Malagasy, Français, Anglais, Histoire, Géographie, Mathématiques, Sciences physiques, SVT, SES, Éducation à la citoyenneté, Philosophie, EPS, TICE |
| T11 / Première S | [RAPE T11 S 2024-2025](https://www.education.gov.mg/wp-content/uploads/2024/09/RAPE-T11-S_2024_2025.pdf) | Malagasy, Français, Anglais, Histoire, Géographie, Mathématiques, Sciences physiques et chimiques, SVT, SES, Éducation à la citoyenneté, Philosophie, EPS, TICE |
| T11 / Première OSE | [RAPE T11 OSE 2024-2025](https://www.education.gov.mg/wp-content/uploads/2024/09/RAPE-T11-OSE_2024_2025.pdf) | Malagasy, Français, Anglais, Histoire, Géographie, Mathématiques, Sciences physiques et chimiques, SVT, SES, Éducation à la citoyenneté, Philosophie, EPS, TICE |
| T12 / Terminale L | [RAPE T12 L 2024-2025](https://www.education.gov.mg/wp-content/uploads/2024/09/RAPE-T12-L_2024_2025.pdf) | Malagasy, Français, Anglais, Histoire, Géographie, Mathématiques, Sciences physiques et chimiques, SVT, SES, Philosophie |
| T12 / Terminale S | [RAPE T12 S 2024-2025](https://www.education.gov.mg/wp-content/uploads/2024/09/RAPE-T12-S_2024_2025.pdf) | Malagasy, Français, Anglais, Histoire, Géographie, Mathématiques, Sciences physiques et chimiques, SVT, SES, Philosophie, EPS |
| T12 / Terminale OSE | [RAPE T12 OSE 2024-2025](https://www.education.gov.mg/wp-content/uploads/2024/09/RAPE-T12-OSE_2024_2025.pdf) | Malagasy, Français, Anglais, Histoire, Géographie, Mathématiques, Sciences physiques et chimiques, SVT, SES, Philosophie |

**Contrôles qui doivent rester dans le code et les tests :**

- T6 utilise « Sciences et technologie » ; il ne faut pas lui attribuer automatiquement les deux matières « Sciences physiques » et « SVT » des classes T7 à T9.
- T7, T8 et T9 ont « Monde du travail » et « Arts ».
- En Première, les trois séries L, S et OSE ont EPS et TICE, mais L distingue « Sciences physiques » du libellé « Sciences physiques et chimiques » des autres séries.
- En Terminale, l'EPS est présente en S, mais absente des sommaires L et OSE. TICE et Éducation à la citoyenneté ne figurent pas dans les sommaires de Terminale L/S/OSE contrôlés.
- Les séries L, S et OSE doivent être attachées à T11 et T12 séparément. Une liste générique partagée entre toutes les classes ou toutes les séries est incorrecte.

La migration `d1a9f4c7e2b6_referentiel_rape_2024_2025.py` ajoute cette édition sous le code `MEN-RAPE-2024-2025-historique`, avec sept niveaux, six options de série (L/S/OSE en T11 et T12) et les associations exactes matière-classe-série. Elle est idempotente et ne supprime pas le catalogue RAPS existant. Le statut de la version est `historique` : elle reste consultable, mais les sélecteurs courants et la synchronisation des cercles ne doivent pas la choisir automatiquement.

## 3. MEN — publication RAPE de septembre 2025 : blocage de vérification

La page officielle des actualités MEN contient une publication « RAPE : Primaire, Collège, Lycée » et propose les fichiers suivants :

- [RAPE Collège (archive RAR)](https://www.education.gov.mg/wp-content/uploads/2025/09RAPE_%20coll%C3%A8ge.rar)
- [RAPE Lycée (archive RAR)](https://www.education.gov.mg/wp-content/uploads/2025/09RAPE_Lyc%C3%A9e.rar)
- [Page officielle des actualités MEN](https://www.education.gov.mg/actus/)

Au contrôle du 31 octobre 2026, l'ouverture et le téléchargement des deux archives renvoient HTTP 500. Leur contenu, leur date d'effet, leurs listes de matières et leurs éventuelles correspondances avec les séries du référentiel n'ont donc pas pu être vérifiés. Cette édition est le prochain bloc de travail prioritaire : ne pas l'importer à partir des seuls titres de fichiers ni inventer les matières.

**Conséquence :** MITARIDALA ne doit pas annoncer que son catalogue scolaire est à jour pour 2026-2027. Les programmes PDF 2024-2025 restent identifiés comme historiques. Le catalogue RAPS initial reste explicitement partiel ; les établissements doivent fournir ou confirmer la version effectivement appliquée avant de sélectionner un régime RAPS/RAPE comme offre locale actuelle.

## 4. METFP — référentiels ETFP publiés en 2026

Le portail du METFP décrit son catalogue comme contenant des référentiels de compétences, de formation, de certification et d'évaluation : [Référentiels et ressources pédagogiques](https://metfp.gov.mg/formation/ressource). Au 31 octobre 2026, l'index officiel affiche 12 référentiels, dernière parution au 14 septembre 2026 ; il montre 9 documents sur la première page et 3 sur la seconde. Cela établit qu'un corpus de 12 éléments est annoncé, mais ne prouve pas que chaque PDF a été téléchargé, lu et rapproché du catalogue MITARIDALA.

Il existe aussi des annonces officielles de remises de référentiels à ne pas confondre avec les 12 entrées déjà visibles dans le catalogue web :
- Le 10 juillet 2026, le METFP annonce la remise de **12 référentiels métiers et référentiels de formation pour le BTP**, répartis en 6 CAPS et 6 FPQ. Cette annonce indique une intégration prévue au référentiel national ; elle ne fournit pas à elle seule les PDF métier à injecter ni la liste des établissements qui ouvrent ces formations : [annonce officielle METFP — BTP](https://www.metfp.gov.mg/article/68).
- Le 23 septembre 2026, le METFP annonce la remise de référentiels et de documents d'organisation pédagogique/équipements pour la gestion des déchets solides ; l'article indique un démarrage prévu au Centre de Formation d'Ankadinandriana, DRETFP Analamanga, avec extension progressive : [annonce officielle METFP — gestion des déchets](https://metfp.gov.mg/article/96).
- Le portail indexe également des référentiels de septembre 2026 en maintenance des systèmes d'impression, solaire photovoltaïque, cuisine, serveur-barman, valet/femme de chambre et pâtisserie-traiteur.

Ces éléments doivent être inventoriés dans une table de suivi distincte avec le type de preuve (PDF publié, remise officielle, offre locale annoncée), la date, le diplôme/certification, le métier canonique et la disponibilité documentaire. Ne pas les ajouter comme lignes actives d'établissement tant que les fichiers et la localisation d'ouverture ne sont pas vérifiés.

Les intitulés visibles parmi les parutions 2026 comprennent notamment :

- Agent de maintenance en système d'impression ;
- Installateur en systèmes solaires photovoltaïques, avec plusieurs référentiels distincts ;
- Agent d'étude spécialisé en système photovoltaïque ;
- Serveur / Barman ;
- Cuisine ;
- CFF Valet / Femme de chambre ;
- Pâtissier-Traiteur ;
- Formation de technicien en systèmes solaires photovoltaïques ;
- BTS Réceptionniste.

Ces publications actualisent la preuve de l'existence de référentiels nationaux pour certains métiers. Elles ne prouvent pas qu'un centre donné à Toamasina ouvre une session dans ce métier pendant l'année 2026-2027. Avant de relier ces référentiels aux parcours locaux, télécharger les PDF individuels, confirmer leur contenu et leur niveau/certification, puis documenter l'alias éventuel vers le métier déjà présent dans MITARIDALA.

Le calendrier METFP de l'année scolaire 2026-2027 est également publié sur le [portail officiel](https://metfp.gov.mg/). Il ne doit pas être confondu avec une liste d'offres par établissement.

## 5. ETFP — établissements d'Atsinanana déjà présents dans le dépôt

Les migrations de cartographie METFP recensent les établissements suivants dans la région Atsinanana :

| Établissement | Parcours explicitement associés dans l'instantané du dépôt |
|---|---|
| CFP Antanambao Manampotsy | Chef d'équipe de chantier ; menuisier bois |
| LTP Brickaville | Agriculture maraîchère ; installation photovoltaïque ; structures métalliques ; chef d'équipe BTP ; restauration ; aviculture |
| CFP Toamasina | Couture textile ; cuisine |
| LTP Toamasina | Structures métalliques ; mécanique générale ; agent d'agriculture ; gestion comptable ; dessin/projet BTP |
| CFP Foulpointe | Menuiserie bois ; valet/femme de chambre ; barman ; pâtisserie ; cuisine ; traiteur ; restauration de meubles |

La cartographie est une preuve de référencement des établissements et des métiers listés à sa date de consultation. Les offres initiales importées restent `a_verifier`, avec `annee_scolaire = NULL`. Elles ne sont donc pas censées apparaître comme inscriptions confirmées en 2026-2027. Garder cette règle jusqu'à réception d'une preuve datée (avis d'ouverture, fiche de rentrée, liste d'admission ou validation officielle) pour chaque offre.

Points d'audit encore ouverts pour Atsinanana :

- confirmer le nom administratif, le type (LTP/CFP/CFPF), la commune et, si disponible, le code de chaque établissement avec le METFP ;
- comparer chaque métier de la cartographie avec les référentiels RF/RFC les plus récents et ne pas fusionner deux intitulés différents sur la seule ressemblance du nom ;
- obtenir la session/année d'ouverture réelle de chaque offre pour 2026-2027 ;
- vérifier les niveaux et diplômes (certificat, qualification, technicien, technicien supérieur, BTS) dans le document du métier, sans les déduire du nom du centre ;
- ne pas désactiver une offre existante sans historique ni validation humaine.

## 6. Université de Toamasina — périmètre et éléments non publiés

Le fichier source versionné dans le dépôt recense actuellement 157 lignes de formation, 24 mentions et six composantes : Faculté DEG (29 lignes / 3 mentions), FST (25 / 2), ENS (61 / 11), FLSH (28 / 6), ISSEDD-GRENE (5 / 1) et ITPT (9 / 1). Les niveaux présents vont de L1 à M2, sauf ITPT qui est recensé de L1 à L3. Les données restent séparées du référentiel collège/lycée.

**Limite de fraîcheur réglementaire :** le portail MESUPRES affiche actuellement que sa liste d'établissements habilités est « en cours de mise à jour ». Le dernier PDF de liste générale retrouvé dans ce contrôle est daté d'août 2022. Les lignes universitaires qui reposent sur ce document constituent des preuves historiques d'habilitation/intitulé, pas une preuve automatique d'ouverture en 2026-2027. Les sources des composantes DEG et FST incluent aussi des pages universitaires et un formulaire FST 2023-2024 ; vérifier chaque maquette et la disponibilité de la rentrée actuelle avec la composante avant de déclarer une offre annuelle actuelle. Sources : [page MESUPRES des établissements](https://www.mesupres.gov.mg/etablissements), [liste MESUPRES d'août 2022](https://www.mesupres.gov.mg/assets/front/documents/etablissements_habilites/liste_des_institutions_superieures_mise_a_jour_aout_2022.pdf).

Les éléments identifiés comme incomplets ou nécessitant une preuve plus récente ne doivent pas être publiés comme offres garanties :

- Gestion / CCA : M1 et M2 sont désormais tous deux en attente. Le seul support M2 trouvé est une évaluation de cours hébergée sur Scribd ; il ne prouve ni habilitation, ni maquette officielle, ni ouverture de rentrée. La ligne M2 a été rétrogradée de « Confirmé » à « À vérifier » et doit être exclue des sélecteurs et cercles jusqu'à preuve officielle ;
- ESPT : composante/formations signalées par des sources historiques, mais parcours et niveaux 2026-2027 à confirmer ;
- Faculté de Médecine : niveaux/parcours courants à confirmer par la faculté.

Ne pas inventer de niveau L/M, de parcours, de domaine ou d'ouverture annuelle à partir d'un simple support de cours ou d'une habilitation ancienne.

## 7. Règles techniques de publication et de non-régression

- Une version de référentiel possède un code et une année propres ; ne pas écraser les versions historiques.
- Les matières sont des associations version + niveau + option/série + matière. La matière seule n'indique pas le programme auquel elle appartient.
- Un profil étudiant conserve la version à travers son `niveau_scolaire_id`. Quiz, Tuteur, documents et offres administratives doivent résoudre la version depuis ce niveau, pas depuis la version nationale la plus récente.
- Les listes par défaut et la synchronisation automatique des cercles ignorent les versions `historique` / `archive`. L'accès explicite à une ancienne version reste possible.
- Les offres locales restent invisibles comme « confirmées » sans statut vérifié, source, année, date de validation et valideur.
- Les sources bloquées, les associations ambiguës et les niveaux absents doivent apparaître comme points à vérifier, jamais être comblés par supposition.
- Aucun traitement de données ne doit modifier le moteur de rendu mathématique LaTeX/KaTeX dans le cadre de ce chantier.

## 8. Critères de clôture avant fusion et déploiement

- [ ] obtenir et auditer le contenu des deux archives RAPE MEN de septembre 2025 ;
- [ ] déterminer avec le MEN l'édition qui régit réellement le programme scolaire 2026-2027 ;
- [ ] confirmer RAPS/RAPE appliqué par établissement à Toamasina/Atsinanana ;
- [ ] rapprocher chaque référentiel METFP 2026 du parcours métier canonique et vérifier les niveaux/certifications ;
- [ ] obtenir les preuves d'ouverture des offres ETFP locales 2026-2027 ;
- [ ] faire passer les tests SQLite et PostgreSQL de migration, l'idempotence, l'API, l'inscription, documents, Quiz, Tuteur et cercles ;
- [ ] exécuter la CI complète en vert ;
- [ ] faire la revue finale du PR avant fusion ; aucun déploiement tant que la validation n'est pas complète.

**État au moment de cet audit :** données RAPE 2024-2025 ajoutées dans une version historique distincte sur une branche de correction ; aucune modification de production, aucune fusion et aucun déploiement.
