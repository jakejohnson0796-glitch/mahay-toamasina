import logging
from datetime import datetime
import random
from typing import List, Optional

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlmodel import Session, or_, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..auth import utilisateur_courant
from ..dependencies import acces_ia_ou_redirection
from ..models import (
    Document, MembreCercle, MissionApprentissage, StatutDocument, TentativeQuiz, ProgressionNotion,
    NiveauScolaire, OptionScolaire, ReferentielScolaire, MatiereScolaire,
    ProgrammeMatiereScolaire,
)
from .. import quiz as quiz_module
from .. import adaptive_learning
from .. import ai_queue
from .. import theme_service
from .. import gamification
from .. import quiz_calibration
from ..rate_limit import limite_depassee

router = APIRouter()
logger = logging.getLogger(__name__)


def _matieres_disponibles(session: Session) -> List[str]:
    valeurs = session.exec(
        select(Document.matiere).where(Document.statut == StatutDocument.APPROUVE).distinct()
    ).all()
    return sorted(valeurs)


def _enseignant_sans_classe_scolaire(utilisateur) -> bool:
    return (
        getattr(utilisateur, "profil_souhaite", None) == "professeur"
        and getattr(utilisateur, "cycle_education", None) in {"college", "lycee"}
        and not getattr(utilisateur, "niveau_scolaire_id", None)
    )


def _contexte_scolaire_quiz(utilisateur, session: Session) -> Optional[dict]:
    """Retourne une classe scolaire validée ou refuse le profil scolaire incomplet."""
    if getattr(utilisateur, "cycle_education", None) not in {"college", "lycee"}:
        return None
    niveau_id = getattr(utilisateur, "niveau_scolaire_id", None)
    if not niveau_id:
        return None if _enseignant_sans_classe_scolaire(utilisateur) else {}
    referentiels = session.exec(
        select(ReferentielScolaire).order_by(
            ReferentielScolaire.date_creation.desc(),
            ReferentielScolaire.id.desc(),
        )
    ).all()
    referentiel = referentiels[0] if referentiels else None
    niveau = session.get(NiveauScolaire, niveau_id)
    if (
        not referentiel
        or not niveau
        or niveau.referentiel_id != referentiel.id
        or not niveau.est_actif
        or niveau.statut_validation != "verifie"
        or niveau.cycle != utilisateur.cycle_education
        or niveau.libelle.casefold() not in quiz_module.NIVEAUX_SCOLAIRES_NORMALISES
    ):
        return {}

    option_id = getattr(utilisateur, "option_scolaire_id", None)
    option = session.get(OptionScolaire, option_id) if option_id else None
    if option_id and (
        not option
        or option.referentiel_id != referentiel.id
        or option.niveau_id != niveau.id
        or not option.est_active
        or option.statut_validation != "verifie"
    ):
        return {}
    if option and option.parent_option_id:
        parent = session.get(OptionScolaire, option.parent_option_id)
        if (
            not parent
            or parent.referentiel_id != referentiel.id
            or parent.niveau_id != niveau.id
            or parent.parent_option_id is not None
            or not parent.est_active
            or parent.statut_validation != "verifie"
        ):
            return {}

    return {
        "niveau": niveau.libelle,
        "cycle_education": niveau.cycle,
        "referentiel_id": referentiel.id,
        "niveau_scolaire_id": niveau.id,
        "option_scolaire_id": option.id if option else None,
        "etablissement_scolaire_id": getattr(utilisateur, "etablissement_scolaire_id", None),
    }


def _matieres_scolaires_disponibles(session: Session, contexte: dict) -> List[str]:
    """Matières validées du programme scolaire et des cours approuvés de la classe."""
    option_ids = set()
    option_id = contexte.get("option_scolaire_id")
    if option_id:
        option_ids.add(option_id)
        option = session.get(OptionScolaire, option_id)
        if option and option.parent_option_id:
            option_ids.add(option.parent_option_id)

    requete = (
        select(MatiereScolaire.libelle)
        .join(
            ProgrammeMatiereScolaire,
            ProgrammeMatiereScolaire.matiere_id == MatiereScolaire.id,
        )
        .where(
            ProgrammeMatiereScolaire.referentiel_id == contexte["referentiel_id"],
            ProgrammeMatiereScolaire.niveau_id == contexte["niveau_scolaire_id"],
            ProgrammeMatiereScolaire.statut_validation == "verifie",
            MatiereScolaire.est_active == True,  # noqa: E712
            MatiereScolaire.statut_validation == "verifie",
        )
    )
    if option_ids:
        requete = requete.where(
            or_(
                ProgrammeMatiereScolaire.option_id.is_(None),
                ProgrammeMatiereScolaire.option_id.in_(option_ids),
            )
        )
    else:
        requete = requete.where(ProgrammeMatiereScolaire.option_id.is_(None))
    valeurs = set(session.exec(requete).all())

    # Les documents scolaires approuvés complètent le programme tant qu'un
    # rattachement matière/classe est encore en cours de vérification.
    docs = select(Document.matiere).where(
        Document.statut == StatutDocument.APPROUVE,
        Document.portee_academique == "scolaire",
        Document.niveau_scolaire_id == contexte["niveau_scolaire_id"],
    )
    if option_ids:
        docs = docs.where(
            or_(
                Document.option_scolaire_id.is_(None),
                Document.option_scolaire_id.in_(option_ids),
            )
        )
    else:
        docs = docs.where(Document.option_scolaire_id.is_(None))
    etablissement_id = contexte.get("etablissement_scolaire_id")
    if etablissement_id:
        docs = docs.where(
            or_(
                Document.etablissement_scolaire_id.is_(None),
                Document.etablissement_scolaire_id == etablissement_id,
            )
        )
    else:
        # Sans établissement sélectionné, ne pas mélanger les documents
        # réservés à une école précise dans la liste de matières du quiz.
        docs = docs.where(Document.etablissement_scolaire_id.is_(None))
    valeurs.update(
        matiere for matiere in session.exec(docs).all()
        if matiere and matiere.strip()
    )
    return sorted(valeurs, key=str.casefold)


def _niveau_quiz_par_defaut(utilisateur, contexte_scolaire=None, progressions=None, historique_niveau=None) -> str:
    """Déduit le niveau sans demander une nouvelle saisie à chaque quiz.

    Le profil scolaire vérifié est prioritaire. Pour l'université, le niveau
    du profil prime, puis les progressions récentes et le dernier quiz.
    """
    progressions = progressions or []
    if contexte_scolaire and contexte_scolaire.get("niveau"):
        return contexte_scolaire["niveau"]

    cycle = getattr(utilisateur, "cycle_education", None)
    if cycle in {"college", "lycee"}:
        niveaux_scolaires = quiz_module.NIVEAUX_SCOLAIRES_NORMALISES
        if historique_niveau and str(historique_niveau).casefold() in niveaux_scolaires:
            return historique_niveau
        for progression in progressions:
            niveau = getattr(progression, "niveau", None)
            if niveau and str(niveau).casefold() in niveaux_scolaires:
                return niveau
        # Les enseignants du secondaire peuvent s'entraîner sans classe
        # individuelle. Le cycle suffit pour éviter de leur attribuer L1.
        return "6e" if cycle == "college" else "Seconde"

    niveau_profil = getattr(utilisateur, "niveau", None)
    if niveau_profil in quiz_module.NIVEAUX:
        return niveau_profil
    for progression in progressions:
        niveau = getattr(progression, "niveau", None)
        if niveau in quiz_module.NIVEAUX:
            return niveau
    if historique_niveau in quiz_module.NIVEAUX:
        return historique_niveau
    # Compatibilité des anciens comptes sans niveau renseigné : un défaut
    # explicite évite de bloquer la première séance; aucune donnée de profil
    # n'est écrasée par ce choix de génération.
    return "L1"


def _suggestion_quiz(
    matieres: List[str],
    progressions: List[ProgressionNotion],
    niveau: Optional[str] = None,
) -> dict:
    """Choisit une priorité pédagogique au bon niveau du parcours."""
    par_casse = {str(matiere).casefold(): matiere for matiere in matieres if matiere}
    for progression in progressions:
        matiere = getattr(progression, "matiere", None)
        if not matiere:
            continue
        niveau_progression = getattr(progression, "niveau", None)
        if (
            niveau
            and niveau_progression
            and str(niveau_progression).casefold() != str(niveau).casefold()
        ):
            continue
        matiere_affichee = par_casse.get(matiere.casefold())
        if not matiere_affichee:
            continue
        notion = (getattr(progression, "notion", None) or "").strip()
        return {
            "matiere": matiere_affichee,
            "notion": notion,
            "difficulte": quiz_module.difficulte_revision_adaptative(progression),
            "progression": progression,
            "basee_sur_progression": True,
        }
    return {
        "matiere": matieres[0] if matieres else "",
        "notion": "",
        "difficulte": "Moyen",
        "progression": None,
        "basee_sur_progression": False,
    }


def _derniere_tentative_utilisateur(session: Session, utilisateur_id: int) -> Optional[TentativeQuiz]:
    """Lit la dernière tentative sans dépendre du statut de correction."""
    try:
        return session.exec(
            select(TentativeQuiz)
            .where(TentativeQuiz.utilisateur_id == utilisateur_id)
            .order_by(TentativeQuiz.id.desc())
            .limit(1)
        ).first()
    except Exception:
        logger.debug("Historique de niveau du quiz indisponible.", exc_info=True)
        return None


@router.get("/quiz")
def page_config_quiz(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    contexte_scolaire = _contexte_scolaire_quiz(utilisateur, session)
    est_profil_scolaire = (
        getattr(utilisateur, "cycle_education", None) in {"college", "lycee"}
        and not _enseignant_sans_classe_scolaire(utilisateur)
    )
    if est_profil_scolaire and not contexte_scolaire:
        return RedirectResponse(
            "/profil/academique?erreur=profil_scolaire_incomplet",
            status_code=303,
        )

    progressions = quiz_module.notions_a_revoir(session, utilisateur.id, limit=8)
    if contexte_scolaire:
        matieres = _matieres_scolaires_disponibles(session, contexte_scolaire)
        niveaux = [contexte_scolaire["niveau"]]
    else:
        matieres = _matieres_disponibles(session)
        # Les matières déjà travaillées restent proposées même si elles ne
        # proviennent pas d'un document approuvé récent (profil universitaire).
        matieres = sorted(
            set(matieres)
            | {
                progression.matiere
                for progression in progressions
                if getattr(progression, "matiere", None)
            },
            key=str.casefold,
        )
        niveaux = quiz_module.NIVEAUX

    derniere_tentative = _derniere_tentative_utilisateur(session, utilisateur.id)
    niveau_quiz = _niveau_quiz_par_defaut(
        utilisateur,
        contexte_scolaire,
        progressions,
        getattr(derniere_tentative, "niveau", None),
    )
    suggestion_quiz = _suggestion_quiz(matieres, progressions, niveau_quiz)
    return templates.TemplateResponse(
        request,
        "quiz_config.html",
        {
            "utilisateur": utilisateur,
            "matieres": matieres,
            "niveaux": niveaux,
            "niveau_quiz": niveau_quiz,
            "suggestion_quiz": suggestion_quiz,
            "difficultes": quiz_module.DIFFICULTES,
            "nb_questions_possibles": quiz_module.NB_QUESTIONS_POSSIBLES,
        },
    )


@router.post("/quiz/generer")
def generer_quiz(
    request: Request,
    matiere: Optional[str] = Form(None),
    matiere_libre: Optional[str] = Form(None),
    mode_quiz: Optional[str] = Form(None),
    niveau: Optional[str] = Form(None),
    difficulte: Optional[str] = Form("auto"),
    nb_questions: int = Form(10),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    host = request.client.host if request.client else "inconnu"
    if limite_depassee(f"ia-quiz:user:{utilisateur.id}", 3, 300) or limite_depassee(f"ia-quiz:ip:{host}", 12, 300):
        return RedirectResponse("/quiz?erreur=trop_de_generations", status_code=303)

    # Les formulaires ouverts avant la refonte continuent de fonctionner :
    # une matière explicite correspond à l'ancien mode personnalisé.
    if mode_quiz is None:
        mode_quiz = "matiere" if ((matiere_libre or "").strip() or (matiere or "").strip() or niveau) else "recommande"
    if mode_quiz not in {"recommande", "hasard", "matiere"}:
        return RedirectResponse("/quiz?erreur=mode_quiz_invalide", status_code=303)

    contexte_scolaire = _contexte_scolaire_quiz(utilisateur, session)
    if (
        getattr(utilisateur, "cycle_education", None) in {"college", "lycee"}
        and not _enseignant_sans_classe_scolaire(utilisateur)
        and not contexte_scolaire
    ):
        return RedirectResponse(
            "/profil/academique?erreur=profil_scolaire_incomplet",
            status_code=303,
        )

    progressions = quiz_module.notions_a_revoir(session, utilisateur.id, limit=8)
    if contexte_scolaire:
        matieres_disponibles = _matieres_scolaires_disponibles(session, contexte_scolaire)
    else:
        matieres_disponibles = _matieres_disponibles(session)
        matieres_disponibles = sorted(
            set(matieres_disponibles)
            | {
                progression.matiere
                for progression in progressions
                if getattr(progression, "matiere", None)
            },
            key=str.casefold,
        )

    derniere_tentative = _derniere_tentative_utilisateur(session, utilisateur.id)
    niveau = _niveau_quiz_par_defaut(
        utilisateur,
        contexte_scolaire,
        progressions,
        getattr(derniere_tentative, "niveau", None),
    )
    suggestion = _suggestion_quiz(matieres_disponibles, progressions, niveau)

    progression_cible = None
    sujet_cible = None
    if mode_quiz == "recommande":
        matiere_choisie = suggestion["matiere"]
        progression_cible = suggestion["progression"]
        sujet_cible = suggestion["notion"] or None
        difficulte_choisie = suggestion["difficulte"]
    elif mode_quiz == "hasard":
        if not matieres_disponibles:
            erreur = "aucune_matiere_scolaire" if contexte_scolaire else "matiere_requise"
            return RedirectResponse(f"/quiz?erreur={erreur}", status_code=303)
        matiere_choisie = random.choice(matieres_disponibles)
        difficulte_choisie = random.choice(quiz_module.DIFFICULTES)
    else:
        matiere_choisie = (matiere_libre or "").strip() or (matiere or "").strip()
        if not matiere_choisie:
            return RedirectResponse("/quiz?erreur=matiere_requise", status_code=303)
        matiere_selectionnee = (matiere or "").strip()
        sujet_libre = (matiere_libre or "").strip()
        if matiere_selectionnee and sujet_libre:
            # La matière reste dans le périmètre du parcours (notamment au
            # collège/lycée) et le texte libre précise le module à travailler.
            matiere_choisie = matiere_selectionnee
            sujet_cible = sujet_libre
        else:
            matiere_choisie = sujet_libre or matiere_selectionnee
        if not matiere_choisie:
            return RedirectResponse("/quiz?erreur=matiere_requise", status_code=303)
        progression_cible = next(
            (
                progression for progression in progressions
                if (getattr(progression, "matiere", None) or "").casefold() == matiere_choisie.casefold()
            ),
            None,
        )
        if (difficulte or "auto").strip() == "auto":
            difficulte_choisie = quiz_module.difficulte_revision_adaptative(progression_cible)
        else:
            difficulte_choisie = (difficulte or "").strip()

    if not matiere_choisie:
        erreur = "aucune_matiere_scolaire" if contexte_scolaire else "matiere_requise"
        return RedirectResponse(f"/quiz?erreur={erreur}", status_code=303)

    if contexte_scolaire:
        # Le serveur impose le niveau réellement sélectionné dans le profil;
        # le navigateur ne peut pas provoquer un quiz d'une autre classe.
        niveau = contexte_scolaire["niveau"]
        correspondance_matiere = next(
            (
                item for item in matieres_disponibles
                if item.casefold() == matiere_choisie.casefold()
            ),
            None,
        )
        if not correspondance_matiere:
            return RedirectResponse(
                "/quiz?erreur=matiere_scolaire_indisponible",
                status_code=303,
            )
        matiere_choisie = correspondance_matiere

    nb_questions = nb_questions if nb_questions in quiz_module.NB_QUESTIONS_POSSIBLES else 10
    try:
        matiere_choisie = quiz_module.valider_parametres(
            matiere_choisie,
            niveau,
            difficulte_choisie,
            nb_questions,
        )
    except quiz_module.QuizValidationError:
        return RedirectResponse("/quiz?erreur=parametres_invalides", status_code=303)

    try:
        tentative = quiz_module.creer_tentative(
            session,
            utilisateur,
            matiere_choisie,
            niveau,
            difficulte_choisie,
            nb_questions,
            cycle_education=contexte_scolaire["cycle_education"] if contexte_scolaire else None,
            niveau_scolaire_id=contexte_scolaire["niveau_scolaire_id"] if contexte_scolaire else None,
            option_scolaire_id=contexte_scolaire["option_scolaire_id"] if contexte_scolaire else None,
            sujet_cible=sujet_cible,
        )
    except quiz_module.QuizValidationError as erreur:
        logger.warning(
            "Generation quiz invalide: user=%s matiere=%s niveau=%s difficulte=%s "
            "nb_questions=%s mode=%s erreur=%s",
            utilisateur.id,
            matiere_choisie,
            niveau,
            difficulte_choisie,
            nb_questions,
            mode_quiz,
            erreur,
        )
        return RedirectResponse("/quiz?erreur=generation_invalide", status_code=303)

    # La verification multi-modeles est durablement mise en file.
    # Sur Render Free, le worker tourne dans le Web et consomme Redis.
    tache_ia_id = ai_queue.planifier_verification_quiz(tentative.id)
    print(
        f"[AI QUEUE] Route /quiz/generer quiz={tentative.id} tache_ia={tache_ia_id} mode={mode_quiz}.",
        flush=True,
    )
    return RedirectResponse(f"/quiz/{tentative.id}", status_code=303)


@router.get("/quiz/historique")
def page_historique(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    tentatives = quiz_module.historique(session, utilisateur.id)
    stats = quiz_module.statistiques(tentatives)

    return templates.TemplateResponse(
        request,
        "quiz_historique.html",
        {"utilisateur": utilisateur, "tentatives": tentatives, "stats": stats},
    )


@router.get("/quiz/reflexion")
def page_reflexion(request: Request, matiere: Optional[str] = None, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    contexte_scolaire = _contexte_scolaire_quiz(utilisateur, session)
    est_profil_scolaire = (
        getattr(utilisateur, "cycle_education", None) in {"college", "lycee"}
        and not _enseignant_sans_classe_scolaire(utilisateur)
    )
    if est_profil_scolaire and not contexte_scolaire:
        return RedirectResponse(
            "/profil/academique?erreur=profil_scolaire_incomplet",
            status_code=303,
        )
    matieres = (
        _matieres_scolaires_disponibles(session, contexte_scolaire)
        if contexte_scolaire else _matieres_disponibles(session)
    )
    if contexte_scolaire:
        if not matieres:
            return RedirectResponse("/quiz?erreur=aucune_matiere_scolaire", status_code=303)
        if matiere:
            matiere = next((item for item in matieres if item.casefold() == matiere.casefold()), None)
        if not matiere:
            matiere = matieres[0]
    theme = theme_service.get_theme_du_jour(matiere=matiere or None)

    return templates.TemplateResponse(
        request,
        "quiz_reflexion.html",
        {
            "utilisateur": utilisateur,
            "theme": theme,
            "matieres": matieres,
            "matiere_selectionnee": matiere or "",
        },
    )


def _tentative_du_proprietaire(session: Session, tentative_id: int, utilisateur_id: int) -> Optional[TentativeQuiz]:
    tentative = session.get(TentativeQuiz, tentative_id)
    if not tentative or tentative.utilisateur_id != utilisateur_id:
        return None
    return tentative


@router.get("/quiz/{tentative_id}")
def page_passer_quiz(request: Request, tentative_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    tentative = _tentative_du_proprietaire(session, tentative_id, utilisateur.id)
    if not tentative:
        return RedirectResponse("/quiz", status_code=303)

    questions = quiz_module.questions(tentative)
    correction_visible = tentative.date_soumission is not None

    return templates.TemplateResponse(
        request,
        "quiz_passer.html",
        {
            "utilisateur": utilisateur,
            "tentative": tentative,
            "questions": questions,
            "reponses": quiz_module.reponses(tentative) or [],
            "confiances": quiz_calibration.lire_confiances(tentative),
            "correction_visible": correction_visible,
            "adaptatif": quiz_module.est_quiz_adaptatif(tentative),
            "adaptatif_etat": quiz_module.etat_adaptatif(tentative) if quiz_module.est_quiz_adaptatif(tentative) else None,
            "secondes_restantes": quiz_module.secondes_restantes_examen(tentative),
        },
    )


@router.post("/quiz/{tentative_id}/repondre")
async def repondre_question_adaptative(
    request: Request,
    tentative_id: int,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Enregistre une réponse adaptative et choisit la question suivante."""
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return JSONResponse({"erreur": "acces_refuse"}, status_code=401)

    tentative = _tentative_du_proprietaire(session, tentative_id, utilisateur.id)
    if not tentative or not quiz_module.est_quiz_adaptatif(tentative):
        return JSONResponse({"erreur": "quiz_adaptatif_introuvable"}, status_code=404)

    formulaire = await request.form()
    try:
        index_question = int(str(formulaire.get("question_index")))
        reponse = int(str(formulaire.get("reponse")))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Réponse adaptative invalide.") from exc

    confiance = str(formulaire.get("confiance") or "").strip().lower() or None
    if confiance is not None and confiance not in quiz_calibration.NIVEAUX_CONFIANCE:
        raise HTTPException(status_code=400, detail="Niveau de confiance invalide.")

    try:
        resultat = quiz_module.enregistrer_reponse_adaptative(
            session,
            tentative,
            index_question,
            reponse,
        )
    except quiz_module.QuizValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if confiance is not None:
        confiances = quiz_calibration.lire_confiances(tentative)
        if 0 <= index_question < len(confiances):
            confiances[index_question] = confiance
            quiz_calibration.fusionner_confiances(tentative, confiances)
            session.add(tentative)
            session.commit()

    return JSONResponse(resultat)


@router.post("/quiz/cible")
def generer_quiz_cible(
    request: Request,
    progression_id: int = Form(...),
    mission_id: Optional[int] = Form(None),
    document_id: Optional[int] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Genere un mini-quiz a partir d'une faiblesse deja identifiee."""
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    progression = session.get(ProgressionNotion, progression_id)
    if not progression or progression.utilisateur_id != utilisateur.id:
        return RedirectResponse("/mes-revisions", status_code=303)

    document_source = None
    if document_id is not None:
        document_source = session.get(Document, document_id)
        if (
            not document_source
            or document_source.statut != StatutDocument.APPROUVE
            or str(getattr(document_source, "fiche_validation_statut", "")) != "validee"
        ):
            return RedirectResponse("/mes-revisions?erreur=source_indisponible", status_code=303)
        if document_source.cercle_id is not None:
            membre = session.exec(
                select(MembreCercle).where(
                    MembreCercle.cercle_id == document_source.cercle_id,
                    MembreCercle.utilisateur_id == utilisateur.id,
                )
            ).first()
            if membre is None:
                return RedirectResponse("/mes-revisions?erreur=source_indisponible", status_code=303)

    mission_adaptative = None
    if mission_id is not None:
        mission_adaptative = session.get(MissionApprentissage, mission_id)
        if (
            not mission_adaptative
            or mission_adaptative.utilisateur_id != utilisateur.id
            or mission_adaptative.statut != "active"
            or mission_adaptative.progression_id != progression.id
            or mission_adaptative.etape not in {"pratiquer", "verifier"}
        ):
            return RedirectResponse("/session-apprentissage", status_code=303)

    if (
        mission_adaptative is None
        and progression.nb_erreurs <= 0
        and not quiz_module.revision_due(progression)
        and not quiz_module.besoin_preuve_maitrise(progression)
    ):
        return RedirectResponse("/mes-revisions", status_code=303)

    host = request.client.host if request.client else "inconnu"
    if limite_depassee(f"ia-quiz:user:{utilisateur.id}", 3, 300) or limite_depassee(f"ia-quiz:ip:{host}", 12, 300):
        return RedirectResponse("/mes-revisions?erreur=trop_de_generations", status_code=303)

    contexte_scolaire = _contexte_scolaire_quiz(utilisateur, session)
    if contexte_scolaire:
        niveau = contexte_scolaire["niveau"]
        matieres_scolaires = _matieres_scolaires_disponibles(session, contexte_scolaire)
        if not any(item.casefold() == progression.matiere.casefold() for item in matieres_scolaires):
            return RedirectResponse(
                "/mes-revisions?erreur=matiere_scolaire_indisponible",
                status_code=303,
            )
    elif (
        getattr(utilisateur, "cycle_education", None) in {"college", "lycee"}
        and not _enseignant_sans_classe_scolaire(utilisateur)
    ):
        return RedirectResponse(
            "/mes-revisions?erreur=profil_scolaire_incomplet",
            status_code=303,
        )
    else:
        niveau = progression.niveau or utilisateur.niveau or "L1"
        if niveau not in quiz_module.NIVEAUX:
            niveau = "L1"
        contexte_scolaire = None

    try:
        tentative = quiz_module.creer_tentative_ciblee(
            session,
            utilisateur,
            progression.matiere,
            niveau,
            progression.notion,
            nb_questions=5,
            progression=progression,
            cycle_education=contexte_scolaire["cycle_education"] if contexte_scolaire else None,
            niveau_scolaire_id=contexte_scolaire["niveau_scolaire_id"] if contexte_scolaire else None,
            option_scolaire_id=contexte_scolaire["option_scolaire_id"] if contexte_scolaire else None,
        )
    except quiz_module.QuizValidationError:
        return RedirectResponse("/mes-revisions?erreur=generation_ciblee", status_code=303)

    if document_source is not None:
        tentative.document_id = document_source.id
        session.add(tentative)
        session.commit()

    if mission_adaptative is not None:
        mission_adaptative.derniere_tentative_id = tentative.id
        mission_adaptative.derniere_session_tuteur_id = None
        mission_adaptative.date_maj = datetime.utcnow()
        session.add(mission_adaptative)
        session.commit()

    tache_ia_id = ai_queue.planifier_verification_quiz(tentative.id)
    print(
        f"[AI QUEUE] Route /quiz/cible quiz={tentative.id} tache_ia={tache_ia_id}.",
        flush=True,
    )
    return RedirectResponse(f"/quiz/{tentative.id}", status_code=303)


@router.post("/quiz/examen/generer")
def generer_examen(
    request: Request,
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Mode examen : matiere/niveau/difficulte tires au sort par le
    serveur (pas de formulaire a remplir), nombre de questions et duree
    fixes. Meme pipeline de generation/verification que le quiz normal."""
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    host = request.client.host if request.client else "inconnu"
    if limite_depassee(f"ia-quiz:user:{utilisateur.id}", 3, 300) or limite_depassee(f"ia-quiz:ip:{host}", 12, 300):
        return RedirectResponse("/quiz?erreur=trop_de_generations", status_code=303)

    contexte_scolaire = _contexte_scolaire_quiz(utilisateur, session)
    if (
        getattr(utilisateur, "cycle_education", None) in {"college", "lycee"}
        and not contexte_scolaire
        and not _enseignant_sans_classe_scolaire(utilisateur)
    ):
        return RedirectResponse(
            "/profil/academique?erreur=profil_scolaire_incomplet",
            status_code=303,
        )
    matieres = (
        _matieres_scolaires_disponibles(session, contexte_scolaire)
        if contexte_scolaire else _matieres_disponibles(session)
    )
    if contexte_scolaire and not matieres:
        return RedirectResponse("/quiz?erreur=aucune_matiere_scolaire", status_code=303)
    matiere = random.choice(matieres) if matieres else "Culture generale"
    niveau = contexte_scolaire["niveau"] if contexte_scolaire else random.choice(quiz_module.NIVEAUX)
    difficulte = random.choice(quiz_module.DIFFICULTES)

    try:
        tentative = quiz_module.creer_tentative_examen(
            session,
            utilisateur,
            matiere,
            niveau,
            difficulte,
            cycle_education=contexte_scolaire["cycle_education"] if contexte_scolaire else None,
            niveau_scolaire_id=contexte_scolaire["niveau_scolaire_id"] if contexte_scolaire else None,
            option_scolaire_id=contexte_scolaire["option_scolaire_id"] if contexte_scolaire else None,
        )
    except quiz_module.QuizValidationError:
        return RedirectResponse("/quiz?erreur=generation_invalide", status_code=303)

    tache_ia_id = ai_queue.planifier_verification_quiz(tentative.id)
    print(
        f"[AI QUEUE] Route /quiz/examen/generer quiz={tentative.id} tache_ia={tache_ia_id}.",
        flush=True,
    )
    return RedirectResponse(f"/quiz/{tentative.id}", status_code=303)


@router.post("/quiz/{tentative_id}/soumettre")
async def soumettre_quiz(request: Request, tentative_id: int, session: Session = Depends(get_session), _csrf: None = Depends(verifier_csrf)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    tentative = _tentative_du_proprietaire(session, tentative_id, utilisateur.id)
    if not tentative:
        return RedirectResponse("/quiz", status_code=303)

    if tentative.date_soumission is not None:
        return RedirectResponse(f"/quiz/{tentative.id}", status_code=303)

    try:
        questions = quiz_module.questions(tentative)
    except (ValueError, quiz_module.QuizValidationError) as exc:
        raise HTTPException(status_code=500, detail="Quiz stocke invalide.") from exc

    formulaire = await request.form()
    nb = len(questions)
    reponses_soumises: List[Optional[int]] = []
    confiances_soumises: List[Optional[str]] = []
    for i, question in enumerate(questions):
        valeur = formulaire.get(f"question_{i}")
        confiance = str(formulaire.get(f"confiance_{i}") or "").strip().lower() or None
        if confiance is not None and confiance not in quiz_calibration.NIVEAUX_CONFIANCE:
            raise HTTPException(status_code=400, detail="Niveau de confiance invalide.")

        if valeur is None or valeur == "":
            reponses_soumises.append(None)
            confiances_soumises.append(None)
            continue
        try:
            reponse = int(str(valeur))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Reponse de quiz invalide.") from exc
        if reponse < 0 or reponse >= len(question["choix"]):
            raise HTTPException(status_code=400, detail="Reponse de quiz invalide.")
        reponses_soumises.append(reponse)
        confiances_soumises.append(confiance)

    if tentative.mode_examen and quiz_module.secondes_restantes_examen(tentative) <= 0:
        reponses_soumises = [None] * nb
        confiances_soumises = [None] * nb

    mission_adaptative = session.exec(
        select(MissionApprentissage).where(
            MissionApprentissage.utilisateur_id == utilisateur.id,
            MissionApprentissage.derniere_tentative_id == tentative.id,
            MissionApprentissage.statut == "active",
        )
    ).first()

    try:
        quiz_module.corriger(session, tentative, reponses_soumises)
        quiz_calibration.fusionner_confiances(
            tentative,
            quiz_calibration.normaliser_confiances(
                confiances_soumises,
                len(questions),
            ),
        )
        if mission_adaptative is not None:
            progression_mission = session.get(ProgressionNotion, mission_adaptative.progression_id)
            score_pourcent = round(
                100 * int(tentative.score or 0) / max(int(tentative.nb_questions or 0), 1)
            )
            maitrise_reellement_confirmee = bool(
                progression_mission
                and quiz_module.diagnostiquer_maitrise(
                    progression_mission
                )["maitrise_confirmee"]
            )
            decision = adaptive_learning.transition_apres_quiz(
                score_pourcent,
                maitrise_reellement_confirmee,
            )
            mission_adaptative.etape = decision["etape"]
            mission_adaptative.statut = decision["statut"]
            mission_adaptative.nb_tentatives = int(mission_adaptative.nb_tentatives or 0) + 1
            mission_adaptative.dernier_score = score_pourcent
            mission_adaptative.dernier_feedback = decision["feedback"]
            mission_adaptative.date_maj = datetime.utcnow()
            mission_adaptative.date_fin = datetime.utcnow() if decision["statut"] == "terminee" else None
            session.add(mission_adaptative)
        session.add(tentative)
        session.commit()
        session.refresh(tentative)
    except quiz_module.QuizValidationError as exc:
        raise HTTPException(status_code=400, detail="Reponses de quiz invalides.") from exc

    gamification.enregistrer_action(
        session,
        utilisateur.id,
        "quiz",
        source_type="tentative_quiz",
        source_key=str(tentative.id),
    )
    session.commit()
    return RedirectResponse(f"/quiz/{tentative.id}/resultat", status_code=303)


@router.get("/quiz/{tentative_id}/resultat")
def page_resultat_quiz(request: Request, tentative_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    tentative = _tentative_du_proprietaire(session, tentative_id, utilisateur.id)
    if not tentative or tentative.date_soumission is None:
        return RedirectResponse("/quiz", status_code=303)

    questions_resultat = quiz_module.questions(tentative)
    reponses_resultat = quiz_module.reponses(tentative) or []
    confiances_resultat = quiz_calibration.lire_confiances(tentative)
    diagnostic_confiance = quiz_calibration.diagnostic_confiance(
        tentative,
        questions=questions_resultat,
        reponses=reponses_resultat,
    )
    mission_adaptative = session.exec(
        select(MissionApprentissage).where(
            MissionApprentissage.utilisateur_id == utilisateur.id,
            MissionApprentissage.derniere_tentative_id == tentative.id,
        )
    ).first()
    notions_detectees = []
    progressions_par_question = []
    vus = set()
    for i, question in enumerate(questions_resultat):
        correcte = i < len(reponses_resultat) and reponses_resultat[i] == question.get("index_bonne_reponse")
        if correcte:
            progressions_par_question.append(None)
            continue
        notion = (question.get("notion") or "").strip() or f"Notions générales — {tentative.matiere}"
        progression = session.exec(
            select(ProgressionNotion).where(
                ProgressionNotion.utilisateur_id == utilisateur.id,
                ProgressionNotion.matiere == tentative.matiere,
                ProgressionNotion.notion == notion,
            )
        ).first()
        progressions_par_question.append(progression.id if progression else None)
        if notion in vus:
            continue
        vus.add(notion)
        notions_detectees.append({
            "notion": notion,
            "progression_id": progression.id if progression else None,
        })

    diagnostic_examen = None
    if tentative.mode_examen:
        diagnostic_examen = quiz_module.diagnostic_examen(
            tentative,
            nb_erreurs=sum(
                1
                for i, question in enumerate(questions_resultat)
                if not (
                    i < len(reponses_resultat)
                    and reponses_resultat[i] == question.get("index_bonne_reponse")
                )
            ),
            nb_notions_faibles=len(notions_detectees),
        )

    return templates.TemplateResponse(
        request,
        "quiz_resultat.html",
        {
            "utilisateur": utilisateur,
            "tentative": tentative,
            "questions": questions_resultat,
            "reponses": reponses_resultat,
            "confiances": confiances_resultat,
            "diagnostic_confiance": diagnostic_confiance,
            "notions_detectees": notions_detectees,
            "progressions_par_question": progressions_par_question,
            "diagnostic_examen": diagnostic_examen,
            "mission_adaptative": mission_adaptative,
        },
    )


@router.post("/quiz/{tentative_id}/questions/{index_question}/signaler")
def signaler_question_quiz(
    request: Request,
    tentative_id: int,
    index_question: int,
    motif: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection


    tentative = _tentative_du_proprietaire(session, tentative_id, utilisateur.id)
    if not tentative or tentative.date_soumission is None:
        return RedirectResponse("/quiz", status_code=303)

    quiz_module.signaler_question(session, tentative_id, index_question, utilisateur.id, motif)

    return RedirectResponse(f"/quiz/{tentative_id}/resultat?signale=1", status_code=303)
