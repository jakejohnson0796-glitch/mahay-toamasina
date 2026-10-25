"""Routes des jeux classiques (culture générale, chiffres et lettres)."""
import random
import re
import unicodedata
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session
from .auth import utilisateur_courant
from .csrf import verifier_csrf
from .database import get_session
from .templating import templates

router = APIRouter(prefix="/jeux-classiques", tags=["jeux-classiques"])
QUESTIONS = [
 {"id":"capitale","theme":"Madagascar","question":"Quelle est la capitale de Madagascar ?","choix":["Toamasina","Antananarivo","Mahajanga","Fianarantsoa"],"bonne":1,"explication":"Antananarivo est la capitale de Madagascar."},
 {"id":"ocean","theme":"Géographie","question":"Dans quel océan se trouve Madagascar ?","choix":["Atlantique","Pacifique","Indien","Arctique"],"bonne":2,"explication":"Madagascar se trouve dans l'océan Indien."},
 {"id":"eau","theme":"Sciences","question":"Quelle est la formule chimique de l'eau ?","choix":["CO₂","H₂O","O₂","NaCl"],"bonne":1,"explication":"Une molécule d'eau contient deux atomes d'hydrogène et un atome d'oxygène."},
 {"id":"premier","theme":"Mathématiques","question":"Lequel de ces nombres est premier ?","choix":["21","27","29","33"],"bonne":2,"explication":"29 n'a que deux diviseurs positifs : 1 et 29."},
 {"id":"equateur","theme":"Géographie","question":"Quelle ligne sépare les hémisphères Nord et Sud ?","choix":["Le tropique du Cancer","Greenwich","L'équateur","Le cercle polaire"],"bonne":2,"explication":"L'équateur est à latitude zéro."},
 {"id":"siecle","theme":"Histoire","question":"Combien d'années compte un siècle ?","choix":["10","50","100","1 000"],"bonne":2,"explication":"Un siècle correspond à 100 années."},
 {"id":"suite","theme":"Logique","question":"Quelle est la suite : 2, 4, 8, 16, … ?","choix":["18","24","30","32"],"bonne":3,"explication":"Chaque terme est multiplié par deux."},
 {"id":"vitesse","theme":"Physique","question":"Quelle unité mesure une vitesse dans le système international ?","choix":["mètre","mètre par seconde","kilogramme","newton"],"bonne":1,"explication":"L'unité SI est le mètre par seconde (m/s)."},
 {"id":"photosynthese","theme":"Biologie","question":"Quel gaz les plantes utilisent-elles pour la photosynthèse ?","choix":["Dioxyde de carbone","Hélium","Hydrogène","Néon"],"bonne":0,"explication":"Les plantes utilisent notamment le dioxyde de carbone et l'eau."},
 {"id":"verbe","theme":"Langue","question":"Quel est l'infinitif de « nous finissons » ?","choix":["Finir","Fini","Finissant","Finissait"],"bonne":0,"explication":"« Finissons » est une forme conjuguée du verbe finir."}
]
MOTS = {"ARBRE","TABLE","LIVRE","ROUTE","FLEUR","PLAGE","ECOLE","AMOUR","SAVOIR","ORANGE","SCIENCE","HISTOIRE","CALCUL","NATURE","SOLEIL","ETOILE","RIVIERE","MALAGASY","CLASSE","ETUDIANT"}

def normaliser(texte):
    texte = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in texte if not unicodedata.combining(c)).upper().strip()

def mot_valide(mot, lettres):
    mot = normaliser(mot).replace(" ","").replace("-","")
    if len(mot) < 2 or mot not in MOTS:
        return False
    disponibles = list(lettres)
    for lettre in mot:
        if lettre not in disponibles:
            return False
        disponibles.remove(lettre)
    return True

def calculer(expression, nombres, cible):
    """Vérifie les calculs avec une grammaire arithmétique restreinte, sans eval."""
    if len(expression) > 100 or not re.fullmatch(r"[0-9+*/().\-\s]+", expression):
        return False, "Expression invalide : utilise les nombres tirés et +, -, × ou ÷."
    tokens = re.findall(r"\d+|[()+*/-]", expression.replace(" ",""))
    if "".join(tokens) != expression.replace(" ","") or not tokens:
        return False, "Expression mathématique invalide."
    pos = 0
    utilises = []
    def facteur():
        nonlocal pos
        if pos >= len(tokens): raise ValueError()
        tok = tokens[pos]
        if tok == "-":
            pos += 1
            return -facteur()
        if tok == "(":
            pos += 1
            val = somme()
            if pos >= len(tokens) or tokens[pos] != ")": raise ValueError()
            pos += 1
            return val
        if tok.isdigit():
            pos += 1
            n = int(tok)
            utilises.append(n)
            return n
        raise ValueError()
    def produit():
        nonlocal pos
        val = facteur()
        while pos < len(tokens) and tokens[pos] in ("*","/"):
            op = tokens[pos]; pos += 1
            droite = facteur()
            if op == "*": val *= droite
            else:
                if droite == 0 or val % droite != 0: raise ValueError()
                val //= droite
        return val
    def somme():
        nonlocal pos
        val = produit()
        while pos < len(tokens) and tokens[pos] in ("+","-"):
            op = tokens[pos]; pos += 1
            droite = produit()
            val = val + droite if op == "+" else val - droite
        return val
    try:
        resultat = somme()
        if pos != len(tokens) or len(utilises) < 2: raise ValueError()
        for n in set(utilises):
            if utilises.count(n) > list(nombres).count(n): return False, "Un nombre a été utilisé plus de fois que dans le tirage."
        if any(n not in nombres for n in utilises): return False, "Utilise uniquement les nombres tirés."
        if abs(resultat) > 1000000: raise ValueError()
        if resultat == cible: return True, "Bravo, tu as atteint le nombre cible !"
        return False, f"Ton résultat est {resultat}. La cible était {cible}."
    except (ValueError, ZeroDivisionError, RecursionError):
        return False, "Expression invalide. Vérifie les nombres, les parenthèses et les opérations."

@router.get("")
def accueil(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur: return RedirectResponse("/connexion", status_code=303)
    return templates.TemplateResponse(request, "jeux_classiques.html", {"utilisateur": utilisateur, "partie": request.session.get("jeux_classiques", {}), "questions": QUESTIONS})

@router.post("/demarrer", dependencies=[Depends(verifier_csrf)])
def demarrer(request: Request, mode: str = Form(...), session: Session = Depends(get_session)):
    if not utilisateur_courant(request, session): return RedirectResponse("/connexion", status_code=303)
    if mode not in {"champion","chiffres","lettres"}: return RedirectResponse("/jeux-classiques", status_code=303)
    etat = {"mode":mode,"score":0,"tour":0}
    if mode == "champion":
        etat["ids"] = [q["id"] for q in random.sample(QUESTIONS, 5)]
    elif mode == "chiffres":
        etat["nombres"] = random.sample([1,2,3,4,5,6,7,8,9,10,25,50,75,100], 6)
        # Construire la cible depuis le tirage garantit au moins une solution exacte.
        etat["cible"] = (etat["nombres"][0] + etat["nombres"][1]) * etat["nombres"][2]
    else:
        voyelles = list("AAAAEEEEIIIOU")
        consonnes = list("BBCCDDFFGGHLLLMMNNNPRRRSSSTTV")
        lettres = [random.choice(voyelles) for _ in range(4)] + [random.choice(consonnes) for _ in range(5)]
        random.shuffle(lettres)
        etat["lettres"] = lettres
    request.session["jeux_classiques"] = etat
    return RedirectResponse("/jeux-classiques", status_code=303)

@router.post("/repondre", dependencies=[Depends(verifier_csrf)])
def repondre(request: Request, reponse: str = Form(""), choix: int = Form(-1), session: Session = Depends(get_session)):
    if not utilisateur_courant(request, session): return RedirectResponse("/connexion", status_code=303)
    etat = request.session.get("jeux_classiques") or {}
    mode = etat.get("mode")
    if mode == "champion":
        ids = etat.get("ids", []); tour = int(etat.get("tour", 0))
        if tour >= len(ids): return RedirectResponse("/jeux-classiques", status_code=303)
        q = next((x for x in QUESTIONS if x["id"] == ids[tour]), None)
        if q is None: return RedirectResponse("/jeux-classiques", status_code=303)
        correcte = choix == q["bonne"]
        etat["score"] = int(etat.get("score",0)) + int(correcte)
        etat["feedback"] = {"correcte":correcte,"explication":q["explication"],"bonne":q["choix"][q["bonne"]]}
        etat["tour"] = tour + 1
    elif mode == "chiffres":
        correcte, msg = calculer(reponse, etat.get("nombres",[]), int(etat.get("cible",0)))
        etat["score"] = int(etat.get("score",0)) + int(correcte)
        etat["feedback"] = {"correcte":correcte,"explication":msg}; etat["termine"] = True
    elif mode == "lettres":
        correcte = mot_valide(reponse, etat.get("lettres",[]))
        etat["score"] = int(etat.get("score",0)) + int(correcte)
        etat["feedback"] = {"correcte":correcte,"explication":"Mot accepté !" if correcte else "Mot non reconnu ou lettres indisponibles."}; etat["termine"] = True
    request.session["jeux_classiques"] = etat
    return RedirectResponse("/jeux-classiques", status_code=303)
