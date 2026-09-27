"""
Validation et normalisation du numero de telephone malgache.

Format accepte en saisie (frontend ET backend) :
  - international prefere pour l'interface : +261 034 12 345 67
    (10 chiffres saisis apres +261, dont le 0 local)
  - international historique accepte : +261 34 12 345 67
    (9 chiffres apres +261, sans le 0 local)
  - local : 034 12 345 67 (10 chiffres, commence par 0)

La forme canonique reste locale a 10 chiffres. Le backend accepte donc
le nouveau format demande par l'interface (+261 suivi de 10 chiffres)
tout en conservant l'ancien format international a 9 chiffres pour ne
pas casser les comptes existants.

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
        if len(reste) == 10 and reste.startswith("0"):
            # Nouveau format d'interface : +261 + 10 chiffres,
            # en conservant le 0 local dans la saisie.
            prefixe_normalise = reste
        elif len(reste) == 9:
            # Compatibilite avec l'ancien format international.
            prefixe_normalise = "0" + reste
        else:
            raise TelephoneInvalide(
                "Entrez 10 chiffres apres +261 (par exemple 0341234567)."
            )
    elif sans_separateurs.startswith("261"):
        reste = sans_separateurs[3:]
        if len(reste) == 10 and reste.startswith("0"):
            prefixe_normalise = reste
        elif len(reste) == 9:
            prefixe_normalise = "0" + reste
        else:
            raise TelephoneInvalide(
                "Entrez 10 chiffres apres 261 (par exemple 0341234567)."
            )
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
            "Le numero doit contenir exactement 10 chiffres au format local "
            "(par exemple 0341234567)."
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
