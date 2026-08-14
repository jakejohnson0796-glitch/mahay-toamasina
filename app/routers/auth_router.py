"""
Inscription, connexion, deconnexion.
"""
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..models import Utilisateur, RoleUtilisateur, Filiere, CodeSecours2FA
from ..auth import hacher_mot_de_passe, verifier_mot_de_passe
from ..rate_limit import limite_depassee
from ..totp_2fa import generer_secret_totp, generer_qrcode_data_uri, verifier_code_totp, generer_codes_secours, hacher_code_secours, verifier_code_secours
from ..telephone import normaliser_telephone, TelephoneInvalide
from .. import subscription


def _ip_client(request: Request) -> str:
    return request.client.host if request.client else "inconnu"

router = APIRouter()


@router.get("/inscription")
def formulaire_inscription(request: Request, session: Session = Depends(get_session)):
    filieres = session.exec(select(Filiere)).all()
    return templates.TemplateResponse(
        request, "register.html", {"filieres": filieres, "erreur": None}
    )


@router.post("/inscription")
def inscription(
    request: Request,
    nom: str = Form(...),
    telephone: str = Form(...),
    mot_de_passe: str = Form(...),
    role: RoleUtilisateur = Form(RoleUtilisateur.ETUDIANT),
    filiere_id: Optional[int] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    # Anti-spam : limite la creation automatisee de comptes en masse
    # (chaque etudiant inscrit declenche un essai gratuit — voir
    # subscription.creer_essai_gratuit plus bas, donc un spam
    # d'inscriptions a aussi un cout direct, pas seulement un risque
    # d'abus des cercles/quiz).
    if limite_depassee(f"inscription:ip:{_ip_client(request)}", max_tentatives=8, fenetre_secondes=3600):
        filieres = session.exec(select(Filiere)).all()
        return templates.TemplateResponse(
            request,
            "register.html",
            {"filieres": filieres, "erreur": "Trop de tentatives d'inscription depuis cette adresse. Reessayez plus tard."},
        )

    # SECURITE : le formulaire public (register.html) ne propose que
    # "etudiant" et "sponsor" dans son <select>, mais rien n'empeche un
    # appel direct (curl/Postman/devtools) d'envoyer role=admin. Sans ce
    # garde-fou, n'importe qui obtiendrait un compte administrateur
    # complet en un seul POST non authentifie. Un compte ADMIN ne doit
    # jamais pouvoir naitre de l'auto-inscription : il est cree a la main
    # via app/creer_admin.py (execute par un operateur de confiance ayant
    # deja acces au serveur), jamais via cette route publique.
    if role not in (RoleUtilisateur.ETUDIANT, RoleUtilisateur.SPONSOR):
        role = RoleUtilisateur.ETUDIANT

    # SECURITE : le backend est la source de verite pour la validation du
    # numero, jamais le frontend seul — un numero avec des lettres, un
    # mauvais indicatif ou une mauvaise longueur est rejete ici meme si le
    # JS du formulaire a ete contourne. La normalisation (+261.../261.../0...
    # -> forme canonique locale "0XXXXXXXXX") empeche aussi qu'une meme
    # personne cree plusieurs comptes avec des variantes du meme numero.
    try:
        telephone_normalise = normaliser_telephone(telephone)
    except TelephoneInvalide as erreur:
        filieres = session.exec(select(Filiere)).all()
        return templates.TemplateResponse(
            request,
            "register.html",
            {"filieres": filieres, "erreur": str(erreur)},
        )

    deja_inscrit = session.exec(select(Utilisateur).where(Utilisateur.telephone == telephone_normalise)).first()
    if deja_inscrit:
        filieres = session.exec(select(Filiere)).all()
        return templates.TemplateResponse(
            request,
            "register.html",
            {"filieres": filieres, "erreur": "Ce numero est deja enregistre."},
        )

    utilisateur = Utilisateur(
        nom=nom,
        telephone=telephone_normalise,
        mot_de_passe_hash=hacher_mot_de_passe(mot_de_passe),
        role=role,
        filiere_id=filiere_id,
    )
    session.add(utilisateur)
    session.commit()
    session.refresh(utilisateur)

    if utilisateur.role == RoleUtilisateur.ETUDIANT:
        subscription.creer_essai_gratuit(session, utilisateur)

    request.session["user_id"] = utilisateur.id
    return RedirectResponse("/", status_code=303)


@router.get("/connexion")
def formulaire_connexion(request: Request):
    return templates.TemplateResponse(request, "login.html", {"erreur": None})


@router.post("/connexion")
def connexion(
    request: Request,
    telephone: str = Form(...),
    mot_de_passe: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    # Anti brute-force : deux limites cumulees.
    # - par IP : empeche un attaquant de tester en rafale plein de
    #   numeros differents depuis une seule machine/script.
    # - par numero cible : protege un compte precis meme si l'attaquant
    #   change d'IP ou passe par un proxy/VPN tournant.
    # Les deux compteurs avancent meme quand la 1ere limite bloque deja,
    # pour qu'un attaquant ne puisse pas "garder sous le seuil" l'un des
    # deux en jouant sur l'ordre des tentatives.
    trop_ip = limite_depassee(f"connexion:ip:{_ip_client(request)}", max_tentatives=15, fenetre_secondes=60)
    trop_tel = limite_depassee(f"connexion:tel:{telephone}", max_tentatives=6, fenetre_secondes=60)
    if trop_ip or trop_tel:
        return templates.TemplateResponse(
            request, "login.html", {"erreur": "Trop de tentatives. Reessayez dans une minute."}
        )

    # On accepte en connexion les memes variantes qu'a l'inscription
    # (+261..., 261..., 0...) en les ramenant a la meme forme canonique
    # que celle stockee en base — sinon un compte cree via "+261 34..."
    # ne pourrait jamais se reconnecter avec cette meme ecriture. Un
    # format non reconnu n'est PAS traite comme une erreur de validation
    # ici (pas de message distinct) : on le laisse simplement echouer au
    # lookup, pour ne pas donner d'indice supplementaire a un attaquant
    # et garder le meme message d'erreur generique.
    try:
        telephone_normalise = normaliser_telephone(telephone)
    except TelephoneInvalide:
        telephone_normalise = telephone

    utilisateur = session.exec(select(Utilisateur).where(Utilisateur.telephone == telephone_normalise)).first()
    if not utilisateur or not verifier_mot_de_passe(mot_de_passe, utilisateur.mot_de_passe_hash):
        return templates.TemplateResponse(
            request, "login.html", {"erreur": "Numero ou mot de passe incorrect."}
        )
    if utilisateur.banni:
        return templates.TemplateResponse(
            request, "login.html", {"erreur": "Ce compte a ete suspendu. Contactez un administrateur."}
        )

    if utilisateur.totp_active:
        # Ne pas ouvrir la session tout de suite : le mot de passe seul
        # ne suffit pas, il faut encore le code 2FA. On memorise juste
        # QUI est en train de se connecter (utile nulle part d'autre tant
        # que le code n'est pas verifie) et on redirige vers l'etape
        # suivante — voir verifier_2fa() ci-dessous.
        request.session["en_attente_2fa_user_id"] = utilisateur.id
        return RedirectResponse("/connexion/2fa", status_code=303)

    request.session["user_id"] = utilisateur.id
    return RedirectResponse("/", status_code=303)


@router.get("/connexion/2fa")
def page_2fa(request: Request):
    if not request.session.get("en_attente_2fa_user_id"):
        return RedirectResponse("/connexion", status_code=303)
    return templates.TemplateResponse(request, "connexion_2fa.html", {})


@router.post("/connexion/2fa")
def verifier_2fa(
    request: Request,
    code: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    user_id = request.session.get("en_attente_2fa_user_id")
    if not user_id:
        return RedirectResponse("/connexion", status_code=303)

    # Anti brute-force specifique : un code TOTP n'a que 6 chiffres
    # (1 million de combinaisons), largement a la portee d'un script sans
    # cette limite — bien plus severe que la limite de connexion normale.
    if limite_depassee(f"2fa:ip:{_ip_client(request)}", max_tentatives=8, fenetre_secondes=60) or \
       limite_depassee(f"2fa:user:{user_id}", max_tentatives=5, fenetre_secondes=60):
        return templates.TemplateResponse(
            request, "connexion_2fa.html", {"erreur": "Trop de tentatives. Reessayez dans une minute."}
        )

    utilisateur = session.get(Utilisateur, user_id)
    if not utilisateur or not utilisateur.totp_active:
        request.session.pop("en_attente_2fa_user_id", None)
        return RedirectResponse("/connexion", status_code=303)

    code_saisi = code.strip()
    valide = verifier_code_totp(utilisateur.totp_secret, code_saisi)

    if not valide and "-" in code_saisi:
        # Tentative avec un code de secours plutot qu'un code TOTP.
        codes_non_utilises = session.exec(
            select(CodeSecours2FA).where(
                CodeSecours2FA.utilisateur_id == user_id,
                CodeSecours2FA.utilise == False,  # noqa: E712
            )
        ).all()
        for c in codes_non_utilises:
            if verifier_code_secours(code_saisi, c.code_hash):
                c.utilise = True
                c.date_utilisation = datetime.utcnow()
                session.add(c)
                session.commit()
                valide = True
                break

    if not valide:
        return templates.TemplateResponse(
            request, "connexion_2fa.html", {"erreur": "Code invalide."}
        )

    request.session.pop("en_attente_2fa_user_id", None)
    request.session["user_id"] = utilisateur.id
    return RedirectResponse("/", status_code=303)


@router.get("/deconnexion")
def deconnexion(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


# ============================================================
# Gestion de la double authentification (2FA / TOTP)
# ============================================================

@router.get("/securite")
def page_securite(request: Request, session: Session = Depends(get_session)):
    utilisateur = session.get(Utilisateur, request.session.get("user_id"))
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    nb_codes_restants = 0
    if utilisateur.totp_active:
        nb_codes_restants = len(session.exec(
            select(CodeSecours2FA).where(
                CodeSecours2FA.utilisateur_id == utilisateur.id,
                CodeSecours2FA.utilise == False,  # noqa: E712
            )
        ).all())

    return templates.TemplateResponse(
        request, "securite.html",
        {"utilisateur": utilisateur, "nb_codes_restants": nb_codes_restants},
    )


@router.post("/securite/2fa/demarrer")
def demarrer_activation_2fa(request: Request, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = session.get(Utilisateur, request.session.get("user_id"))
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    if utilisateur.totp_active:
        return RedirectResponse("/securite", status_code=303)

    # Le secret est genere et garde en session UNIQUEMENT tant qu'il
    # n'est pas confirme par un code valide — jamais ecrit en base avant
    # cette confirmation, pour ne jamais laisser un secret "orphelin" et
    # non verifie associe au compte (voir confirmer_activation_2fa).
    secret = generer_secret_totp()
    request.session["totp_secret_en_attente"] = secret
    return RedirectResponse("/securite/2fa/configurer", status_code=303)


@router.get("/securite/2fa/configurer")
def page_configurer_2fa(request: Request, session: Session = Depends(get_session)):
    utilisateur = session.get(Utilisateur, request.session.get("user_id"))
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    secret = request.session.get("totp_secret_en_attente")
    if not secret:
        return RedirectResponse("/securite", status_code=303)

    qr_data_uri = generer_qrcode_data_uri(secret, utilisateur.telephone)
    return templates.TemplateResponse(
        request, "configurer_2fa.html",
        {"utilisateur": utilisateur, "qr_data_uri": qr_data_uri, "secret": secret},
    )


@router.post("/securite/2fa/confirmer")
def confirmer_activation_2fa(
    request: Request,
    code: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = session.get(Utilisateur, request.session.get("user_id"))
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    secret = request.session.get("totp_secret_en_attente")
    if not secret:
        return RedirectResponse("/securite", status_code=303)

    if not verifier_code_totp(secret, code):
        qr_data_uri = generer_qrcode_data_uri(secret, utilisateur.telephone)
        return templates.TemplateResponse(
            request, "configurer_2fa.html",
            {"utilisateur": utilisateur, "qr_data_uri": qr_data_uri, "secret": secret, "erreur": "Code invalide, reessayez."},
        )

    utilisateur.totp_secret = secret
    utilisateur.totp_active = True
    session.add(utilisateur)

    codes_clairs = generer_codes_secours()
    for c in codes_clairs:
        session.add(CodeSecours2FA(utilisateur_id=utilisateur.id, code_hash=hacher_code_secours(c)))
    session.commit()

    request.session.pop("totp_secret_en_attente", None)
    # Les codes en clair ne sont jamais stockes nulle part (ni session, ni
    # base) — uniquement passes une fois au template pour cet affichage,
    # perdus des que la page suivante est quittee.
    return templates.TemplateResponse(
        request, "codes_secours_2fa.html", {"utilisateur": utilisateur, "codes": codes_clairs},
    )


@router.post("/securite/2fa/desactiver")
def desactiver_2fa(
    request: Request,
    mot_de_passe: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = session.get(Utilisateur, request.session.get("user_id"))
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    # Desactiver la 2FA est une action sensible (retire une protection) :
    # on redemande le mot de passe, meme si la session est deja ouverte —
    # empeche quelqu'un qui recupere un appareil deverrouille de
    # desactiver la 2FA en deux clics sans rien connaitre du compte.
    if not verifier_mot_de_passe(mot_de_passe, utilisateur.mot_de_passe_hash):
        return templates.TemplateResponse(
            request, "securite.html",
            {"utilisateur": utilisateur, "nb_codes_restants": 0, "erreur": "Mot de passe incorrect."},
        )

    utilisateur.totp_secret = None
    utilisateur.totp_active = False
    session.add(utilisateur)

    anciens_codes = session.exec(select(CodeSecours2FA).where(CodeSecours2FA.utilisateur_id == utilisateur.id)).all()
    for c in anciens_codes:
        session.delete(c)
    session.commit()

    return RedirectResponse("/securite?desactive=1", status_code=303)


@router.post("/securite/2fa/regenerer-codes-secours")
def regenerer_codes_secours(request: Request, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = session.get(Utilisateur, request.session.get("user_id"))
    if not utilisateur or not utilisateur.totp_active:
        return RedirectResponse("/securite", status_code=303)

    anciens_codes = session.exec(select(CodeSecours2FA).where(CodeSecours2FA.utilisateur_id == utilisateur.id)).all()
    for c in anciens_codes:
        session.delete(c)

    codes_clairs = generer_codes_secours()
    for c in codes_clairs:
        session.add(CodeSecours2FA(utilisateur_id=utilisateur.id, code_hash=hacher_code_secours(c)))
    session.commit()

    return templates.TemplateResponse(
        request, "codes_secours_2fa.html", {"utilisateur": utilisateur, "codes": codes_clairs},
    )
