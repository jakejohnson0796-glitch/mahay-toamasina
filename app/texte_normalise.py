"""
Normalisation de texte pour COMPARAISON uniquement (jamais pour
l'affichage/le stockage) — centralisee ici parce qu'elle est utilisee
a la fois par cercles_referentiel.py (provisionnement automatique) et
referentiel_academique.py (correspondance profil <-> cercle), qui
doivent imperativement rester d'accord sur ce qui compte comme "le
meme parcours" : un desaccord entre les deux romprait silencieusement
soit la creation, soit la reconnaissance d'eligibilite des cercles
nationaux (voir cercles_referentiel.py pour le contexte complet du
probleme que cette normalisation partagee resout).

Les scripts ponctuels (scripts/import_academic_data.py,
scripts/dedupliquer_cercles_nationaux.py) gardent volontairement leur
propre copie de cette fonction plutot que d'importer celle-ci : ce
sont des outils autonomes lances manuellement, pas du code d'app
charge a chaque requete, donc la coherence stricte importe moins que
pour ces deux modules-ci qui tournent en continu et doivent, eux,
rester rigoureusement synchronises.
"""
import re
import unicodedata


def normaliser(texte: str | None) -> str:
    if not texte:
        return ""
    texte = texte.strip().replace("\u2019", "'")
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = re.sub(r"\s+", " ", texte)
    return texte.lower()
