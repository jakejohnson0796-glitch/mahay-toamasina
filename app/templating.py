"""
Instance Jinja2Templates PARTAGEE par tout le projet, a importer partout
(from ..templating import templates) plutot que d'en creer une par
router comme avant. Necessaire pour que jeton_csrf() (voir csrf.py) soit
disponible dans absolument tous les templates, quel que soit le router
qui les rend — une instance par router aurait exige d'enregistrer le
global separement dans chacune, avec le risque d'en oublier une.
"""
from pathlib import Path
import hashlib
from functools import lru_cache

from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func

from .csrf import obtenir_jeton_csrf
from .quiz_validation import (
    rendre_math_html,
    rendre_choix_math_html,
    normaliser_choix_liste,
    normaliser_math_texte,
)

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["jeton_csrf"] = obtenir_jeton_csrf
templates.env.globals["rendre_math_html"] = rendre_math_html
templates.env.globals["rendre_choix_math_html"] = rendre_choix_math_html
templates.env.globals["normaliser_choix_liste"] = normaliser_choix_liste


def _texte_ia_html(texte) -> "Markup":
    """Rend le Markdown courant des reponses IA sans autoriser du HTML brut."""
    import html
    import re
    from markupsafe import Markup

    brut = "" if texte is None else str(texte)
    lignes = brut.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    html_blocks = []
    i = 0

    def inline(valeur: str) -> str:
        # Reserve les fragments mathematiques avant l'echappement Markdown,
        # sinon \\[...\\] et \\( ... \\) apparaissent comme du texte brut.
        # Les modeles peuvent livrer LaTeX avec un ou deux antislashs selon
        # le passage JSON/outil. Normalise d'abord les formes doublement echappees,
        # puis capture les formes usuelles de mathematiques.
        valeur = (
            valeur
            .replace(r"\\[", r"\[")
            .replace(r"\\]", r"\]")
            .replace(r"\\(", r"\(")
            .replace(r"\\)", r"\)")
            .replace(r"\\begin", r"\begin")
            .replace(r"\\end", r"\end")
        )
        # Les reponses du Tuteur peuvent aussi contenir des commandes
        # mathematiques sans delimiters. La normalisation transforme les
        # commandes usuelles en symboles lisibles avant l'echappement HTML.
        valeur = normaliser_math_texte(valeur)
        math_pattern = re.compile(
            r"(\$\$(?:.|\n)*?\$\$|\\\[(?:.|\n)*?\\\]|\\\((?:.|\n)*?\\\)"
            r"|\\begin\{(?:pmatrix|bmatrix|vmatrix|matrix)\}(?:.|\n)*?\\end\{(?:pmatrix|bmatrix|vmatrix|matrix)\})"
        )
        placeholders = {}

        def garder_math(match):
            cle = f"__MATH_{len(placeholders)}__"
            placeholders[cle] = str(rendre_math_html(match.group(0)))
            return cle

        valeur = math_pattern.sub(garder_math, valeur)
        # Une commande \\mathbf hors d'un delimitateur mathematique doit
        # rester lisible plutot que d'etre affichee comme du LaTeX brut.
        valeur = re.sub(r"\\mathbf\{([^{}]+)\}", r"**\1**", valeur)
        valeur = html.escape(valeur, quote=True)
        valeur = re.sub(r"\x60([^\x60]+)\x60", r"<code>\1</code>", valeur)
        valeur = re.sub(r"\*\*([^*\n]+?)\*\*", r"<strong>\1</strong>", valeur)
        valeur = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", valeur)
        for cle, rendu in placeholders.items():
            valeur = valeur.replace(cle, rendu)
        return valeur

    def _tableau_est_matrice(entetes: list[str], rows: list[list[str]]) -> bool:
        """Reconnaît un tableau Markdown carré qui représente une matrice."""
        toutes = [cellule.strip() for ligne in [entetes] + rows for cellule in ligne]
        if len(entetes) < 2 or len(entetes) != len(rows) + 1:
            return False
        taille = len(entetes)
        if taille < 2:
            return False

        def cellule_math(cellule: str) -> bool:
            valeur = normaliser_math_texte(cellule).strip()
            if not valeur or len(valeur) > 40:
                return False
            # Une cellule de matrice doit ressembler à une expression
            # mathématique, pas à un libellé de tableau (« Nom », « Note »...).
            if re.fullmatch(r"[A-Za-zα-ωΑ-Ω]", valeur):
                return True
            return bool(
                re.search(r"\\frac|\\sqrt|[0-9]|[+\\-*/=^_×·≤≥≠≈()]", valeur)
                and re.fullmatch(r"[A-Za-z0-9α-ωΑ-Ω_+\\-*/=^_{}().×·≤≥≠≈ ]+", valeur)
            )

        return all(cellule_math(cellule) for cellule in toutes)

    def rendre_tableau_matrice(entetes: list[str], rows: list[list[str]]) -> str:
        valeurs = [entetes] + rows
        lignes_tex = ["&".join(normaliser_math_texte(cellule).strip() for cellule in ligne) for ligne in valeurs]
        bloc = r"\[" + r"\begin{pmatrix}" + r"\\ ".join(lignes_tex) + r"\end{pmatrix}" + r"\]"
        return str(rendre_math_html(bloc))

    def est_sep_tableau(ligne: str) -> bool:
        morceaux = [m.strip() for m in ligne.strip().strip("|").split("|")]
        return bool(morceaux) and all(
            re.fullmatch(r":?-{1,}:?", morceau.replace(" ", "")) for morceau in morceaux
        )

    while i < len(lignes):
        ligne = lignes[i].strip()
        if not ligne:
            i += 1
            continue

        if "|" in ligne and i + 1 < len(lignes) and est_sep_tableau(lignes[i + 1]):
            def cellules(texte_ligne: str) -> list[str]:
                return [inline(c.strip()) for c in texte_ligne.strip().strip("|").split("|")]

            entetes = cellules(ligne)
            i += 2
            rows = []
            while i < len(lignes) and lignes[i].strip() and "|" in lignes[i]:
                rows.append(cellules(lignes[i]))
                i += 1

            if (
                rows
                and all(len(row) == len(entetes) for row in rows)
                and _tableau_est_matrice(entetes, rows)
            ):
                html_blocks.append(rendre_tableau_matrice(entetes, rows))
                continue

            html_blocks.append(
                '<div class="ai-markdown-table-wrap"><table class="ai-markdown-table"><thead><tr>'
                + "".join(f"<th>{c}</th>" for c in entetes)
                + "</tr></thead><tbody>"
                + "".join(
                    "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
                    for row in rows
                )
                + "</tbody></table></div>"
            )
            continue

        match_titre = re.match(r"^(#{1,3})\s+(.+)$", ligne)
        if match_titre:
            niveau = min(len(match_titre.group(1)) + 2, 5)
            html_blocks.append(f"<h{niveau}>{inline(match_titre.group(2))}</h{niveau}>")
            i += 1
            continue

        if re.match(r"^[-*]\s+", ligne):
            items = []
            while i < len(lignes):
                courant = lignes[i].strip()
                if not courant or not re.match(r"^[-*]\s+", courant):
                    break
                items.append(re.sub(r"^[-*]\s+", "", courant))
                i += 1
            html_blocks.append("<ul>" + "".join(f"<li>{inline(item)}</li>" for item in items) + "</ul>")
            continue

        if re.match(r"^\d+[.)]\s+", ligne):
            items = []
            while i < len(lignes):
                courant = lignes[i].strip()
                if not courant or not re.match(r"^\d+[.)]\s+", courant):
                    break
                items.append(re.sub(r"^\d+[.)]\s+", "", courant))
                i += 1
            html_blocks.append("<ol>" + "".join(f"<li>{inline(item)}</li>" for item in items) + "</ol>")
            continue

        if re.fullmatch(r"[-*_]{3,}", ligne):
            i += 1
            html_blocks.append("<hr>")
            continue

        paragraph = [ligne]
        i += 1
        while i < len(lignes) and lignes[i].strip():
            prochain = lignes[i].strip()
            if (
                "|" in prochain
                or re.match(r"^(#{1,3})\s+", prochain)
                or re.match(r"^[-*]\s+", prochain)
                or re.match(r"^\d+[.)]\s+", prochain)
                or re.fullmatch(r"[-*_]{3,}", prochain)
            ):
                break
            paragraph.append(prochain)
            i += 1
        html_blocks.append("<p>" + "<br>".join(inline(part) for part in paragraph) + "</p>")

    return Markup("".join(html_blocks) or "<p>—</p>")


templates.env.filters["texte_ia"] = _texte_ia_html

from .auth import jours_inactivite as _jours_inactivite

templates.env.globals["jours_inactivite"] = _jours_inactivite


def _jours_depuis_creation(utilisateur, maintenant=None) -> int:
    """Nombre de jours complets depuis la creation du compte."""
    from datetime import datetime as _datetime

    if not utilisateur or not utilisateur.date_creation:
        return 0
    maintenant = maintenant or _datetime.utcnow()
    return max(0, (maintenant - utilisateur.date_creation).days)


templates.env.globals["jours_depuis_creation"] = _jours_depuis_creation


def _nb_notifications_admin_nouvelles(request) -> int:
    """Compteur leger pour afficher l'alerte admin dans la navigation."""
    user_id = request.session.get("user_id")
    if not user_id:
        return 0

    from .database import engine
    from .models import Utilisateur, Notification, TypeNotification
    from sqlmodel import select

    with Session(engine) as session:
        admin = session.get(Utilisateur, user_id)
        if not admin or admin.role.value != "admin":
            return 0
        return len(
            session.exec(
                select(Notification.id)
                .where(Notification.destinataire_id == admin.id)
                .where(Notification.type_notification == TypeNotification.NOUVELLE_INSCRIPTION)
                .where(Notification.lu == False)  # noqa: E712
            ).all()
        )


templates.env.globals["nb_notifications_admin_nouvelles"] = _nb_notifications_admin_nouvelles


def _compter_notifications_non_lues(request) -> int:
    """Compteur des notifications non lues de l'utilisateur courant."""
    user_id = request.session.get("user_id")
    if not user_id:
        return 0
    from .database import engine
    from .models import Notification
    with Session(engine) as session:
        return int(session.exec(
            select(func.count())
            .select_from(Notification)
            .where(Notification.destinataire_id == user_id)
            .where(Notification.lu == False)  # noqa: E712
        ).one())


templates.env.globals["compter_notifications_non_lues"] = _compter_notifications_non_lues


def _calculer_jours_inactivite(utilisateur, maintenant=None) -> int:
    """Global Jinja non conflictuel avec les contextes qui exposent deja
    un entier nomme jours_inactivite."""
    from .auth import jours_inactivite as _fonction_jours_inactivite
    return _fonction_jours_inactivite(utilisateur, maintenant)


templates.env.globals["calculer_jours_inactivite"] = _calculer_jours_inactivite


@lru_cache(maxsize=256)
def _version_asset(chemin_relatif: str) -> str:
    """Global Jinja utilise dans base.html pour suffixer les fichiers
    statiques (style.css, navigation.js) d'un parametre ?v=<hash> —
    sans cache-busting, un navigateur qui a deja visite le site avant
    un deploiement peut continuer a servir une COPIE EN MEMOIRE de
    l'ancien style.css meme apres que le HTML change (l'URL du fichier
    ne change jamais sinon, donc rien ne force le navigateur a le
    re-telecharger). Le hash change automatiquement des que le
    contenu du fichier change, sans jamais avoir besoin d'y penser a
    la main (pas de numero de version a incrementer soi-meme, donc pas
    de risque d'oubli a un futur deploiement).

    8 caracteres de hash suffisent ici (simple invalidation de cache,
    pas une preuve d'integrite) ; calcule une fois par demarrage du
    serveur (pas a chaque requete) puisque le fichier ne change jamais
    en cours d'execution."""
    chemin_absolu = BASE_DIR / "static" / chemin_relatif
    try:
        contenu = chemin_absolu.read_bytes()
    except FileNotFoundError:
        # Compatibilite avec les appels historiques qui passent simplement
        # "ai-learning.js", "security-ui.js", etc. : les scripts vivent sous
        # static/js/. Le fallback garde un seul contrat de cache-busting.
        if "/" not in chemin_relatif:
            try:
                contenu = (BASE_DIR / "static" / "js" / chemin_relatif).read_bytes()
            except FileNotFoundError:
                return "0"
        else:
            return "0"
    return hashlib.md5(contenu).hexdigest()[:8]


templates.env.globals["version_asset"] = _version_asset


def _profil_academique_a_actualiser(request) -> bool:
    """Global Jinja (meme principe que jeton_csrf ci-dessus) : vrai si
    l'utilisateur connecte est un(e) etudiant(e) dont le profil
    academique a besoin d'etre actualise (§21-22 du brief refonte
    academique nationale — statut PROFILE_ACADEMIC_UPDATE_REQUIRED).

    Enregistre ici plutot que passe explicitement dans le contexte de
    chaque route : la notification doit pouvoir s'afficher dans
    base.html sur N'IMPORTE QUELLE page (§22 : "des qu'un ancien
    utilisateur se connecte"), et la plupart des ~20 routes existantes
    ne passent pas toutes systematiquement `utilisateur` a leur
    template. Ouvre sa propre session DB courte et isolee, le temps de
    cette seule verification — meme logique que jeton_csrf() qui lit
    request.session independamment de la route appelante.

    Import de .database et .models fait ICI (pas en haut du fichier)
    pour eviter tout risque d'import circulaire : ce module est importe
    tres tot par de nombreux routers, avant que database/models n'aient
    forcement fini de s'initialiser dans tous les contextes.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return False

    from .database import engine
    from .models import Utilisateur
    from . import referentiel_academique

    with Session(engine) as session:
        utilisateur = session.get(Utilisateur, user_id)
        if not utilisateur:
            return False
        return referentiel_academique.profil_academique_incomplet(utilisateur, session)


templates.env.globals["profil_academique_a_actualiser"] = _profil_academique_a_actualiser


# Palette d'avatars du chat de cercle (cercle_chat.html) : couleurs fixes
# (independantes de [data-theme], contrairement a --color-*-clair qui
# s'inversent entre les deux themes) choisies suffisamment saturees/sombres
# pour rester lisibles avec le texte blanc de l'initiale par-dessus, dans
# les deux themes a la fois -- un avatar identifie visuellement une
# personne, il n'a pas de raison de changer de couleur quand on bascule
# le theme. Mesurees au contrastometre (blanc #FFFFFF par-dessus, WCAG
# 1.4.3) malgre le statut aria-hidden/decoratif de l'initiale : 4.30:1 et
# 4.37:1 sur les deux premieres teintes d'origine, sous le seuil 4.5:1
# du texte normal (l'initiale ne remplit pas les criteres de taille du
# "grand texte" qui abaisserait ce seuil a 3:1) -- ajustees vers des
# teintes plus sombres de meme famille pour repasser au-dessus. Ratio
# de chaque teinte finale commente sur sa ligne ci-dessous.
#
# ATTENTION EN CAS DE MODIFICATION : cette liste est dupliquee dans
# cercle_chat.html (fonction JS couleurAvatar(), meme ordre exact) pour
# que les messages ajoutes en direct par le WebSocket utilisent la meme
# couleur que ceux rendus par le serveur au chargement de la page. Les
# deux listes DOIVENT rester identiques, sinon l'avatar d'une meme
# personne change de couleur selon que le message vient du rendu initial
# ou du fil temps reel.
_PALETTE_AVATARS = [
    "#1E7A34",  # vert foret (ajuste depuis #2B8A3E : 4.37:1 -> 5.40:1 sur blanc)
    "#1864AB",  # bleu ocean (6.09:1 sur blanc)
    "#C23E0A",  # orange brule (ajuste depuis #D9480F : 4.30:1 -> 5.27:1 sur blanc)
    "#C2255C",  # rose fuchsia (5.66:1 sur blanc)
    "#087F5B",  # sarcelle (5.00:1 sur blanc)
    "#862E9C",  # violet amethyste (7.28:1 sur blanc) -- distinct de --primary, plus indigo
]


def _couleur_avatar(nom: str) -> str:
    """Couleur de fond deterministe pour l'avatar-initiale d'un auteur de
    message (§ chat de cercle) : somme des code points du nom modulo la
    taille de la palette, plutot qu'un hash cryptographique (md5 comme
    _version_asset ci-dessus) qui serait plus lourd a reproduire a
    l'identique en JS. ord() (Python) et charCodeAt() (JS) renvoient le
    meme code point Unicode pour un caractere donne, donc cette somme
    simple donne exactement le meme resultat des deux cotes."""
    if not nom:
        return _PALETTE_AVATARS[0]
    return _PALETTE_AVATARS[sum(ord(c) for c in nom) % len(_PALETTE_AVATARS)]


templates.env.globals["couleur_avatar"] = _couleur_avatar


def csp_nonce(request) -> str:
    """Nonce CSP de la requete courante, genere par le middleware de securite."""
    return getattr(request.state, "csp_nonce", "")


templates.env.globals["csp_nonce"] = csp_nonce


def couleur_avatar_index(nom: str) -> int:
    if not nom:
        return 0
    return sum(ord(c) for c in nom) % len(_PALETTE_AVATARS)


def avatar_taille_classe(taille: int) -> int:
    try:
        valeur = int(taille)
    except (TypeError, ValueError):
        return 32
    return valeur if valeur in (24, 27, 30, 32, 34, 72) else 32


templates.env.globals["couleur_avatar_index"] = couleur_avatar_index
templates.env.globals["avatar_taille_classe"] = avatar_taille_classe
