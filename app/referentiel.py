"""
Valeurs normalisees partagees par tout le referentiel academique
(cercles, profil etudiant, quiz, cours). Un seul endroit a modifier si
la liste des niveaux doit evoluer.

Avant ce module, app/quiz.py definissait sa propre liste NIVEAUX = [L1..M2],
utilisee uniquement pour les quiz. Ce module l'etend (ajout D1-D3) et la
centralise pour que le profil etudiant, les cercles et les quiz utilisent
tous exactement la meme representation (voir §35 du brief refonte
academique : 'stocker une valeur normalisee, afficher un libelle humain').
"""

NIVEAUX = ["L1", "L2", "L3", "M1", "M2", "D1", "D2", "D3"]

NIVEAUX_LIBELLES = {
    "L1": "Licence 1",
    "L2": "Licence 2",
    "L3": "Licence 3",
    "M1": "Master 1",
    "M2": "Master 2",
    "D1": "Doctorat 1",
    "D2": "Doctorat 2",
    "D3": "Doctorat 3",
}


def libelle_niveau(code: str) -> str:
    """'L3' -> 'Licence 3'. Renvoie le code tel quel si inconnu (ne
    doit jamais faire planter l'affichage pour une valeur inattendue)."""
    return NIVEAUX_LIBELLES.get(code, code)
