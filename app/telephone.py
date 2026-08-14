"""
Validation et normalisation du numero de telephone malgache.

Format accepte en saisie (frontend ET backend) :
  - international : +261 XX XX XXX XX  (261 + 9 chiffres)
  - local          : 0XX XX XXX XX     (10 chiffres, commence par 0)

Les deux formes designent le meme numero physique (+261 34 12 345 67
== 034 12 345 67) : le "0" local correspond au "+261" international,
jamais les deux en meme temps. On normalise donc TOUJOURS vers une
forme canonique unique avant stockage/comparaison, afin qu'une meme
personne ne puisse pas creer deux comptes avec deux ecritures du
meme numero (+261..., 261..., 0...).

Forme canonique retenue : locale a 10 chiffres ("034XXXXXXX"). C'est
deja le format present dans la base existante (voir placeholder
historique du formulaire d'inscription) — on ne change donc PAS le
format des donnees deja stockees, on se contente de le valider
strictement desormais et d'accepter en plus la saisie "+261" en
entree, normalisee vers ce meme format canonique.
"""
import re

# Prefixes mobiles malgaches valides : 032, 033, 034, 037, 038.
# (02x = fixe, non couvert ici — le formulaire d'inscription ne cible
# que le mobile, utilise pour l'identification/2FA du compte.)
_PREFIXES_MOBILES_VALIDES = ("032", "033", "034", "037", "038")

# Numero local complet : 0 + prefixe operateur (2 chiffres) + 7 chiffres = 10 chiffres.
_RE_LOCAL = re.compile(r"^0\d{9}$")


class TelephoneInvalide(ValueError):
    """Leve quand le numero fourni n'est pas un numero mobile malgache
    valide, quel que soit le format d'entree (local ou international)."""
    pass


def normaliser_telephone(brut: str) -> str:
    """Valide strictement puis renvoie le numero sous forme canonique
    locale a 10 chiffres ("034XXXXXXX"). Leve TelephoneInvalide sinon.

    Ne fait JAMAIS confiance a une validation deja faite cote client :
    cette fonction est appelee cote serveur et doit a elle seule
    rejeter tout ce qui n'est pas un numero mobile malgache valide,
    y compris les lettres, symboles, longueurs incorrectes ou
    indicatifs errones — meme si le formulaire HTML/JS a ete
    contourne (curl, devtools, etc.).
    """
    if brut is None:
        raise TelephoneInvalide("Numero de telephone manquant.")

    # On tolere les espaces et tirets de mise en forme (034 12 345 67,
    # 034-12-345-67) mais RIEN d'autre : aucune lettre, aucun autre
    # symbole n'est jamais accepte, meme au milieu du numero.
    sans_separateurs = re.sub(r"[ \-.]", "", brut.strip())

    if not sans_separateurs:
        raise TelephoneInvalide("Numero de telephone manquant.")

    if sans_separateurs.startswith("+261"):
        reste = sans_separateurs[4:]
        prefixe_normalise = "0" + reste
    elif sans_separateurs.startswith("261") and len(sans_separateurs) == 12:
        # "261341234567" sans le "+" — tolere, meme regle que ci-dessus.
        reste = sans_separateurs[3:]
        prefixe_normalise = "0" + reste
    elif sans_separateurs.startswith("0"):
        prefixe_normalise = sans_separateurs
    else:
        raise TelephoneInvalide(
            "Le numero doit commencer par +261 (ou par 0 pour le format local)."
        )

    # A ce stade, tout caractere non numerique est un rejet immediat —
    # c'est ce qui bloque explicitement les lettres (ex: "+261 34 AB 123 45").
    if not prefixe_normalise.isdigit():
        raise TelephoneInvalide("Le numero ne doit contenir que des chiffres.")

    if not _RE_LOCAL.match(prefixe_normalise):
        raise TelephoneInvalide(
            "Le numero doit contenir exactement 9 chiffres apres +261 "
            "(soit 10 chiffres au format local commencant par 0)."
        )

    if prefixe_normalise[:3] not in _PREFIXES_MOBILES_VALIDES:
        raise TelephoneInvalide(
            "Indicatif operateur invalide (attendu : 032, 033, 034, 037 ou 038)."
        )

    return prefixe_normalise


def telephone_affichage_international(canonique: str) -> str:
    """Pour l'affichage uniquement (ex: page profil) : convertit la forme
    canonique locale vers "+261 XX XX XXX XX". Ne pas utiliser pour la
    comparaison/stockage — toujours comparer sur la forme canonique."""
    reste = canonique[1:]  # retire le "0" local
    return f"+261 {reste[0:2]} {reste[2:4]} {reste[4:7]} {reste[7:9]}"
