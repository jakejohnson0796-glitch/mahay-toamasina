"""
Inscription, connexion, deconnexion.
"""
from typing import Optional
from datetime import datetime, timedelta
import hashlib
import secrets

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse, FileResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..models import Utilisateur, RoleUtilisateur, Filiere, Mention, Universite, CodeSecours2FA, CodeEmail2FA, CodeReinitialisationMotDePasse, DemandeChangementFiliere, StatutDemandeChangementFiliere, Notification, TypeNotification
from .. import referentiel_academique
from ..referentiel import NIVEAUX
from ..auth import utilisateur_courant, hacher_mot_de_passe, verifier_mot_de_passe, empreinte_session_utilisateur, creer_rappel_inactivite_si_necessaire, jours_inactivite, notifier_nouvelle_inscription_aux_admins
from ..rate_limit import limite_depassee
from ..totp_2fa import generer_secret_totp, generer_qrcode_data_uri, verifier_code_totp, generer_codes_secours, hacher_code_secours, verifier_code_secours
from ..telephone import normaliser_telephone, TelephoneInvalide
from ..web_utils import entier_ou_none
from .. import subscription
from ..storage import sauvegarder_avatar, obtenir_url_telechargement, supprimer_fichier, stockage_distant_actif, FichierInvalide
from ..email_utils import envoyer_email, email_configure, EmailNonConfigure
from ..conditions_legales import VERSION_CONDITIONS


def _ip_client(request: Request) -> str:
    return request.client.host if request.client else "inconnu"


def _redirection_apres_connexion(utilisateur: Utilisateur) -> RedirectResponse:
    """Point de sortie commun aux deux chemins de connexion reussie (avec
    et sans 2FA, voir connexion() et verifier_2fa()) : si le mot de passe
    vient d'etre reinitialise par un admin ou via /mot-de-passe-oublie,
    on renvoie vers /securite plutot que l'accueil -- le rappel visible
    tant que doit_changer_mot_de_passe est actif (voir la carte "Changer
    mon mot de passe" dans securite.html) s'affiche alors immediatement,
    au lieu de dependre de l'utilisateur pour aller le chercher lui-meme."""
    if utilisateur.doit_changer_mot_de_passe:
        return RedirectResponse("/securite", status_code=303)
    return RedirectResponse("/", status_code=303)

router = APIRouter()

LONGUEUR_MIN_MOT_DE_PASSE = 8
LONGUEUR_MAX_MOT_DE_PASSE = 72
LONGUEUR_MAX_NOM = 120


def _rotation_session_authentifiee(request: Request) -> None:
    """Rotation de session apres authentification en conservant le jeton CSRF."""
    jeton_csrf = request.session.get("_csrf_token")
    request.session.clear()
    if jeton_csrf:
        request.session["_csrf_token"] = jeton_csrf


def _ouvrir_session_authentifiee(request: Request, utilisateur: Utilisateur) -> None:
    """Finalise une authentification reussie avec une nouvelle session propre."""
    _rotation_session_authentifiee(request)
    request.session["user_id"] = utilisateur.id
    request.session["auth_fingerprint"] = empreinte_session_utilisateur(utilisateur)



def _preparer_rappel_inactivite_apres_connexion(
    request: Request,
    session: Session,
    utilisateur: Utilisateur,
) -> None:
    jours, notification_id = creer_rappel_inactivite_si_necessaire(utilisateur, session)
    if notification_id:
        request.session["notification_inactivite"] = {
            "notification_id": notification_id,
            "jours": jours,
        }

def _telephone_rate_key(telephone: str) -> str:
    try:
        return f"tel:{normaliser_telephone(telephone)}"
    except TelephoneInvalide:
        brute = (telephone or "").strip().casefold()[:128]
        return "invalide:" + hashlib.sha256(brute.encode("utf-8")).hexdigest()[:16]


def _contexte_formulaire_inscription(session: Session, erreur: Optional[str] = None) -> dict:
    """Regroupe le contexte commun aux (re)rendus de register.html — la
    liste des Composante/Filiere n'y figure plus : elles sont chargees
    en cascade par le JS via /api/academique/... (§7-8 du brief), donc
    seule la liste des Universite (etape 1, toujours affichee) est
    encore preparee cote serveur."""
    return {
        "universites": session.exec(select(Universite).where(Universite.est_active == True)).all(),  # noqa: E712
        "niveaux": NIVEAUX,
        "erreur": erreur,
        "version_conditions": VERSION_CONDITIONS,
    }


@router.get("/inscription")
def formulaire_inscription(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(
        request, "register.html", _contexte_formulaire_inscription(session)
    )


@router.post("/inscription")
def inscription(
    request: Request,
    nom: str = Form(...),
    telephone: str = Form(...),
    mot_de_passe: str = Form(...),
    role: RoleUtilisateur = Form(RoleUtilisateur.ETUDIANT),
    mention_id: Optional[str] = Form(None),
    filiere_id: Optional[str] = Form(None),
    universite_id: Optional[str] = Form(None),
    composante_id: Optional[str] = Form(None),
    niveau: Optional[str] = Form(None),
    accepter_conditions: str = Form(""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    mention_id_nettoye = entier_ou_none(mention_id)
    filiere_id_nettoye = entier_ou_none(filiere_id)
    universite_id_nettoye = entier_ou_none(universite_id)
    composante_id_nettoye = entier_ou_none(composante_id)

    # La case obligatoire côté navigateur est doublée d'un contrôle serveur :
    # un POST direct ne peut pas créer de compte sans accepter les conditions.
    if accepter_conditions != "oui":
        return templates.TemplateResponse(
            request,
            "register.html",
            _contexte_formulaire_inscription(
                session,
                "Vous devez lire et accepter les conditions d’utilisation et la charte éthique avant de créer un compte.",
            ),
            status_code=400,
        )

    nom = nom.strip()
    if not nom or len(nom) > LONGUEUR_MAX_NOM:
        return templates.TemplateResponse(
            request, "register.html",
            _contexte_formulaire_inscription(session, f"Le nom est obligatoire et limite a {LONGUEUR_MAX_NOM} caracteres."),
        )
    if len(mot_de_passe) < LONGUEUR_MIN_MOT_DE_PASSE or len(mot_de_passe) > LONGUEUR_MAX_MOT_DE_PASSE:
        return templates.TemplateResponse(
            request, "register.html",
            _contexte_formulaire_inscription(session, f"Le mot de passe doit contenir entre {LONGUEUR_MIN_MOT_DE_PASSE} et {LONGUEUR_MAX_MOT_DE_PASSE} caracteres."),
        )

    # Anti-spam : limite la creation automatisee de comptes en masse
    # (chaque etudiant inscrit declenche un essai gratuit — voir
    # subscription.creer_essai_gratuit plus bas, donc un spam
    # d'inscriptions a aussi un cout direct, pas seulement un risque
    # d'abus des cercles/quiz).
    if limite_depassee(f"inscription:ip:{_ip_client(request)}", max_tentatives=8, fenetre_secondes=3600):
        return templates.TemplateResponse(
            request, "register.html",
            _contexte_formulaire_inscription(session, "Trop de tentatives d'inscription depuis cette adresse. Reessayez plus tard."),
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

    # §7-9 du brief refonte academique nationale, revu le 10/09/2026
    # (Filiere.niveau) : pour un(e) ETUDIANT(E), universite/mention/niveau
    # deviennent obligatoires et VALIDES cote backend (jamais uniquement
    # cote JS, qui peut etre contourne par un appel direct) -- filiere_id,
    # lui, reste FACULTATIF : un etudiant en tronc commun (aucun parcours
    # nomme a son niveau) n'a justement rien a choisir de plus. Un
    # sponsor/repetiteur n'a pas de parcours academique a declarer — ces
    # 4 champs restent optionnels pour ce role, comme avant.
    if role == RoleUtilisateur.ETUDIANT:
        erreur_academique = referentiel_academique.erreur_choix_academique(
            session,
            universite_id_nettoye,
            composante_id_nettoye,
            mention_id_nettoye,
            filiere_id_nettoye,
            niveau,
            set(NIVEAUX),
        )
        if erreur_academique:
            return templates.TemplateResponse(
                request, "register.html",
                _contexte_formulaire_inscription(session, erreur_academique),
            )
    else:
        # Un sponsor n'a pas de parcours academique : on ignore ces
        # champs meme si un appel direct les fournissait, plutot que de
        # les valider pour un role qui n'en a pas besoin.
        universite_id_nettoye = None
        composante_id_nettoye = None
        mention_id_nettoye = None
        filiere_id_nettoye = None
        niveau = None

    # SECURITE : le backend est la source de verite pour la validation du
    # numero, jamais le frontend seul — un numero avec des lettres, un
    # mauvais indicatif ou une mauvaise longueur est rejete ici meme si le
    # JS du formulaire a ete contourne. La normalisation (+261.../261.../0...
    # -> forme canonique locale "0XXXXXXXXX") empeche aussi qu'une meme
    # personne cree plusieurs comptes avec des variantes du meme numero.
    try:
        telephone_normalise = normaliser_telephone(telephone)
    except TelephoneInvalide as erreur:
        return templates.TemplateResponse(
            request, "register.html",
            _contexte_formulaire_inscription(session, str(erreur)),
        )

    deja_inscrit = session.exec(select(Utilisateur).where(Utilisateur.telephone == telephone_normalise)).first()
    if deja_inscrit:
        return templates.TemplateResponse(
            request, "register.html",
            _contexte_formulaire_inscription(session, "Ce numero est deja enregistre."),
        )

    utilisateur = Utilisateur(
        nom=nom,
        telephone=telephone_normalise,
        mot_de_passe_hash=hacher_mot_de_passe(mot_de_passe),
        role=role,
        mention_id=mention_id_nettoye,
        filiere_id=filiere_id_nettoye,
        faculte_id=composante_id_nettoye,
        universite_id=universite_id_nettoye,
        niveau=niveau,
        conditions_acceptees_le=datetime.utcnow(),
        version_conditions_acceptees=VERSION_CONDITIONS,
        derniere_activite_le=datetime.utcnow(),
    )
    session.add(utilisateur)
    session.commit()
    session.refresh(utilisateur)

    if utilisateur.role == RoleUtilisateur.ETUDIANT:
        subscription.creer_essai_gratuit(session, utilisateur)

    # Notification interne : chaque administrateur recoit une alerte.
    notifier_nouvelle_inscription_aux_admins(utilisateur, session)
    session.commit()

    _ouvrir_session_authentifiee(request, utilisateur)
    if utilisateur.role == RoleUtilisateur.ETUDIANT:
        return RedirectResponse("/bienvenue", status_code=303)
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
    try:
        telephone_normalise = normaliser_telephone(telephone)
    except TelephoneInvalide:
        telephone_normalise = telephone
    trop_tel = limite_depassee(f"connexion:{_telephone_rate_key(telephone)}", max_tentatives=6, fenetre_secondes=60)
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
    utilisateur = session.exec(select(Utilisateur).where(Utilisateur.telephone == telephone_normalise)).first()
    if not utilisateur or not verifier_mot_de_passe(mot_de_passe, utilisateur.mot_de_passe_hash):
        return templates.TemplateResponse(
            request, "login.html", {"erreur": "Numero ou mot de passe incorrect."}
        )
    if utilisateur.banni:
        return templates.TemplateResponse(
            request, "login.html", {"erreur": "Ce compte a ete suspendu. Contactez un administrateur."}
        )

    if utilisateur.totp_active or utilisateur.email_otp_active:
        _rotation_session_authentifiee(request)
        # Le mot de passe seul ne suffit pas : on attend l'une des methodes
        # MFA activees avant d'ouvrir la session authentifiee.
        request.session["en_attente_2fa_user_id"] = utilisateur.id
        request.session["en_attente_2fa_email_statut"] = "non_envoye"
        request.session["en_attente_2fa_email_envoye"] = False
        request.session.pop("en_attente_2fa_methode", None)
        # Si l'email est la seule methode active, envoyer tout de suite le
        # code attendu. Avec TOTP actif, l'utilisateur choisit sa methode
        # sur l'ecran suivant et aucun email n'est envoye sans demande.
        if utilisateur.email_otp_active and not utilisateur.totp_active:
            statut_email = _demander_code_email_connexion(request, session, utilisateur)
            request.session["en_attente_2fa_email_statut"] = statut_email
            request.session["en_attente_2fa_email_envoye"] = statut_email == "envoye"
        return RedirectResponse("/connexion/2fa", status_code=303)

    _ouvrir_session_authentifiee(request, utilisateur)
    _preparer_rappel_inactivite_apres_connexion(request, session, utilisateur)
    return _redirection_apres_connexion(utilisateur)


@router.get("/connexion/2fa")
def page_2fa(request: Request, session: Session = Depends(get_session)):
    user_id = request.session.get("en_attente_2fa_user_id")
    if not user_id:
        return RedirectResponse("/connexion", status_code=303)

    utilisateur = session.get(Utilisateur, user_id)
    if not utilisateur or not (utilisateur.totp_active or utilisateur.email_otp_active):
        request.session.pop("en_attente_2fa_user_id", None)
        request.session.pop("en_attente_2fa_email_envoye", None)
        request.session.pop("en_attente_2fa_email_statut", None)
        request.session.pop("en_attente_2fa_methode", None)
        return RedirectResponse("/connexion", status_code=303)

    codes_secours_disponibles = session.exec(
        select(CodeSecours2FA).where(
            CodeSecours2FA.utilisateur_id == user_id,
            CodeSecours2FA.utilise == False,  # noqa: E712
        )
    ).first() is not None
    return templates.TemplateResponse(
        request,
        "connexion_2fa.html",
        {
            "totp_disponible": utilisateur.totp_active,
            "email_disponible": utilisateur.email_otp_active,
            "email_masque": _masquer_email(utilisateur.email),
            "email_envoye": bool(request.session.get("en_attente_2fa_email_envoye")),
            "email_statut": request.session.get("en_attente_2fa_email_statut", "non_envoye"),
            "methode_defaut": request.session.get("en_attente_2fa_methode") or ("totp" if utilisateur.totp_active else "email"),
            "codes_secours_disponibles": codes_secours_disponibles,
        },
    )


@router.post("/connexion/2fa/envoyer-email")
def envoyer_code_email_connexion(
    request: Request,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    user_id = request.session.get("en_attente_2fa_user_id")
    if not user_id:
        return RedirectResponse("/connexion", status_code=303)
    utilisateur = session.get(Utilisateur, user_id)
    if not utilisateur or not utilisateur.email_otp_active:
        return RedirectResponse("/connexion", status_code=303)

    statut = _demander_code_email_connexion(request, session, utilisateur)
    request.session["en_attente_2fa_email_statut"] = statut
    request.session["en_attente_2fa_email_envoye"] = statut == "envoye"
    request.session["en_attente_2fa_methode"] = "email"
    return RedirectResponse("/connexion/2fa", status_code=303)


@router.post("/connexion/2fa")
def verifier_2fa(
    request: Request,
    code: str = Form(...),
    methode: str = Form("totp"),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    user_id = request.session.get("en_attente_2fa_user_id")
    if not user_id:
        return RedirectResponse("/connexion", status_code=303)

    utilisateur = session.get(Utilisateur, user_id)
    if not utilisateur or not (utilisateur.totp_active or utilisateur.email_otp_active):
        request.session.pop("en_attente_2fa_user_id", None)
        request.session.pop("en_attente_2fa_email_envoye", None)
        request.session.pop("en_attente_2fa_email_statut", None)
        request.session.pop("en_attente_2fa_methode", None)
        return RedirectResponse("/connexion", status_code=303)

    # Limitation stricte pour les codes courts : toutes les methodes sont
    # protegees contre les tentatives massives, par adresse IP et par compte.
    trop_ip = limite_depassee(f"2fa:ip:{_ip_client(request)}", max_tentatives=8, fenetre_secondes=60)
    trop_utilisateur = limite_depassee(f"2fa:user:{user_id}", max_tentatives=5, fenetre_secondes=60)
    if trop_ip or trop_utilisateur:
        codes_secours_disponibles = session.exec(
            select(CodeSecours2FA).where(
                CodeSecours2FA.utilisateur_id == user_id,
                CodeSecours2FA.utilise == False,  # noqa: E712
            )
        ).first() is not None
        return templates.TemplateResponse(
            request,
            "connexion_2fa.html",
            {
                "erreur": "Trop de tentatives. Reessayez dans une minute.",
                "totp_disponible": utilisateur.totp_active,
                "email_disponible": utilisateur.email_otp_active,
                "email_masque": _masquer_email(utilisateur.email),
                "email_envoye": bool(request.session.get("en_attente_2fa_email_envoye")),
                "email_statut": request.session.get("en_attente_2fa_email_statut", "non_envoye"),
                "methode_defaut": request.session.get("en_attente_2fa_methode") or ("totp" if utilisateur.totp_active else "email"),
                "codes_secours_disponibles": codes_secours_disponibles,
            },
        )

    code_saisi = code.strip()
    valide = False

    if methode == "email" and utilisateur.email_otp_active:
        valide = _verifier_code_email_2fa(session, user_id, code_saisi, "connexion")
    elif methode == "totp" and utilisateur.totp_active:
        valide = verifier_code_totp(utilisateur.totp_secret, code_saisi)
    elif methode == "secours":
        valide = False

    # Un code de secours peut être utilisé à la place du facteur choisi.
    # Il est marqué consommé avant que la session authentifiée soit ouverte.
    if not valide and "-" in code_saisi:
        codes_non_utilises = session.exec(
            select(CodeSecours2FA).where(
                CodeSecours2FA.utilisateur_id == user_id,
                CodeSecours2FA.utilise == False,  # noqa: E712
            )
        ).all()
        for entree in codes_non_utilises:
            if verifier_code_secours(code_saisi, entree.code_hash):
                entree.utilise = True
                entree.date_utilisation = datetime.utcnow()
                session.add(entree)
                session.commit()
                valide = True
                break

    if not valide:
        codes_secours_disponibles = session.exec(
            select(CodeSecours2FA).where(
                CodeSecours2FA.utilisateur_id == user_id,
                CodeSecours2FA.utilise == False,  # noqa: E712
            )
        ).first() is not None
        return templates.TemplateResponse(
            request,
            "connexion_2fa.html",
            {
                "erreur": "Code invalide ou expire.",
                "totp_disponible": utilisateur.totp_active,
                "email_disponible": utilisateur.email_otp_active,
                "email_masque": _masquer_email(utilisateur.email),
                "email_envoye": bool(request.session.get("en_attente_2fa_email_envoye")),
                "email_statut": request.session.get("en_attente_2fa_email_statut", "non_envoye"),
                "methode_defaut": methode if methode in ("totp", "email", "secours") else "totp",
                "codes_secours_disponibles": codes_secours_disponibles,
            },
        )

    request.session.pop("en_attente_2fa_email_envoye", None)
    request.session.pop("en_attente_2fa_email_statut", None)
    request.session.pop("en_attente_2fa_methode", None)
    _ouvrir_session_authentifiee(request, utilisateur)
    _preparer_rappel_inactivite_apres_connexion(request, session, utilisateur)
    return _redirection_apres_connexion(utilisateur)


# ============================================================
# Mot de passe oublie (code envoye par EMAIL, gratuit -- voir
# app/email_utils.py). L'identifiant reste le TELEPHONE (comme pour la
# connexion) : l'email n'est qu'un canal de secours facultatif renseigne
# sur /securite (voir modifier_email() plus haut). Un compte sans email
# enregistre, ou si le SMTP n'est pas configure sur ce serveur, ne peut
# pas passer par ce flux self-service -- seule la reinitialisation par
# un admin (/admin/utilisateurs) reste possible pour lui.
#
# Comme pour la connexion, la reponse a l'etape "saisir mon numero" est
# TOUJOURS la meme (redirection vers l'etape code), que le compte
# existe ou non, qu'il ait un email ou non, et meme si la limite
# anti-abus est depassee : ne jamais laisser deviner par le
# comportement de la page si un numero est enregistre sur le site.
# ============================================================

DUREE_VALIDITE_CODE_RESET = timedelta(minutes=15)


@router.get("/mot-de-passe-oublie")
def formulaire_mot_de_passe_oublie(request: Request):
    return templates.TemplateResponse(request, "mot_de_passe_oublie.html", {})


@router.post("/mot-de-passe-oublie")
def demander_reinitialisation(
    request: Request,
    telephone: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    # Anti-abus : memes deux limites cumulees que la connexion (voir
    # connexion() plus haut) -- eviter qu'un script fasse partir des
    # emails en rafale (cout de service + spam pour la victime) en
    # essayant plein de numeros, ou en boucle sur UN numero precis.
    trop_ip = limite_depassee(f"reinit:ip:{_ip_client(request)}", max_tentatives=8, fenetre_secondes=3600)
    trop_tel = limite_depassee(f"reinit:{_telephone_rate_key(telephone)}", max_tentatives=3, fenetre_secondes=3600)

    if not (trop_ip or trop_tel):
        try:
            telephone_normalise = normaliser_telephone(telephone)
        except TelephoneInvalide:
            telephone_normalise = telephone

        utilisateur = session.exec(select(Utilisateur).where(Utilisateur.telephone == telephone_normalise)).first()

        if utilisateur and utilisateur.email and email_configure():
            code = f"{secrets.randbelow(1_000_000):06d}"
            session.add(CodeReinitialisationMotDePasse(
                utilisateur_id=utilisateur.id,
                code_hash=hacher_mot_de_passe(code),
                expire_le=datetime.utcnow() + DUREE_VALIDITE_CODE_RESET,
            ))
            session.commit()

            try:
                envoyer_email(
                    utilisateur.email,
                    "Gasy Mahay — code de reinitialisation",
                    f"Votre code de reinitialisation de mot de passe est : {code}\n\n"
                    "Il expire dans 15 minutes. Si vous n'etes pas a l'origine de cette "
                    "demande, ignorez cet email : votre mot de passe actuel reste valable.",
                )
            except Exception as exc:
                # Echec d'envoi (hote SMTP injoignable, identifiants
                # invalides...) : jamais repercute dans la reponse (le
                # message reste generique, voir mot_de_passe_oublie_code.html)
                # pour ne pas reveler d'info a un attaquant -- mais on le
                # journalise cote serveur pour pouvoir diagnostiquer.
                print(f"[mot-de-passe-oublie] echec envoi email : {exc}")

            request.session["en_attente_reinit_user_id"] = utilisateur.id

    return RedirectResponse("/mot-de-passe-oublie/code", status_code=303)


@router.get("/mot-de-passe-oublie/code")
def formulaire_code_reinitialisation(request: Request):
    return templates.TemplateResponse(request, "mot_de_passe_oublie_code.html", {"erreur": None})


@router.post("/mot-de-passe-oublie/code")
def verifier_code_reinitialisation(
    request: Request,
    code: str = Form(...),
    nouveau_mot_de_passe: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    erreur_generique = "Code invalide ou expire."
    user_id = request.session.get("en_attente_reinit_user_id")

    # Anti brute-force sur le code (6 chiffres, 1 million de
    # combinaisons) : meme principe double IP+cible que la 2FA plus haut.
    trop_ip = limite_depassee(f"reinit-code:ip:{_ip_client(request)}", max_tentatives=10, fenetre_secondes=600)
    trop_user = user_id and limite_depassee(f"reinit-code:user:{user_id}", max_tentatives=6, fenetre_secondes=600)
    if trop_ip or trop_user:
        return templates.TemplateResponse(
            request, "mot_de_passe_oublie_code.html", {"erreur": "Trop de tentatives. Reessayez dans quelques minutes."}
        )

    # Pas de session en attente : soit personne n'a demande de code
    # (acces direct a cette page), soit le numero saisi a l'etape
    # precedente n'a genere aucun code (compte inexistant/sans email).
    # Meme message d'erreur que "code invalide" dans tous les cas.
    if not user_id:
        return templates.TemplateResponse(request, "mot_de_passe_oublie_code.html", {"erreur": erreur_generique})

    if len(nouveau_mot_de_passe) < LONGUEUR_MIN_MOT_DE_PASSE or len(nouveau_mot_de_passe) > LONGUEUR_MAX_MOT_DE_PASSE:
        return templates.TemplateResponse(
            request, "mot_de_passe_oublie_code.html",
            {"erreur": f"Le nouveau mot de passe doit faire au moins {LONGUEUR_MIN_MOT_DE_PASSE} caracteres."},
        )

    codes_valides = session.exec(
        select(CodeReinitialisationMotDePasse).where(
            CodeReinitialisationMotDePasse.utilisateur_id == user_id,
            CodeReinitialisationMotDePasse.utilise == False,  # noqa: E712
            CodeReinitialisationMotDePasse.expire_le > datetime.utcnow(),
        )
    ).all()

    code_saisi = code.strip()
    entree_correspondante = next(
        (entree for entree in codes_valides if verifier_mot_de_passe(code_saisi, entree.code_hash)), None
    )
    if not entree_correspondante:
        return templates.TemplateResponse(request, "mot_de_passe_oublie_code.html", {"erreur": erreur_generique})

    utilisateur = session.get(Utilisateur, user_id)
    entree_correspondante.utilise = True
    utilisateur.mot_de_passe_hash = hacher_mot_de_passe(nouveau_mot_de_passe)
    utilisateur.doit_changer_mot_de_passe = False
    session.add(entree_correspondante)
    session.add(utilisateur)
    session.commit()
    request.session.pop("en_attente_reinit_user_id", None)

    return RedirectResponse("/connexion?ok=mot_de_passe_reinitialise", status_code=303)


@router.post("/deconnexion")
def deconnexion(request: Request, _csrf: None = Depends(verifier_csrf)):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


# ============================================================
# Actualisation du profil academique (§21-24 du brief refonte
# academique nationale) : ecran dedie pour un compte existant dont
# referentiel_academique.profil_academique_incomplet() est vrai
# (universite/filiere/niveau manquant ou devenu incoherent). La
# notification qui y renvoie s'affiche sur toutes les pages tant que ce
# n'est pas resolu — voir templating.py (profil_academique_a_actualiser)
# et base.html. Reutilise la meme cascade Universite -> Composante ->
# Filiere -> Niveau que l'inscription (memes endpoints
# /api/academique/...), et la MEME validation stricte cote backend
# (§9 : une combinaison universite/filiere incoherente est rejetee ici
# aussi, jamais seulement empechee par le JS).
# ============================================================

def _rendu_formulaire_profil_academique(
    request: Request,
    utilisateur: Utilisateur,
    session: Session,
    erreur: Optional[str] = None,
):
    demande_en_attente = session.exec(
        select(DemandeChangementFiliere).where(
            DemandeChangementFiliere.utilisateur_id == utilisateur.id,
            DemandeChangementFiliere.statut == StatutDemandeChangementFiliere.EN_ATTENTE,
        )
    ).first()
    filiere_demandee = (
        session.get(Filiere, demande_en_attente.nouvelle_filiere_id)
        if demande_en_attente and demande_en_attente.nouvelle_filiere_id
        else None
    )
    mention_demandee = (
        session.get(Mention, demande_en_attente.nouvelle_mention_id)
        if demande_en_attente and demande_en_attente.nouvelle_mention_id
        else None
    )
    profil = referentiel_academique.contexte_profil_academique(utilisateur, session)

    return templates.TemplateResponse(
        request,
        "profil_academique.html",
        {
            "utilisateur": utilisateur,
            "universites": session.exec(
                select(Universite).where(Universite.est_active == True)  # noqa: E712
            ).all(),
            "niveaux": NIVEAUX,
            "erreur": erreur,
            "demande_en_attente": demande_en_attente,
            "filiere_demandee": filiere_demandee,
            "mention_demandee": mention_demandee,
            "composante_id_actuelle": profil["faculte"].id if profil["faculte"] else None,
        },
    )


@router.get("/profil/academique")
def formulaire_actualisation_academique(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    return _rendu_formulaire_profil_academique(request, utilisateur, session)


@router.post("/profil/academique")
def actualiser_profil_academique(
    request: Request,
    universite_id: Optional[str] = Form(None),
    composante_id: Optional[str] = Form(None),
    mention_id: Optional[str] = Form(None),
    filiere_id: Optional[str] = Form(None),
    niveau: Optional[str] = Form(None),
    motif_filiere: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Universite et niveau restent modifiables librement (comme avant).
    La mention et la filiere, elles, NE PEUVENT PAS etre modifiees
    directement depuis cette route (demande explicite de Jake) : elles
    passent desormais par une DemandeChangementFiliere soumise a
    validation d'un admin — voir /admin/referentiel/demandes-filiere.
    Etendue le 10/09/2026 (Filiere.niveau, Utilisateur.mention_id) pour
    couvrir la mention en plus de la filiere : une demande peut porter
    sur la mention seule (ex: passage/retour au tronc commun a un
    niveau qui n'a pas de parcours nomme), sur la filiere seule, ou sur
    les deux ensemble."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    if utilisateur.role not in (RoleUtilisateur.ETUDIANT, RoleUtilisateur.PROFESSEUR):
        return RedirectResponse("/securite", status_code=303)

    def _contexte(message_erreur: str):
        return _rendu_formulaire_profil_academique(request, utilisateur, session, message_erreur)

    universite_id_nettoye = entier_ou_none(universite_id)
    composante_id_nettoye = entier_ou_none(composante_id)
    mention_id_nettoye = entier_ou_none(mention_id)
    filiere_id_nettoye = entier_ou_none(filiere_id)

    # Meme validateur que l'inscription : le profil ne peut jamais
    # enregistrer une combinaison Universite / Mention / Parcours / Niveau
    # incoherente. La mention et le parcours restent soumis a approbation,
    # mais leur coherence est verifiee avant de creer la demande.
    erreur_academique = referentiel_academique.erreur_choix_academique(
        session,
        universite_id_nettoye,
        composante_id_nettoye,
        mention_id_nettoye,
        filiere_id_nettoye,
        niveau,
        set(NIVEAUX),
    )
    if erreur_academique:
        return _contexte(erreur_academique)

    # Universite reste modifiable ; le niveau suit la MEME regle de
    # cooldown de 14 jours que /securite/niveau. Cela empeche ce formulaire
    # de servir de contournement en changeant le niveau depuis un autre ecran.
    ancien_niveau = utilisateur.niveau
    if niveau != ancien_niveau and not referentiel_academique.peut_modifier_niveau_maintenant(utilisateur):
        return _contexte(
            "Vous avez recemment modifie votre niveau. Attendez la fin du delai de 14 jours avant de le changer a nouveau."
        )

    utilisateur.universite_id = universite_id_nettoye
    utilisateur.niveau = niveau
    if niveau != ancien_niveau:
        utilisateur.niveau_modifie_le = datetime.utcnow()
    session.add(utilisateur)
    session.commit()

    # Mention ET filiere deja identiques aux actuelles : rien a demander
    # (evite une demande inutile si l'etudiant re-confirme juste ses
    # choix existants en ajustant seulement son universite/niveau).
    if mention_id_nettoye == utilisateur.mention_id and filiere_id_nettoye == utilisateur.filiere_id:
        utilisateur.faculte_id = composante_id_nettoye
        session.add(utilisateur)
        session.commit()
        return RedirectResponse("/dashboard?ok=profil_academique_actualise", status_code=303)

    demande_existante = session.exec(
        select(DemandeChangementFiliere).where(
            DemandeChangementFiliere.utilisateur_id == utilisateur.id,
            DemandeChangementFiliere.statut == StatutDemandeChangementFiliere.EN_ATTENTE,
        )
    ).first()
    if demande_existante:
        if (
            demande_existante.nouvelle_mention_id == mention_id_nettoye
            and demande_existante.nouvelle_filiere_id == filiere_id_nettoye
            and demande_existante.nouvelle_faculte_id == composante_id_nettoye
        ):
            # Demande identique deja en attente : rien a refaire.
            return RedirectResponse("/dashboard?ok=profil_academique_actualise", status_code=303)
        return _contexte(
            "Vous avez deja une demande de changement de mention/parcours en attente de validation. "
            "Un admin doit la traiter avant d'en soumettre une nouvelle."
        )

    if not motif_filiere or not motif_filiere.strip():
        return _contexte("Merci d'expliquer brievement pourquoi vous demandez ce changement (obligatoire).")

    session.add(DemandeChangementFiliere(
        utilisateur_id=utilisateur.id,
        ancienne_filiere_id=utilisateur.filiere_id,
        nouvelle_filiere_id=filiere_id_nettoye,
        nouvelle_mention_id=mention_id_nettoye,
        nouvelle_faculte_id=composante_id_nettoye,
        motif=motif_filiere.strip(),
        statut=StatutDemandeChangementFiliere.EN_ATTENTE,
    ))
    session.commit()

    return RedirectResponse("/dashboard?ok=demande_filiere_envoyee", status_code=303)


# ============================================================
# Gestion de la double authentification (2FA / TOTP)
# ============================================================

DUREE_VALIDITE_CODE_EMAIL_2FA = timedelta(minutes=10)


def _masquer_email(email: Optional[str]) -> str:
    """Masque l'adresse de destination dans l'ecran de connexion."""
    if not email or "@" not in email:
        return ""
    local, domaine = email.rsplit("@", 1)
    local_masque = (local[:1] + "***") if local else "***"
    morceaux = domaine.split(".", 1)
    domaine_masque = (morceaux[0][:1] + "***") if morceaux[0] else "***"
    suffixe = "." + morceaux[1] if len(morceaux) == 2 else ""
    return f"{local_masque}@{domaine_masque}{suffixe}"


def _emettre_code_email_2fa(
    session: Session, utilisateur: Utilisateur, purpose: str
) -> None:
    """Crée un OTP haché avant envoi, et invalide les anciens OTP du même flux."""
    if purpose not in ("activation", "connexion"):
        raise ValueError("Finalite de code email MFA invalide.")
    if not utilisateur.email:
        raise EmailNonConfigure("Aucune adresse email n'est configuree pour ce compte.")
    if not email_configure():
        raise EmailNonConfigure("Le service SMTP n'est pas configure.")

    codes_precedents = session.exec(
        select(CodeEmail2FA).where(
            CodeEmail2FA.utilisateur_id == utilisateur.id,
            CodeEmail2FA.purpose == purpose,
            CodeEmail2FA.utilise == False,  # noqa: E712
        )
    ).all()
    maintenant = datetime.utcnow()
    for entree in codes_precedents:
        entree.utilise = True
        entree.date_utilisation = maintenant
        session.add(entree)

    code = f"{secrets.randbelow(1_000_000):06d}"
    entree = CodeEmail2FA(
        utilisateur_id=utilisateur.id,
        purpose=purpose,
        code_hash=hacher_mot_de_passe(code),
        expire_le=maintenant + DUREE_VALIDITE_CODE_EMAIL_2FA,
    )
    session.add(entree)
    session.commit()

    if purpose == "activation":
        sujet = "Gasy Mahay — confirmation de la double authentification"
        corps = (
            f"Votre code de confirmation Gasy Mahay est : {code}\n\n"
            "Ce code expire dans 10 minutes. Saisissez-le sur le site pour activer "
            "la double authentification par email. Si vous n'etes pas a l'origine "
            "de cette demande, ignorez ce message."
        )
    else:
        sujet = "Gasy Mahay — code de connexion"
        corps = (
            f"Votre code de connexion Gasy Mahay est : {code}\n\n"
            "Ce code expire dans 10 minutes et ne peut servir qu'une seule fois. "
            "Ne le communiquez jamais. Si vous n'etes pas a l'origine de cette "
            "tentative, changez votre mot de passe."
        )

    try:
        envoyer_email(utilisateur.email, sujet, corps)
    except Exception:
        # Un code dont l'envoi a échoué ne doit jamais rester valide.
        entree.utilise = True
        entree.date_utilisation = datetime.utcnow()
        session.add(entree)
        session.commit()
        raise


def _verifier_code_email_2fa(
    session: Session, utilisateur_id: int, code: str, purpose: str
) -> bool:
    """Vérifie l'expiration, la finalité, l'usage unique et consomme l'OTP."""
    if len(code) != 6 or not code.isdigit():
        return False
    maintenant = datetime.utcnow()
    candidats = session.exec(
        select(CodeEmail2FA).where(
            CodeEmail2FA.utilisateur_id == utilisateur_id,
            CodeEmail2FA.purpose == purpose,
            CodeEmail2FA.utilise == False,  # noqa: E712
            CodeEmail2FA.expire_le > maintenant,
        )
    ).all()
    for entree in candidats:
        # Les vérifications Python protègent aussi contre un mock/driver
        # qui renverrait une ligne hors des critères de la requête.
        if (
            entree.utilise
            or entree.purpose != purpose
            or entree.expire_le <= maintenant
        ):
            continue
        if verifier_mot_de_passe(code, entree.code_hash):
            entree.utilise = True
            entree.date_utilisation = maintenant
            session.add(entree)
            # Un seul code actif par flux : invalider aussi tous les autres.
            for autre in candidats:
                if autre.id != entree.id and not autre.utilise:
                    autre.utilise = True
                    autre.date_utilisation = maintenant
                    session.add(autre)
            session.commit()
            return True
    return False


def _demander_code_email_connexion(
    request: Request, session: Session, utilisateur: Utilisateur
) -> str:
    """Demande un OTP de connexion avec limites anti-spam et réponse non sensible."""
    trop_ip = limite_depassee(
        f"2fa-email-envoi:ip:{_ip_client(request)}",
        max_tentatives=8,
        fenetre_secondes=600,
    )
    trop_utilisateur = limite_depassee(
        f"2fa-email-envoi:user:{utilisateur.id}",
        max_tentatives=3,
        fenetre_secondes=600,
    )
    if trop_ip or trop_utilisateur:
        return "limite"
    try:
        _emettre_code_email_2fa(session, utilisateur, "connexion")
    except EmailNonConfigure:
        return "non_configure"
    except Exception as exc:
        # Ne jamais journaliser l'OTP ni les informations SMTP.
        print(f"[2fa-email] echec d'envoi ({type(exc).__name__}).")
        return "echec"
    return "envoye"



def _contexte_securite(
    utilisateur: Utilisateur, session: Session,
    erreur_photo: Optional[str] = None, erreur_bio: Optional[str] = None,
    erreur_email: Optional[str] = None, erreur_mot_de_passe: Optional[str] = None,
    erreur_2fa: Optional[str] = None,
) -> dict:
    """Factorise le contexte de securite.html, construit a plusieurs
    endroits : le GET normal ci-dessous, et chaque POST /profil/... ou
    /securite/mot-de-passe quand la valeur soumise est rejetee (meme
    principe que _contexte() dans actualiser_profil_academique() plus
    haut -- on re-rend directement le formulaire avec l'erreur plutot
    que de passer par une redirection, pour eviter d'avoir a encoder un
    message d'erreur libre dans l'URL)."""
    nb_codes_restants = 0
    if utilisateur.totp_active or utilisateur.email_otp_active:
        nb_codes_restants = len(session.exec(
            select(CodeSecours2FA).where(
                CodeSecours2FA.utilisateur_id == utilisateur.id,
                CodeSecours2FA.utilise == False,  # noqa: E712
            )
        ).all())

    profil_academique = referentiel_academique.contexte_profil_academique(utilisateur, session)

    return {
        "utilisateur": utilisateur,
        "jours_inactivite": jours_inactivite(utilisateur),
        "nb_codes_restants": nb_codes_restants,
        "profil_academique": profil_academique,
        "universites": session.exec(select(Universite).where(Universite.est_active == True)).all(),  # noqa: E712
        "niveaux": NIVEAUX,
        "peut_modifier_niveau": referentiel_academique.peut_modifier_niveau_maintenant(utilisateur),
        "jours_avant_changement_niveau": referentiel_academique.jours_avant_prochain_changement_niveau(utilisateur),
        "erreur_photo": erreur_photo,
        "erreur_bio": erreur_bio,
        "erreur_email": erreur_email,
        "erreur_mot_de_passe": erreur_mot_de_passe,
        "erreur_2fa": erreur_2fa,
        "email_smtp_configure": email_configure(),
    }


@router.get("/securite")
def page_securite(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    return templates.TemplateResponse(request, "securite.html", _contexte_securite(utilisateur, session))


# ============================================================
# Photo de profil (upload reel OU avatar auto-genere) -- voir
# app/storage.py (sauvegarder_avatar) et couleur_avatar() dans
# app/templating.py pour le repli initiale+couleur quand aucune photo
# n'est definie. Affichee depuis securite.html (carte "Photo de
# profil"), la sidebar (base.html) et partout ou un Utilisateur est
# liste (administration, membres d'un cercle) via le macro
# components/avatar.html.
# ============================================================

@router.post("/profil/photo")
def uploader_photo_profil(
    request: Request,
    photo: UploadFile = File(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    try:
        # ancien_chemin=utilisateur.photo_chemin AVANT d'ecraser le
        # champ ci-dessous : sauvegarder_avatar() s'en sert pour
        # supprimer l'ancienne photo une fois la nouvelle validee (voir
        # sa docstring dans storage.py).
        utilisateur.photo_chemin = sauvegarder_avatar(photo, utilisateur.id, ancien_chemin=utilisateur.photo_chemin)
    except FichierInvalide as exc:
        return templates.TemplateResponse(
            request, "securite.html", _contexte_securite(utilisateur, session, erreur_photo=str(exc))
        )

    session.add(utilisateur)
    session.commit()
    return RedirectResponse("/securite?ok=photo_mise_a_jour", status_code=303)


@router.post("/profil/photo/supprimer")
def supprimer_photo_profil(
    request: Request,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    if utilisateur.photo_chemin:
        supprimer_fichier(utilisateur.photo_chemin)
        utilisateur.photo_chemin = None
        session.add(utilisateur)
        session.commit()

    return RedirectResponse("/securite?ok=photo_supprimee", status_code=303)


@router.get("/profil/photo/{utilisateur_id}")
def afficher_photo_profil(utilisateur_id: int, session: Session = Depends(get_session)):
    """Sert la photo de profil d'un utilisateur. Volontairement PUBLIC
    (pas de verification de session) : un avatar affiche dans un cercle
    d'etude ou l'administration doit etre visible par les autres
    membres/admins, exactement comme un document approuve est
    telechargeable par n'importe qui -- aucune donnee sensible n'est
    exposee (juste l'image elle-meme). Meme pattern que
    documents_router.telecharger_document() : redirection vers l'URL
    publique Supabase si le stockage distant est actif, sinon lecture
    directe du disque local."""
    utilisateur = session.get(Utilisateur, utilisateur_id)
    if not utilisateur or not utilisateur.photo_chemin:
        raise HTTPException(status_code=404)

    if stockage_distant_actif():
        return RedirectResponse(obtenir_url_telechargement(utilisateur.photo_chemin, expires_in=300, telechargement=False))
    return FileResponse(utilisateur.photo_chemin)


# Longueur max de la bio ("A propos", voir Utilisateur.bio) : une courte
# presentation, pas un texte long -- alignee sur la limite deja posee
# cote formulaire (voir maxlength dans securite.html) pour que le
# message d'erreur reste coherent avec ce que le champ autorise deja a
# la frappe.
LONGUEUR_MAX_BIO = 280


@router.post("/profil/bio")
def modifier_bio(
    request: Request,
    bio: str = Form(""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Met a jour le texte "A propos" affiche dans le panneau profil du
    chat de cercle (voir GET /cercles/{id}/membres/{id}/profil dans
    cercles_router.py). Champ facultatif : une valeur vide efface la
    bio (redevient None), pas de chaine vide stockee en base."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    bio_nettoyee = bio.strip()
    if len(bio_nettoyee) > LONGUEUR_MAX_BIO:
        return templates.TemplateResponse(
            request, "securite.html",
            _contexte_securite(utilisateur, session, erreur_bio=f"Texte trop long (max {LONGUEUR_MAX_BIO} caracteres)."),
        )

    utilisateur.bio = bio_nettoyee or None
    session.add(utilisateur)
    session.commit()
    return RedirectResponse("/securite?ok=bio_mise_a_jour", status_code=303)


@router.post("/profil/email")
def modifier_email(
    request: Request,
    email: str = Form(""),
    mot_de_passe: str = Form(""),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Met a jour l'email de recuperation (voir carte "Email de
    recuperation" sur securite.html). Champ facultatif : une valeur
    vide efface l'email (redevient None) -- dans ce cas, "mot de passe
    oublie" (voir plus bas) ne pourra plus etre utilise en self-service
    pour ce compte, seule la reinitialisation par un admin restera
    possible. Validation minimale (presence d'un "@" et d'un "." apres)
    : ce n'est qu'un canal de secours, pas l'identifiant de connexion
    (qui reste le telephone), pas besoin d'une verification par lien de
    confirmation pour ce niveau d'enjeu."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    email_nettoye = email.strip()
    if email_nettoye and ("@" not in email_nettoye or "." not in email_nettoye.split("@")[-1]):
        return templates.TemplateResponse(
            request, "securite.html",
            _contexte_securite(utilisateur, session, erreur_email="Adresse email invalide."),
        )

    email_precedent = utilisateur.email or ""
    email_modifie = email_nettoye.casefold() != email_precedent.casefold()
    mfa_email_desactive = False
    if email_modifie and utilisateur.email_otp_active:
        # Sans cette vérification, un navigateur laissé ouvert pourrait
        # retirer le facteur MFA simplement en remplaçant l'adresse email.
        if not mot_de_passe or not verifier_mot_de_passe(mot_de_passe, utilisateur.mot_de_passe_hash):
            return templates.TemplateResponse(
                request, "securite.html",
                _contexte_securite(
                    utilisateur, session,
                    erreur_email="Mot de passe actuel requis et doit être correct pour modifier l'adresse utilisée par la MFA.",
                ),
            )
    if email_modifie:
        # Un changement d'adresse invalide le facteur email : la nouvelle
        # adresse devra prouver sa possession avant de pouvoir être activée.
        if utilisateur.email_otp_active:
            utilisateur.email_otp_active = False
            mfa_email_desactive = True
        codes_email = session.exec(
            select(CodeEmail2FA).where(
                CodeEmail2FA.utilisateur_id == utilisateur.id,
                CodeEmail2FA.utilise == False,  # noqa: E712
            )
        ).all()
        maintenant = datetime.utcnow()
        for entree in codes_email:
            entree.utilise = True
            entree.date_utilisation = maintenant
            session.add(entree)
        request.session.pop("email_2fa_activation_user_id", None)

    utilisateur.email = email_nettoye or None
    session.add(utilisateur)
    session.commit()
    if mfa_email_desactive:
        request.session["auth_fingerprint"] = empreinte_session_utilisateur(utilisateur)
    return RedirectResponse("/securite?ok=email_mis_a_jour", status_code=303)


# Longueur min du mot de passe : alignee sur la regle deja appliquee a
# l'inscription (voir inscription() plus haut) -- un nouveau mot de
# passe ne doit pas pouvoir etre plus faible que ce qu'on exige a la
# creation du compte.
LONGUEUR_MIN_MOT_DE_PASSE = 8


@router.post("/securite/mot-de-passe")
def modifier_mot_de_passe(
    request: Request,
    ancien_mot_de_passe: str = Form(...),
    nouveau_mot_de_passe: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Change son propre mot de passe en etant deja connecte -- exige
    l'ANCIEN mot de passe (que ce soit le mot de passe habituel, ou le
    mot de passe temporaire genere par un admin / recu par email, voir
    plus bas) pour eviter qu'une session laissee ouverte sur un
    appareil partage suffise a elle seule a prendre le controle du
    compte. Efface doit_changer_mot_de_passe : c'est le point de sortie
    du rappel affiche apres une reinitialisation (admin ou email)."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    if not verifier_mot_de_passe(ancien_mot_de_passe, utilisateur.mot_de_passe_hash):
        return templates.TemplateResponse(
            request, "securite.html",
            _contexte_securite(utilisateur, session, erreur_mot_de_passe="Ancien mot de passe incorrect."),
        )
    if len(nouveau_mot_de_passe) < LONGUEUR_MIN_MOT_DE_PASSE:
        return templates.TemplateResponse(
            request, "securite.html",
            _contexte_securite(
                utilisateur, session,
                erreur_mot_de_passe=f"Le nouveau mot de passe doit faire au moins {LONGUEUR_MIN_MOT_DE_PASSE} caracteres.",
            ),
        )

    utilisateur.mot_de_passe_hash = hacher_mot_de_passe(nouveau_mot_de_passe)
    utilisateur.doit_changer_mot_de_passe = False
    session.add(utilisateur)
    session.commit()
    request.session["auth_fingerprint"] = empreinte_session_utilisateur(utilisateur)
    return RedirectResponse("/securite?ok=mot_de_passe_modifie", status_code=303)


@router.post("/securite/universite")
def modifier_universite(
    request: Request,
    universite_id: int = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Definit l'universite d'un profil qui n'en a pas encore (comptes
    crees avant l'ajout de ce champ, voir migration f2b8e6a1c9d3, ou
    inscrits sans que l'inscription ne le demandait encore). Une fois
    definie, ce formulaire disparait du profil (voir securite.html) —
    changer d'universite ensuite n'est pas encore prevu, contacter un
    admin le cas echeant."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)

    if utilisateur.universite_id is not None:
        return RedirectResponse("/profil/academique", status_code=303)

    universite = session.get(Universite, universite_id)
    if not universite or not universite.est_active:
        return RedirectResponse("/securite?erreur=universite_invalide", status_code=303)

    utilisateur.universite_id = universite.id
    session.add(utilisateur)
    session.commit()

    return RedirectResponse("/securite?ok=universite_modifiee", status_code=303)


@router.post("/securite/niveau")
def modifier_niveau(
    request: Request,
    niveau: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """§14 et §16 du brief "cercles nationaux" : le niveau est
    modifiable librement par l'etudiant (contrairement a filiere_id,
    jamais expose en modification directe dans ce formulaire — voir
    §11), mais au maximum une fois tous les 14 jours, verifie ici cote
    backend (jamais uniquement cote frontend)."""
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    if utilisateur.role not in (RoleUtilisateur.ETUDIANT, RoleUtilisateur.PROFESSEUR):
        return RedirectResponse("/securite", status_code=303)

    if niveau not in NIVEAUX:
        return RedirectResponse("/securite?erreur=niveau_invalide", status_code=303)

    if niveau == utilisateur.niveau:
        return RedirectResponse("/securite?ok=niveau_deja_a_jour", status_code=303)

    if not referentiel_academique.peut_modifier_niveau_maintenant(utilisateur):
        return RedirectResponse("/securite?erreur=niveau_cooldown", status_code=303)

    utilisateur.niveau = niveau
    utilisateur.niveau_modifie_le = datetime.utcnow()
    session.add(utilisateur)
    session.commit()

    return RedirectResponse("/securite?ok=niveau_modifie", status_code=303)


@router.post("/securite/2fa/demarrer")
def demarrer_activation_2fa(request: Request, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
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
    utilisateur = utilisateur_courant(request, session)
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
    utilisateur = utilisateur_courant(request, session)
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

    # Les codes de secours sont communs aux méthodes MFA actives.
    # Remplacer l'ancien lot évite d'accumuler des codes oubliés.
    anciens_codes = session.exec(
        select(CodeSecours2FA).where(CodeSecours2FA.utilisateur_id == utilisateur.id)
    ).all()
    for ancien_code in anciens_codes:
        session.delete(ancien_code)
    codes_clairs = generer_codes_secours()
    for code_secours in codes_clairs:
        session.add(CodeSecours2FA(utilisateur_id=utilisateur.id, code_hash=hacher_code_secours(code_secours)))
    session.commit()

    request.session.pop("totp_secret_en_attente", None)
    request.session["auth_fingerprint"] = empreinte_session_utilisateur(utilisateur)
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
    utilisateur = utilisateur_courant(request, session)
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

    # Garder les codes de secours si l'OTP email reste actif.
    if not utilisateur.email_otp_active:
        anciens_codes = session.exec(
            select(CodeSecours2FA).where(CodeSecours2FA.utilisateur_id == utilisateur.id)
        ).all()
        for entree in anciens_codes:
            session.delete(entree)
    session.commit()
    request.session["auth_fingerprint"] = empreinte_session_utilisateur(utilisateur)

    return RedirectResponse("/securite?desactive=1", status_code=303)


@router.post("/securite/2fa/regenerer-codes-secours")
def regenerer_codes_secours(request: Request, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur or not (utilisateur.totp_active or utilisateur.email_otp_active):
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


@router.post("/securite/2fa/email/demarrer")
def demarrer_activation_2fa_email(
    request: Request,
    mot_de_passe: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    if utilisateur.email_otp_active:
        return RedirectResponse("/securite", status_code=303)

    trop_ip = limite_depassee(
        f"2fa-email-activation:ip:{_ip_client(request)}",
        max_tentatives=8,
        fenetre_secondes=3600,
    )
    trop_utilisateur = limite_depassee(
        f"2fa-email-activation:user:{utilisateur.id}",
        max_tentatives=3,
        fenetre_secondes=3600,
    )
    if trop_ip or trop_utilisateur:
        return templates.TemplateResponse(
            request, "securite.html",
            _contexte_securite(utilisateur, session, erreur_2fa="Trop de demandes d'activation. Reessayez plus tard."),
        )
    if not verifier_mot_de_passe(mot_de_passe, utilisateur.mot_de_passe_hash):
        return templates.TemplateResponse(
            request, "securite.html",
            _contexte_securite(utilisateur, session, erreur_2fa="Mot de passe incorrect."),
        )
    if not utilisateur.email:
        return templates.TemplateResponse(
            request, "securite.html",
            _contexte_securite(utilisateur, session, erreur_2fa="Ajoutez d'abord une adresse email dans votre profil."),
        )
    if not email_configure():
        return templates.TemplateResponse(
            request, "securite.html",
            _contexte_securite(utilisateur, session, erreur_2fa="L'envoi email n'est pas configure sur le serveur. Aucun SMS ne sera utilise."),
        )

    try:
        _emettre_code_email_2fa(session, utilisateur, "activation")
    except Exception as exc:
        print(f"[2fa-email] echec du code d'activation ({type(exc).__name__}).")
        return templates.TemplateResponse(
            request, "securite.html",
            _contexte_securite(utilisateur, session, erreur_2fa="Impossible d'envoyer le code. Verifiez la configuration email ou reessayez plus tard."),
        )

    request.session["email_2fa_activation_user_id"] = utilisateur.id
    return RedirectResponse("/securite/2fa/email/confirmer", status_code=303)


@router.get("/securite/2fa/email/confirmer")
def page_confirmer_2fa_email(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    if (
        request.session.get("email_2fa_activation_user_id") != utilisateur.id
        or utilisateur.email_otp_active
    ):
        return RedirectResponse("/securite", status_code=303)
    return templates.TemplateResponse(
        request,
        "configurer_2fa.html",
        {"email_mode": True, "email_masque": _masquer_email(utilisateur.email), "erreur": None},
    )


@router.post("/securite/2fa/email/confirmer")
def confirmer_activation_2fa_email(
    request: Request,
    code: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    if (
        request.session.get("email_2fa_activation_user_id") != utilisateur.id
        or utilisateur.email_otp_active
        or not utilisateur.email
    ):
        return RedirectResponse("/securite", status_code=303)

    trop_ip = limite_depassee(
        f"2fa-email-confirmation:ip:{_ip_client(request)}",
        max_tentatives=10,
        fenetre_secondes=600,
    )
    trop_utilisateur = limite_depassee(
        f"2fa-email-confirmation:user:{utilisateur.id}",
        max_tentatives=6,
        fenetre_secondes=600,
    )
    if trop_ip or trop_utilisateur:
        return templates.TemplateResponse(
            request, "confirmer_2fa_email.html",
            {"email_masque": _masquer_email(utilisateur.email), "erreur": "Trop de tentatives. Reessayez dans quelques minutes."},
        )

    if not _verifier_code_email_2fa(session, utilisateur.id, code.strip(), "activation"):
        return templates.TemplateResponse(
            request, "configurer_2fa.html",
            {"email_mode": True, "email_masque": _masquer_email(utilisateur.email), "erreur": "Code invalide ou expire."},
        )

    utilisateur.email_otp_active = True
    session.add(utilisateur)
    codes_clairs = []
    if not utilisateur.totp_active:
        anciens_codes = session.exec(
            select(CodeSecours2FA).where(CodeSecours2FA.utilisateur_id == utilisateur.id)
        ).all()
        for ancien_code in anciens_codes:
            session.delete(ancien_code)
        codes_clairs = generer_codes_secours()
        for code_secours in codes_clairs:
            session.add(
                CodeSecours2FA(
                    utilisateur_id=utilisateur.id,
                    code_hash=hacher_code_secours(code_secours),
                )
            )
    session.commit()
    request.session.pop("email_2fa_activation_user_id", None)
    request.session["auth_fingerprint"] = empreinte_session_utilisateur(utilisateur)

    if codes_clairs:
        return templates.TemplateResponse(
            request, "codes_secours_2fa.html",
            {"utilisateur": utilisateur, "codes": codes_clairs},
        )
    return RedirectResponse("/securite?email_2fa_active=1", status_code=303)


@router.post("/securite/2fa/email/desactiver")
def desactiver_2fa_email(
    request: Request,
    mot_de_passe: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    if not utilisateur:
        return RedirectResponse("/connexion", status_code=303)
    if not verifier_mot_de_passe(mot_de_passe, utilisateur.mot_de_passe_hash):
        return templates.TemplateResponse(
            request, "securite.html",
            _contexte_securite(utilisateur, session, erreur_2fa="Mot de passe incorrect."),
        )

    utilisateur.email_otp_active = False
    request.session.pop("email_2fa_activation_user_id", None)
    codes_email = session.exec(
        select(CodeEmail2FA).where(
            CodeEmail2FA.utilisateur_id == utilisateur.id,
            CodeEmail2FA.utilise == False,  # noqa: E712
        )
    ).all()
    maintenant = datetime.utcnow()
    for entree in codes_email:
        entree.utilise = True
        entree.date_utilisation = maintenant
        session.add(entree)

    if not utilisateur.totp_active:
        codes_secours = session.exec(
            select(CodeSecours2FA).where(CodeSecours2FA.utilisateur_id == utilisateur.id)
        ).all()
        for entree in codes_secours:
            session.delete(entree)
    session.add(utilisateur)
    session.commit()
    request.session["auth_fingerprint"] = empreinte_session_utilisateur(utilisateur)
    return RedirectResponse("/securite?email_2fa_desactive=1", status_code=303)



@router.post("/notifications/inactivite/lue")
def marquer_notification_inactivite_lue(
    request: Request,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    notification_data = request.session.pop("notification_inactivite", None)
    if notification_data:
        notification_id = notification_data.get("notification_id")
        notification = session.get(Notification, notification_id) if notification_id else None
        if notification and notification.destinataire_id == request.session.get("user_id") and notification.type_notification == TypeNotification.INACTIVITE_3_JOURS:
            notification.lu = True
            session.add(notification)
            session.commit()
    return RedirectResponse("/", status_code=303)
