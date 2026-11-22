# MITARIDALA — Apprendre, pratiquer et progresser

MITARIDALA est une plateforme éducative destinée aux élèves, aux étudiants et aux enseignants de Madagascar. Elle rassemble les ressources d’apprentissage, les exercices, l’accompagnement pédagogique et les espaces de collaboration dans un même environnement.

**Accéder à la plateforme :** [mitaridala.onrender.com](https://mitaridala.onrender.com)

## Ce que propose la plateforme

### Ressources pédagogiques
- Rechercher des cours, fiches, exercices, annales et corrigés.
- Déposer des ressources soumises à modération avant leur publication.
- Retrouver les documents selon le parcours et les matières disponibles.
- Déposer jusqu’à 15 documents en un envoi, avec 20 Mo maximum par fichier et 120 Mo par lot.
- Faire analyser chaque fichier séparément : extraction directe des PDF textuels, Word et PowerPoint ; PaddleOCR PP-OCRv5 en français est prioritaire pour les scans et Tesseract français/anglais sert de repli si nécessaire. Un récapitulatif des métadonnées et de la confiance détectée est ensuite produit. Les documents restent soumis à modération avant publication.
- Consulter un avertissement lorsqu’aucun texte n’a pu être extrait ; les valeurs saisies manuellement ne gonflent pas le score de confiance automatique.

### Apprentissage et révision
- S’entraîner avec des quiz et consulter ses résultats.
- Repérer les notions à retravailler après un exercice.
- Utiliser le Tuteur IA pour obtenir une explication, un exemple, un exercice et une correction.
- Consulter des supports de révision liés aux ressources et aux activités disponibles.

### Collaboration
- Rejoindre des cercles d’étude et échanger avec d’autres apprenants.
- Participer aux activités de classe virtuelle proposées par la plateforme.
- Suivre ses activités et sa progression.

### Parcours scolaires et universitaires
MITARIDALA prend en compte différents parcours : collège, lycée, enseignement technique et formation professionnelle, ainsi que l’enseignement supérieur. Les choix affichés dépendent des informations disponibles dans le catalogue.

## Parcours d’apprentissage

1. Choisir son cycle, son niveau et sa matière lorsqu’ils sont proposés.
2. Rechercher un cours ou une ressource adaptée.
3. Pratiquer avec un quiz ou un exercice.
4. Examiner les erreurs et demander une explication lorsque nécessaire.
5. Revoir les notions difficiles et suivre ses progrès.

## Langues

L’interface propose le français, le malgache et l’anglais. La disponibilité des traductions peut varier selon les pages et les contenus.

## Utilisation responsable de l’intelligence artificielle

Les réponses générées servent à accompagner l’apprentissage. Elles peuvent être incomplètes ou comporter des erreurs. Pour les travaux importants, les apprenants doivent comparer les explications avec leur cours, leur enseignant et les sources de référence.

## Référentiel académique

La présence d’un établissement ou d’un programme dans un catalogue ne constitue pas, à elle seule, une preuve d’habilitation en vigueur, d’accréditation ou d’ouverture des admissions pour une année donnée. Ces informations doivent être confirmées auprès des autorités et établissements concernés à partir de documents officiels récents.

Les données incomplètes ou incertaines ne doivent pas être présentées comme des offres confirmées.

## Respect des contenus et des personnes

Les utilisateurs doivent respecter les droits des auteurs et ne partager que des documents qu’ils sont autorisés à diffuser. Les échanges doivent rester respectueux et conformes aux règles d’utilisation de la plateforme.

## Vision

L’objectif de MITARIDALA est de rendre les ressources éducatives plus faciles à trouver, de soutenir un apprentissage régulier et de renforcer l’entraide entre apprenants et enseignants.


### Installer les moteurs OCR en développement local

Le Dockerfile de production installe automatiquement PaddlePaddle CPU et PaddleOCR. Pour reproduire ce moteur sur un poste local Python 3.12 :

```bash
python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
python -m pip install -r requirements-ocr.txt
```

Les modèles PP-OCRv5 français sont chargés à la première lecture d'un scan puis conservés dans le cache local. Avant ce chargement, l'application vérifie la limite mémoire du conteneur : par défaut, elle exige au moins 2 560 MiB pour éviter un arrêt par manque de mémoire ; ce seuil peut être réglé avec PADDLE_OCR_MIN_MEMORY_MB. En dessous du seuil, ou si PaddleOCR n'est pas installé, le traitement continue avec Tesseract lorsque celui-ci est installé.
