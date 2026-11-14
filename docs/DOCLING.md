# Extraction documentaire Docling

## Intégration

MITARIDALA conserve un pipeline hybride :

- PDF : Docling est essayé en premier lorsque `DOCLING_ENABLED=true` et que le paquet optionnel est installé.
- PDF non exploitable par Docling, conversion interrompue ou paquet absent : repli automatique sur `pdfplumber + Tesseract`.
- Images : Tesseract avec les prétraitements existants.
- DOCX/PPTX : extracteurs bureautiques existants, sans changement de comportement.

Le dépôt par lot conserve sa limite de 15 documents, son plafond global de 120 Mo, sa limite de 20 Mo par fichier et sa concurrence maximale de deux analyses. Les conversions Docling sont sérialisées et configurées avec des files/batches de petite taille pour limiter la mémoire. L'extracteur continue à plafonner les PDF à 60 pages et le texte à 300 000 caractères.

## Installation optionnelle

Ne pas installer Docling dans l'image du service web Render Free : la bibliothèque entraîne des dépendances de calcul et des modèles de mise en page/OCR qui peuvent augmenter fortement la taille de l'image, le démarrage et la mémoire utilisée.

Sur un worker séparé qui dispose d'une mémoire suffisante et d'un espace disque/cache persistant :

```bash
pip install -r requirements-docling.txt
docling-tools models download --output-dir /models
```

Le cache de modèles doit être préparé pendant le build ou fourni comme artefact persistant. Définir ensuite `DOCLING_ARTIFACTS_PATH=/models`. L'adaptateur refuse d'activer Docling si le dossier est absent ou vide et passe à l'extracteur historique : cela évite un téléchargement de modèles imprévisible pendant un dépôt utilisateur.

Vérifier également que Tesseract et les modèles français/anglais sont installés dans l'image système.

## Activation progressive

Configurer uniquement sur le worker Docling :

- `DOCLING_ARTIFACTS_PATH=/models` : dossier contenant les modèles pré-téléchargés.
- `DOCLING_ENABLED=true` : active l'essai Docling pour les PDF uniquement lorsque le cache existe.
- `DOCLING_TABLE_STRUCTURE=true` : active le modèle de reconstruction des tableaux ; le laisser désactivé tant que la mémoire n'a pas été mesurée.

Par défaut, les deux options sont désactivées. Le service actuel n'est donc pas alourdi et garde son comportement OCR éprouvé.

## Qualité et langues

Un résultat Docling trop court, vide ou manifestement bruité déclenche le repli automatique. Le moteur réellement utilisé est présenté dans le résultat du dépôt. Ce signal est une indication technique et non une garantie d'exactitude ; la modération humaine reste obligatoire.

La configuration initiale de Tesseract dans l'adaptateur est français + anglais. Elle ne garantit pas la reconnaissance du malgache, des écritures manuscrites, des scans inclinés ou des formules mathématiques complexes. Ces cas doivent être évalués avec un corpus de documents anonymisés avant activation à grande échelle.

## Vérifications avant production

Comparer les mêmes fichiers dans les deux moteurs : PDF natifs, scans, pages mixtes, tableaux, colonnes, sujets CEPE/BEPC/BAC, documents universitaires, français et malgache. Mesurer l'extraction correcte des titres/matières/années, le taux de classement erroné, les pages omises, la durée et le pic mémoire. Ne pas supprimer Tesseract tant que Docling n'a pas démontré un gain mesuré sur le corpus réel.
