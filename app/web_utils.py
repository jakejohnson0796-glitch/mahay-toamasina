"""
Petit utilitaire de parsing pour les champs de formulaire et parametres
de requete optionnels de type entier (filiere_id, mention_id, etc).

Le probleme qu'il resout : un <select> HTML avec une option du genre
<option value="">— aucune —</option> envoie une CHAINE VIDE quand cette
option est choisie — jamais "absent". Si la route FastAPI declare ce
champ `Optional[int] = Form(None)` (ou `= None` pour un parametre de
requete GET), Pydantic tente de parser "" comme un entier AVANT que le
corps de la fonction ne s'execute, et renvoie une erreur 422 brute a
l'utilisateur au lieu du comportement "rien de selectionne" attendu.

Regle du projet : tout champ de ce genre (associe a un <select> qui
propose une option vide) est declare `Optional[str] = Form(None)` (ou
`Optional[str] = None` pour un parametre GET), jamais `Optional[int]` —
et converti avec entier_ou_none() des la premiere ligne du corps de la
fonction.
"""
from typing import Optional


def entier_ou_none(valeur: Optional[str]) -> Optional[int]:
    """Convertit un champ de formulaire/parametre de requete texte en
    entier. None ou "" -> None (option "aucune" d'un <select>, ou
    parametre absent de l'URL). Une valeur non numerique (URL/requete
    bricolee) -> None egalement, plutot que de lever une exception non
    controlee jusqu'a l'utilisateur."""
    if not valeur:
        return None
    try:
        return int(valeur)
    except ValueError:
        return None
