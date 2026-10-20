# Conception responsive de MITARIDALA

## Objectif

Une même page doit rester lisible et utilisable avec une largeur de 265 px comme sur tablette et ordinateur, sans dépendre d'un modèle de téléphone ou d'un navigateur particulier.

## Contrat commun

- Le document et les conteneurs de page ne doivent pas imposer de largeur minimale fixe.
- Les grilles réduisent leurs colonnes avec des pistes `minmax(0, 1fr)`; les cartes et enfants flexibles peuvent rétrécir.
- Les images et vidéos sont fluides ; les contenus scientifiques, préformatés et tableaux larges peuvent défiler horizontalement dans leur propre conteneur plutôt que d'élargir toute la page.
- Les formulaires restent dans leur conteneur et les libellés longs peuvent revenir à la ligne.
- La navigation mobile utilise six colonnes stables, une icône au-dessus d'un libellé court, des zones tactiles hautes d'au moins 44 px et les marges de sécurité des écrans avec encoche.
- Le contenu conserve une marge inférieure pour ne pas être masqué par la barre fixe. Les styles respectent `prefers-reduced-motion`.

## Ruptures ciblées

- `340 px et moins` : libellés et icônes mobiles compacts.
- `560 px et moins` : disposition à une colonne pour les familles de cartes denses.
- `768 px et moins` : navigation mobile fixe en bas, compatible portrait et paysage.
- `900 px et moins` : les panneaux principaux basculent dans une disposition tablette plus étroite.
- Au-delà de `768 px` : la navigation mobile est masquée et la navigation de bureau reste active.

Ce sont des points de rupture fondés sur la place disponible, pas sur la marque d'un appareil. Les tailles CSS, l'orientation et les zones de sécurité permettent aux navigateurs Android, Chrome, Edge, Firefox et Safari de calculer la mise en page à partir du viewport.

## Pourquoi ne pas ajouter Bootstrap ou Tailwind maintenant ?

Le projet dispose déjà de plusieurs feuilles CSS métier, d'un système de styles partagé et d'une navigation Jinja commune. Charger un second framework en parallèle introduirait deux conventions de classes, alourdirait les pages et ne corrigerait pas un HTML invalide. La couche `responsive-universal.css` centralise les règles transversales tout en laissant les styles par page en place. Une migration complète vers un framework se déciderait séparément et page par page, après un inventaire des composants.

## Vérification

La commande `node scripts/smoke_global_responsive.mjs` est exécutée dans la CI après l'installation de Playwright/Chromium. Le test inspecte la structure réelle des six liens de navigation dans `base.html`, puis exerce sept familles de pages (tableau de bord, documents, quiz, cercles, classe virtuelle, administration et authentification) à 11 largeurs de 265 à 1440 px. Il vérifie l'absence de débordement horizontal, la position des onglets, leurs zones tactiles, les thèmes clair et sombre et l'absence de navigation mobile sur grand écran.

Ce test automatisé complète — sans remplacer — une inspection réelle sur appareils et navigateurs physiques, notamment les barres d'adresse dynamiques et les claviers mobiles.
