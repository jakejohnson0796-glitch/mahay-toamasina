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

## 3. Contrôle du portail officiel METFP : divergence à résoudre

Page consultée : https://metfp.gov.mg/formation/ressource

La page rendue lors de ce contrôle affiche « 1 référentiel publié », daté du 16/02/2026, et un seul résultat : « DOCUMENTS REFERENTIELS BTS RECEPTIONNISTE_VF (2025) ». Le rapport initial, établi à partir d'une consultation antérieure, mentionnait douze entrées de référentiels publiées jusqu'au 14/09/2026.

Ces deux constats ne concordent pas. La page peut être filtrée, paginée, mise en cache ou avoir changé depuis le précédent relevé ; la consultation présente ne permet pas d'expliquer la divergence. **Ne pas supprimer les données METFP déjà importées et ne pas les présenter comme exhaustives ou confirmées sur la seule base de cette page.**

À faire :
1. vérifier l'état des filtres, la pagination et le chargement JavaScript du portail ;
2. rechercher les douze documents précédemment recensés par titre exact et retrouver leurs URL officielles ;
3. télécharger chaque document accessible et relever titre, type de référentiel, métier, certification, date de publication et empreinte du fichier ;
4. séparer les référentiels publiés, les remises officielles annoncées et les offres ouvertes dans un centre ;
5. conserver les offres ETFP de Toamasina/Atsinanana en attente tant qu'une preuve datée d'ouverture pour 2026-2027 n'est pas disponible.

## 4. Règles de publication pour MITARIDALA

| Élément | Décision actuelle |
|---|---|
| RAPE MEN septembre 2026 T6-T12 | Version annuelle de référence, statut global partiel |
| PE Collège T6-T9 | Identifié dans l'index ; contenu détaillé et date d'effet à récupérer |
| PE Lycée T10-T12 | Identifié dans l'index ; contenu détaillé et date d'effet à récupérer |
| Coefficients / volumes horaires lycée | Document identifié ; fichier et tableaux à auditer |
| Séries A/C/D vs L/S/OSE | Correspondance non établie ; ne pas fusionner |
| Offres d'établissements scolaires à Toamasina | À vérifier individuellement pour l'année concernée |
| Référentiels METFP 2026 | Divergence d'index à résoudre ; ne pas déclarer l'inventaire complet |
| Offres ETFP locales 2026-2027 | Non confirmées sans preuve datée d'ouverture |

## 5. Étapes de clôture

- [ ] Obtenir les pièces jointes PDF PE Collège et PE Lycée depuis le portail MEN ou directement auprès du MEN.
- [ ] Obtenir le PDF « Coefficient et volume horaire niveau lycée » et vérifier les tableaux par classe/série.
- [ ] Relever les dates d'édition, arrêtés ou notes de service qui établissent l'année d'effet du PE et du RAPE.
- [ ] Obtenir la preuve officielle de correspondance des séries A/C/D et L/S/OSE, ou conserver deux nomenclatures distinctes.
- [ ] Contrôler les onze RAPE ligne par ligne contre la migration et les tests.
- [ ] Réconcilier le catalogue METFP : 12 éléments précédemment relevés contre 1 élément visible lors de la présente consultation.
- [ ] Vérifier établissement par établissement les offres scolaires et ETFP réellement ouvertes à Toamasina/Atsinanana en 2026-2027.
- [ ] Mettre à jour le rapport principal et le TODO seulement après ces contrôles.
- [ ] Exécuter tests SQLite, smoke PostgreSQL, CI complète et revue du PR avant toute fusion.
- [ ] Après fusion seulement, contrôler migrations, /health, /ready, logs et parcours catalogue en production.

## 6. Hors périmètre

Aucun changement n'est autorisé ici sur le moteur de rendu LaTeX/KaTeX, les quiz, le Tuteur IA ou les documents utilisateurs. Aucune migration de données de production, fusion ou mise en production ne doit être déclenchée par ce rapport.
