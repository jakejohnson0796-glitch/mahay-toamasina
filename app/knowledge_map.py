"""Carte de connaissances et pre-requis pedagogiques de Gasy Mahay.

Le moteur ne cree aucune nouvelle note de maitrise : il reutilise ProgressionNotion
et ajoute une couche de lecture des relations entre notions. Les relations sont
volontairement prudentes : elles ne sont affichees que lorsque les deux notions
ont ete effectivement observees chez l'etudiant.
"""
import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Tuple

from .models import ProgressionNotion
from .quiz import diagnostiquer_maitrise


def _sans_accents(texte: str) -> str:
    texte = unicodedata.normalize("NFKD", str(texte or "").lower())
    return "".join(car for car in texte if not unicodedata.combining(car))


def _normaliser(texte: str) -> str:
    valeur = _sans_accents(texte)
    valeur = re.sub(r"[^a-z0-9]+", " ", valeur)
    return re.sub(r"\s+", " ", valeur).strip()


def _matiere_famille(matiere: str) -> str:
    texte = _normaliser(matiere)
    if any(x in texte for x in ("math", "algebre", "analyse", "probabil")):
        return "mathematiques"
    if any(x in texte for x in ("physique", "mecanique", "electricite", "electromagnet")):
        return "physique"
    if any(x in texte for x in ("chimie", "chimique", "biochimie")):
        return "chimie"
    if any(x in texte for x in ("informatique", "programmation", "algorithm", "developpement")):
        return "informatique"
    if any(x in texte for x in ("comptabil", "gestion", "finance")):
        return "comptabilite"
    return "autre"


# Relations volontairement conservatrices. Elles servent uniquement lorsque
# les deux notions sont effectivement presentes dans l'historique de l'etudiant.
_CONCEPTS: Dict[str, Dict[str, object]] = {
    "fractions": {"famille": "mathematiques", "label": "Fractions", "aliases": ["fraction", "fractions"]},
    "puissances": {"famille": "mathematiques", "label": "Puissances", "aliases": ["puissance", "puissances", "exposant", "exposants"]},
    "equations": {"famille": "mathematiques", "label": "Équations", "aliases": ["equation", "equations"]},
    "fonctions": {"famille": "mathematiques", "label": "Fonctions", "aliases": ["fonction", "fonctions"]},
    "derivees": {"famille": "mathematiques", "label": "Dérivées", "aliases": ["derivee", "derivees", "derivation"]},
    "integrales": {"famille": "mathematiques", "label": "Intégrales", "aliases": ["integrale", "integrales", "integration"]},
    "vecteurs": {"famille": "mathematiques", "label": "Vecteurs", "aliases": ["vecteur", "vecteurs"]},
    "matrices": {"famille": "mathematiques", "label": "Matrices", "aliases": ["matrice", "matrices"]},
    "determinants": {"famille": "mathematiques", "label": "Déterminants", "aliases": ["determinant", "determinants"]},
    "systemes": {"famille": "mathematiques", "label": "Systèmes linéaires", "aliases": ["systeme lineaire", "systemes lineaires", "systeme d equations", "systemes d equations"]},
    "probabilites": {"famille": "mathematiques", "label": "Probabilités", "aliases": ["probabilite", "probabilites"]},
    "statistiques": {"famille": "mathematiques", "label": "Statistiques", "aliases": ["statistique", "statistiques"]},

    "unites": {"famille": "physique", "label": "Unités et dimensions", "aliases": ["unite", "unites", "dimension", "dimensions"]},
    "vecteurs_physique": {"famille": "physique", "label": "Vecteurs en physique", "aliases": ["vecteur", "vecteurs"]},
    "cinematique": {"famille": "physique", "label": "Cinématique", "aliases": ["cinematique", "mouvement"]},
    "dynamique": {"famille": "physique", "label": "Dynamique", "aliases": ["dynamique", "lois de newton", "newton"]},
    "energie": {"famille": "physique", "label": "Énergie", "aliases": ["energie", "travail et energie", "travail energie"]},
    "electricite": {"famille": "physique", "label": "Électricité", "aliases": ["electricite", "circuits", "circuit electrique"]},

    "atome": {"famille": "chimie", "label": "Atome et structure", "aliases": ["atome", "atomes", "structure atomique"]},
    "moles": {"famille": "chimie", "label": "Moles et quantité de matière", "aliases": ["mole", "moles", "quantite de matiere"]},
    "stoechiometrie": {"famille": "chimie", "label": "Stœchiométrie", "aliases": ["stoechiometrie", "stoichiometrie"]},
    "solutions": {"famille": "chimie", "label": "Solutions", "aliases": ["solution", "solutions", "concentration", "concentrations"]},
    "acides_bases": {"famille": "chimie", "label": "Acides et bases", "aliases": ["acide", "acides", "base", "bases", "ph"]},

    "variables": {"famille": "informatique", "label": "Variables et types", "aliases": ["variable", "variables", "types de donnees", "type de donnees"]},
    "conditions_boucles": {"famille": "informatique", "label": "Conditions et boucles", "aliases": ["condition", "conditions", "boucle", "boucles", "if", "for", "while"]},
    "fonctions_info": {"famille": "informatique", "label": "Fonctions", "aliases": ["fonction", "fonctions", "procedure", "procedures"]},
    "structures_donnees": {"famille": "informatique", "label": "Structures de données", "aliases": ["structure de donnees", "structures de donnees", "liste", "tableau", "dictionnaire"]},
    "algorithmes": {"famille": "informatique", "label": "Algorithmes", "aliases": ["algorithme", "algorithmes", "complexite", "complexite algorithmique"]},

    "debit_credit": {"famille": "comptabilite", "label": "Débit / crédit", "aliases": ["debit credit", "debit et credit", "debit", "credit"]},
    "comptes_ecritures": {"famille": "comptabilite", "label": "Comptes et écritures", "aliases": ["ecriture comptable", "ecritures comptables", "comptes", "compte en t", "comptes en t"]},
    "balance": {"famille": "comptabilite", "label": "Balance", "aliases": ["balance", "balance comptable"]},
    "bilan_resultat": {"famille": "comptabilite", "label": "Bilan et résultat", "aliases": ["bilan", "compte de resultat", "compte de résultat", "resultat"]},
}

_RELATIONS: Tuple[Tuple[str, str], ...] = (
    ("fractions", "equations"),
    ("puissances", "equations"),
    ("equations", "fonctions"),
    ("fonctions", "derivees"),
    ("derivees", "integrales"),
    ("vecteurs", "matrices"),
    ("matrices", "determinants"),
    ("determinants", "systemes"),
    ("probabilites", "statistiques"),

    ("unites", "cinematique"),
    ("vecteurs_physique", "cinematique"),
    ("cinematique", "dynamique"),
    ("dynamique", "energie"),
    ("electricite", "energie"),

    ("atome", "moles"),
    ("moles", "stoechiometrie"),
    ("stoechiometrie", "solutions"),
    ("solutions", "acides_bases"),

    ("variables", "conditions_boucles"),
    ("conditions_boucles", "fonctions_info"),
    ("fonctions_info", "structures_donnees"),
    ("structures_donnees", "algorithmes"),

    ("debit_credit", "comptes_ecritures"),
    ("comptes_ecritures", "balance"),
    ("balance", "bilan_resultat"),
)


def _correspondance(progression: ProgressionNotion) -> Optional[str]:
    famille = _matiere_famille(progression.matiere)
    notion = _normaliser(progression.notion)
    if not notion:
        return None

    candidats = []
    for cle, concept in _CONCEPTS.items():
        if concept["famille"] != famille:
            continue
        aliases = [str(alias) for alias in concept["aliases"]]
        for alias in aliases:
            alias_norm = _normaliser(alias)
            if alias_norm and (notion == alias_norm or alias_norm in notion or notion in alias_norm):
                candidats.append((len(alias_norm), cle))
    if not candidats:
        return None
    candidats.sort(reverse=True)
    return candidats[0][1]


def _score(progression: ProgressionNotion) -> int:
    return max(0, min(100, int(progression.score_maitrise or 0)))


def construire_carte(progressions: Iterable[ProgressionNotion]) -> dict:
    progressions = list(progressions)
    observables: Dict[Tuple[str, str], ProgressionNotion] = {}
    concept_par_id: Dict[int, Optional[str]] = {}

    for progression in progressions:
        concept = _correspondance(progression)
        concept_par_id[int(progression.id or id(progression))] = concept
        cle = (str(progression.matiere or ""), str(concept or f"raw:{progression.id}"))
        ancien = observables.get(cle)
        if ancien is None or _score(progression) < _score(ancien):
            observables[cle] = progression

    groupes: Dict[str, List[dict]] = {}
    for progression in observables.values():
        concept = _correspondance(progression)
        diagnostic = diagnostiquer_maitrise(progression)
        node = {
            "id": int(progression.id or 0),
            "matiere": progression.matiere,
            "notion": progression.notion,
            "score": _score(progression),
            "statut": diagnostic["statut"],
            "libelle": diagnostic["libelle"],
            "confiance": diagnostic["confiance"],
            "concept": concept,
            "famille": _matiere_famille(progression.matiere),
            "prerequis": [],
            "dependances": [],
        }
        groupes.setdefault(str(progression.matiere), []).append(node)

    index: Dict[Tuple[str, str], dict] = {}
    for nodes in groupes.values():
        for node in nodes:
            if node["concept"]:
                index[(node["matiere"], node["concept"])] = node

    relations = []
    for matiere, nodes in groupes.items():
        famille = _matiere_famille(matiere)
        for source_key, target_key in _RELATIONS:
            if _CONCEPTS.get(source_key, {}).get("famille") != famille:
                continue
            source = index.get((matiere, source_key))
            target = index.get((matiere, target_key))
            if not source or not target:
                continue
            relation = {
                "matiere": matiere,
                "source": source,
                "target": target,
                "source_faible": source["score"] < 70,
                "cible_faible": target["score"] < 70,
                "message": (
                    f"Consolide d'abord « {source['notion']} » avant de viser « {target['notion']} »."
                    if source["score"] < 70 and target["score"] < 85
                    else f"« {source['notion']} » sert de prérequis à « {target['notion']} »."
                ),
            }
            source["dependances"].append(target["notion"])
            target["prerequis"].append(source["notion"])
            relations.append(relation)

    for nodes in groupes.values():
        nodes.sort(key=lambda node: (node["score"], node["notion"].lower()))

    priorites = sorted(
        [node for nodes in groupes.values() for node in nodes],
        key=lambda node: (0 if node["prerequis"] else 1, node["score"], node["notion"].lower()),
    )

    blocages = [
        relation
        for relation in relations
        if relation["source_faible"] and relation["cible"]["score"] >= relation["source"]["score"]
    ]
    blocages.sort(key=lambda relation: (relation["source"]["score"], relation["target"]["score"]))

    prochaine = blocages[0]["source"] if blocages else (priorites[0] if priorites else None)
    sujets = [
        {
            "matiere": matiere,
            "nodes": nodes,
            "relations": [r for r in relations if r["matiere"] == matiere],
        }
        for matiere, nodes in groupes.items()
    ]

    return {
        "sujets": sujets,
        "relations": relations,
        "blocages": blocages[:6],
        "prochaine": prochaine,
        "nb_notions": len([node for nodes in groupes.values() for node in nodes]),
        "nb_relations": len(relations),
    }
