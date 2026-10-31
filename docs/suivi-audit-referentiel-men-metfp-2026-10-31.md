# Suivi de l'audit des référentiels MEN / METFP — 31 octobre 2026

## Objet

Compléter le rapport initial `audit-referentiels-men-metfp-toamasina-2026-10-31.md` par un contrôle indépendant des pages officielles et une revue ciblée de la migration `MEN-RAPE-2026-09`.

Ce document ne transforme aucune donnée incertaine en donnée confirmée. Il ne modifie pas les programmes en base et ne déclenche aucun déploiement.

## 1. Contrôle du portail officiel MEN

Page consultée : https://plateforme.education.mg/bibliotheque-numerique/?lang=fr

L'index officiel distingue clairement :
- Programmes d'Études (PE) : collège T6 à T9, soit quatre documents ;
- Programmes d'Études (PE) : lycée T10 à T12, plus un document distinct « Coefficient et volume horaire niveau lycée » ;
- Répartitions annuelles (RAPE) : T6, T7, T8, T9, T10, T11 L/S/OSE et T12 L/S/OSE, soit onze documents.

Pages officielles de cours consultées :
- PE Collège : https://plateforme.education.mg/bibliotheque-numerique/course/view.php?id=981
- PE Lycée et coefficients : https://plateforme.education.mg/bibliotheque-numerique/course/view.php?id=982

Les pages de cours exposent les sections « PE COLLEGE », « PE LYCEE » et « COEFFICIENT ET VOLUME HORAIRE », mais l'extraction de page consultable ne révèle pas les pièces PDF téléchargeables ni leur version/date d'effet. Il n'est donc pas possible, à partir de ces seules pages, d'auditer les compétences, objectifs, chapitres détaillés, volumes horaires et coefficients. Le statut global doit rester **partiel**.

### Point de cohérence des séries à résoudre

La page MEN consacrée au lycée affiche encore les programmes « Seconde A C D », « Première A C D » et « Terminale A C D » :
https://www.education.gov.mg/systeme-educatif/lycee/

L'index des RAPE de septembre 2026 présente, lui, des documents T11 et T12 en séries L/S/OSE. Ces nomenclatures ne doivent pas être considérées comme équivalentes sans texte officiel de correspondance ou document ministériel explicitant leur relation. Ne pas renommer automatiquement A/C/D en L/S/OSE, ni inversement. Ajouter une table de correspondance versionnée seulement après obtention d'une preuve officielle.

## 2. Contrôle de l'édition annuelle 2026

Le dépôt contient la migration `alembic/versions/e2b7c9d4a1f6_referentiel_rape_2026_09.py`, qui crée la version `MEN-RAPE-2026-09`, la garde au statut `partiel`, et associe les programmes par niveau/série aux PDF RAPE individuels.

Le rapport initial inventorie les onze PDF et leurs matières. Les liens directs restent ceux indiqués dans le rapport initial. La RAPE est une répartition annuelle et ne remplace pas le PE complet.

Contrôles à conserver :
- 6e à 3e : ne pas déduire des options/séries qui ne figurent pas dans les sources ;
- Seconde : conserver séparément les intitulés de matières propres à T10, dont TIC ;
- Première : conserver les associations séparées par série et la terminologie TICE ;
- Terminale : vérifier les associations propres à chaque PDF L/S/OSE ; ne pas appliquer une liste générique issue d'une autre année ;
- conserver les PDF comme sources distinctes même lorsque leurs sommaires paraissent identiques ;
- les associations niveau/série/matière doivent pointer vers le PDF exact, et non seulement vers l'index de la bibliothèque.

La migration stocke une URL source directe sur les associations de programme. En revanche, la source de l'entité matière est l'index général MEN : c'est une source de catalogue, pas une preuve suffisante pour établir seule la présence d'une matière dans chaque classe/série. Pour les écrans et exports, privilégier la source portée par l'association programme-niveau-série.

## 3. Contrôle du portail officiel METFP : pagination vérifiée, inventaire public de 12

Pages consultées :
- https://www.metfp.gov.mg/formation/ressource
- https://www.metfp.gov.mg/formation/ressource?page=2
- https://www.metfp.gov.mg/media

La première page du catalogue affiche explicitement « 12 référentiels publiés », « dernière parution 14/09/2026 » et « 9 documents affichés sur 12 au total ». La seconde page affiche les 3 documents restants. Le constat précédent d'un seul document était donc incomplet : il correspondait à une vue ancienne ou à une extraction ne parcourant pas la pagination. **La divergence du nombre est résolue : l'index public annonce bien 12 référentiels.**

Inventaire des douze entrées, telles qu'affichées par le portail :
- RÉF N°62 — REFERENTIEL DE FORMATION (RF), 14/09/2026 ;
- RÉF N°61 — Agent de Maintenance en Système d’Impression, 14/09/2026 ;
- RÉF N°60 — INSTALLATEURE EN SYTEME SOLAIRES PV (ISSPV), 14/09/2026 ;
- RÉF N°59 — INSTALLATEURE EN SYTEME SOLAIRE PHOTOVOLTAIQUE, 14/09/2026 ;
- RÉF N°58 — AGENT de MAINTENANCE en SYSTÈME d’IMPRESSION, 14/09/2026 ;
- RÉF N°57 — AGENT D'ETUDE SPECIALISE EN SYSTEME PHOTOVOLTAIQUE -AESSPV-, 14/09/2026 ;
- RÉF N°56 — CFF Valet/Femme de chambre, 10/09/2026 ;
- RÉF N°55 — Cuisine, 10/09/2026 ;
- RÉF N°54 — Serveur Barman, 10/09/2026 ;
- RÉF N°53 — Patissier-Traiteur, 10/09/2026 ;
- RÉF N°52 — Formation de technicien en systèmes solaires photovoltaïques, 10/09/2026 ;
- RÉF N°15 — BTS Réceptionniste, 16/02/2026.

La médiathèque officielle recense les mêmes titres de référentiels et dates de publication. Cette double présence renforce la preuve d'existence et de publication des douze entrées. En revanche, les fichiers PDF ne sont pas directement récupérables dans le rendu textuel consulté : le portail demande de renseigner les coordonnées et le motif avant téléchargement. Il faut donc distinguer **publication vérifiée dans l'index** et **contenu intégral du PDF audité**. Les douze entrées sont confirmées comme notices publiées, mais les compétences, modules, durées, prérequis et certifications de chaque PDF restent à examiner.

Autre corpus, à ne pas confondre avec les douze notices ci-dessus : le METFP a annoncé le 10 juillet 2026 la remise officielle de 12 référentiels métiers et référentiels de formation BTP (six CAPS et six FPQ), destinés à une intégration dans le référentiel national. Cette annonce prouve la remise institutionnelle, mais ne permet pas d'affirmer que les douze documents sont les mêmes que les douze notices visibles dans le catalogue, ni de les importer sans leurs fichiers individuels : https://www.metfp.gov.mg/article/68.

Le METFP a aussi annoncé le 3 août 2026 la remise de référentiels concernant notamment les formations CFF dans les énergies renouvelables, les services d'hébergement et le conseil en orientation scolaire et professionnelle : https://www.metfp.gov.mg/article/77. Les notices du catalogue datées des 10 et 14 septembre sont des preuves plus directes de publication individuelle.

**Décision MITARIDALA :** mettre à jour le statut de l'inventaire national METFP à « 12 notices publiées — contenu PDF à auditer ». Ne pas marquer ces métiers comme offres ouvertes à Toamasina. Les offres ETFP locales restent à vérifier établissement par établissement pour 2026-2027.

À faire :
1. obtenir les douze PDF par le parcours officiel de téléchargement et relever titre, type, métier, certification, date, durée, prérequis et empreinte du fichier ;
2. rapprocher les doublons apparents (maintenance impression, solaire photovoltaïque) sans les fusionner avant comparaison des PDF ;
3. inventorier séparément les 12 référentiels BTP annoncés le 10 juillet et vérifier les pièces de chacun ;
4. séparer référentiel national publié, remise officielle annoncée et offre ouverte dans un centre ;
5. obtenir une preuve datée d'ouverture pour chaque offre de Toamasina/Atsinanana en 2026-2027.

## 4. Règles de publication pour MITARIDALA

| Élément | Décision actuelle |
|---|---|
| RAPE MEN septembre 2026 T6-T12 | Version annuelle de référence, statut global partiel |
| PE Collège T6-T9 | Identifié dans l'index ; contenu détaillé et date d'effet à récupérer |
| PE Lycée T10-T12 | Identifié dans l'index ; contenu détaillé et date d'effet à récupérer |
| Coefficients / volumes horaires lycée | Document identifié ; fichier et tableaux à auditer |
| Séries A/C/D vs L/S/OSE | Correspondance non établie ; ne pas fusionner |
| Offres d'établissements scolaires à Toamasina | À vérifier individuellement pour l'année concernée |
| Référentiels METFP 2026 | 12 notices publiées vérifiées ; PDF à auditer, offres locales distinctes |
| Offres ETFP locales 2026-2027 | Non confirmées sans preuve datée d'ouverture |

## 5. Étapes de clôture

- [ ] Obtenir les pièces jointes PDF PE Collège et PE Lycée depuis le portail MEN ou directement auprès du MEN.
- [ ] Obtenir le PDF « Coefficient et volume horaire niveau lycée » et vérifier les tableaux par classe/série.
- [ ] Relever les dates d'édition, arrêtés ou notes de service qui établissent l'année d'effet du PE et du RAPE.
- [ ] Obtenir la preuve officielle de correspondance des séries A/C/D et L/S/OSE, ou conserver deux nomenclatures distinctes.
- [ ] Contrôler les onze RAPE ligne par ligne contre la migration et les tests.
- [x] Réconcilier la pagination du catalogue METFP : 9 notices en page 1 + 3 en page 2 = 12 notices publiées.
- [ ] Télécharger et auditer les douze PDF METFP ; vérifier séparément les douze référentiels BTP annoncés.
- [ ] Vérifier établissement par établissement les offres scolaires et ETFP réellement ouvertes à Toamasina/Atsinanana en 2026-2027.
- [ ] Mettre à jour le rapport principal et le TODO seulement après ces contrôles.
- [ ] Exécuter tests SQLite, smoke PostgreSQL, CI complète et revue du PR avant toute fusion.
- [ ] Après fusion seulement, contrôler migrations, /health, /ready, logs et parcours catalogue en production.

## 6. Hors périmètre

Aucun changement n'est autorisé ici sur le moteur de rendu LaTeX/KaTeX, les quiz, le Tuteur IA ou les documents utilisateurs. Aucune migration de données de production, fusion ou mise en production ne doit être déclenchée par ce rapport.
