from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form
from typing import Optional
import re
from fastapi.responses import RedirectResponse
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..auth import utilisateur_courant
from ..dependencies import acces_ia_ou_redirection
from ..models import Document, MembreCercle, MissionApprentissage, SessionTuteur, ProgressionNotion, StatutDocument
from ..storage import ouvrir_fichier_local
from ..text_extraction import extraire_texte
from ..ia_transport import normaliser_structure_tuteur
from .. import ai_queue, ai_quiz
from ..rate_limit import limite_depassee
from .. import quiz as quiz_module
from .. import gamification

router = APIRouter()

NB_HISTORIQUE_AFFICHE = 10
MAX_EXTRAIT_DOCUMENT = 6000


def _utilisateur_membre_cercle(session: Session, cercle_id: Optional[int], utilisateur_id: int) -> bool:
    if cercle_id is None:
        return True
    return session.exec(
        select(MembreCercle).where(
            MembreCercle.cercle_id == cercle_id,
            MembreCercle.utilisateur_id == utilisateur_id,
        )
    ).first() is not None


def _contexte_progression_tuteur(progression: ProgressionNotion) -> str:
    """Construit un contexte pédagogique compact à partir de la mémoire de la notion."""
    score = max(0, min(100, int(progression.score_maitrise or 0)))
    prochaine = (
        progression.prochaine_revision_le.strftime("%d/%m/%Y")
        if progression.prochaine_revision_le
        else "dès maintenant"
    )
    statut = "fragile" if score < 50 else ("en cours d'acquisition" if score < 75 else "plutôt maîtrisée")
    diagnostic = quiz_module.diagnostiquer_maitrise(progression)
    return (
        "MEMOIRE D'APPRENTISSAGE — cette notion a déjà été travaillée par cet étudiant. "
        f"Notion={progression.notion}; matière={progression.matiere}; niveau={progression.niveau or 'non précisé'}; "
        f"maîtrise={score}%; confiance={diagnostic['confiance']}%; "
        f"questions={progression.nb_questions}; réussites={progression.nb_reussites}; "
        f"erreurs={progression.nb_erreurs}; série actuelle={progression.serie_reussites}; "
        f"niveau maximal réussi={diagnostic['niveau_max_reussi']}; preuve={diagnostic['libelle']}; "
        f"prochaine révision={prochaine}. "
        "Traite la preuve de maîtrise comme une contrainte pédagogique : "
        "si elle n'est pas prouvée, aide l'étudiant à combler les preuves manquantes "
        "avant de considérer la notion acquise. Rappelle les erreurs à éviter, "
        "ne redonne pas mécaniquement la même explication, et termine par un exercice "
        "court permettant de vérifier la compréhension."
    )


def _extrait_document_pertinent(document: Document, question: str) -> str:
    """Extrait localement quelques passages d'un document approuvé.

    On privilégie les blocs contenant des termes significatifs de la question,
    puis on limite fortement la taille envoyée au modèle afin de préserver la
    latence. Le texte reste une source de contexte : le Tuteur doit signaler
    lorsqu'il ne trouve pas l'information plutôt que l'inventer.
    """
    try:
        with ouvrir_fichier_local(document.chemin_fichier) as chemin_local:
            texte = extraire_texte(str(chemin_local)) or ""
    except Exception:
        return ""

    texte = re.sub(r"\s+", " ", texte).strip()
    if not texte:
        return ""

    blocs = [texte[i:i + 1800] for i in range(0, min(len(texte), 18000), 1800)]
    termes = {
        mot.lower()
        for mot in re.findall(r"[A-Za-zÀ-ÿ0-9]{4,}", question or "")
        if mot.lower() not in {"avec", "pour", "dans", "cette", "comme", "donne", "aide-moi"}
    }

    def score(bloc: str) -> int:
        bas = bloc.lower()
        return sum(bas.count(mot) for mot in termes)

    blocs_scores = sorted(enumerate(blocs), key=lambda item: (score(item[1]), -item[0]), reverse=True)
    selection = [bloc for _, bloc in blocs_scores[:3] if score(bloc) > 0]
    if not selection:
        selection = blocs[:3]

    extrait = "\n\n".join(selection)
    return extrait[:MAX_EXTRAIT_DOCUMENT]


@router.get("/tuteur")
def page_tuteur(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    historique = session.exec(
        select(SessionTuteur)
        .where(SessionTuteur.utilisateur_id == utilisateur.id)
        .order_by(SessionTuteur.date_creation.desc())
        .limit(NB_HISTORIQUE_AFFICHE)
    ).all()

    notions = quiz_module.notions_a_revoir(session, utilisateur.id, limit=8)

    return templates.TemplateResponse(
        request,
        "tuteur.html",
        {
            "utilisateur": utilisateur,
            "historique": historique,
            "notions_a_revoir": notions,
        },
    )


@router.post("/tuteur/demander")
def demander_tuteur(
    request: Request,
    question: str = Form(...),
    progression_id: Optional[int] = Form(None),
    mission_id: Optional[int] = Form(None),
    document_id: Optional[int] = Form(None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    host = request.client.host if request.client else "inconnu"
    if limite_depassee(f"ia-tuteur:user:{utilisateur.id}", 10, 300) or limite_depassee(f"ia-tuteur:ip:{host}", 30, 300):
        return RedirectResponse("/tuteur?erreur=trop_de_questions", status_code=303)

    question = question.strip()[:4000]
    if not question:
        return RedirectResponse("/tuteur?erreur=question_requise", status_code=303)

    mission_adaptative = None
    if mission_id is not None:
        mission_adaptative = session.get(MissionApprentissage, mission_id)
        if (
            not mission_adaptative
            or mission_adaptative.utilisateur_id != utilisateur.id
            or mission_adaptative.statut != "active"
            or mission_adaptative.etape != "comprendre"
            or (progression_id is not None and progression_id != mission_adaptative.progression_id)
        ):
            return RedirectResponse("/session-apprentissage", status_code=303)
        progression_id = mission_adaptative.progression_id

    progression = None
    if progression_id:
        candidat_progression = session.get(ProgressionNotion, progression_id)
        if (
            candidat_progression
            and candidat_progression.utilisateur_id == utilisateur.id
            and (
                mission_adaptative is not None
                or candidat_progression.nb_erreurs > 0
                or quiz_module.revision_due(candidat_progression)
            )
        ):
            progression = candidat_progression

    document_source = None
    if document_id:
        candidat = session.get(Document, document_id)
        if (
            candidat
            and candidat.statut == StatutDocument.APPROUVE
            and _utilisateur_membre_cercle(session, candidat.cercle_id, utilisateur.id)
        ):
            document_source = candidat

    question_pour_ia = question
    matiere_pour_ia = progression.matiere if progression else None

    if progression:
        question_pour_ia = (
            f"{question}\n\n"
            f"{_contexte_progression_tuteur(progression)}"
        )

    if document_source:
        extrait = _extrait_document_pertinent(document_source, question)
        matiere_pour_ia = matiere_pour_ia or document_source.matiere
        if extrait:
            question_pour_ia = (
                f"{question}\n\n"
                f"SOURCE DOCUMENTAIRE — {document_source.titre} "
                f"({document_source.matiere}, {document_source.annee})\n"
                "Utilise prioritairement cet extrait comme source de contexte. "
                "Ne présente pas une information comme provenant du document si elle n'y figure pas. "
                "Si l'extrait est insuffisant, indique-le clairement.\n\n"
                f"EXTRAIT :\n{extrait}"
            )

    if document_source and progression:
        question_pour_ia = (
            f"{question_pour_ia}\n\n"
            "Le contexte documentaire et la mémoire d'apprentissage sont complémentaires : "
            "utilise le document comme source de contenu et l'historique comme source de personnalisation."
        )

    reponse = ai_quiz.generer_reponse_tuteur(
        question_pour_ia,
        notion=progression.notion if progression else None,
        matiere=matiere_pour_ia,
        verifier=False,
    )
    # La génération initiale est déjà livrée. La relecture multi-modèles
    # est toujours une tâche durable et ne dépend plus du cycle de vie HTTP.
    reponse.pop("_statut_verification", None)
    reponse.pop("_erreur_verification", None)
    reponse.pop("_verification_ok", None)

    # Canonisation finale avant tout stockage, même en cas de secours ou
    # d'arbitrage multi-modèles partiel.
    reponse = normaliser_structure_tuteur(reponse)

    session_tuteur = SessionTuteur(
        utilisateur_id=utilisateur.id,
        notion=progression.notion if progression else None,
        progression_id=progression.id if progression else None,
        question=question,
        explication=reponse["explication"],
        exemple=reponse["exemple"],
        exercice=reponse["exercice"],
        correction=reponse["correction"],
        statut_verification_ia="en_attente",
        erreur_verification_ia=None,
    )
    session.add(session_tuteur)
    session.flush()
    if mission_adaptative is not None:
        mission_adaptative.etape = "pratiquer"
        mission_adaptative.derniere_tentative_id = None
        mission_adaptative.derniere_session_tuteur_id = session_tuteur.id
        mission_adaptative.dernier_feedback = "Explication enregistrée. Passe maintenant au quiz ciblé sur cette même notion."
        mission_adaptative.date_maj = datetime.utcnow()
        mission_adaptative.date_fin = None
        session.add(mission_adaptative)
    gamification.enregistrer_action(
        session,
        utilisateur.id,
        "tuteur",
        source_type="session_tuteur",
        source_key=str(session_tuteur.id),
    )
    session.commit()
    session.refresh(session_tuteur)

    # La réponse initiale est livrée immédiatement. La vérification
    # multi-modèles est maintenant persistée dans la file IA : le worker
    # peut la reprendre après redémarrage, avec retries et lease.
    ai_queue.planifier_verification_tuteur(session_tuteur.id)

    return RedirectResponse(f"/tuteur/{session_tuteur.id}", status_code=303)


@router.get("/tuteur/{session_id}/statut")
def statut_tuteur(request: Request, session_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return JSONResponse({"statut": "non_autorise"}, status_code=401)

    session_tuteur = session.get(SessionTuteur, session_id)
    if not session_tuteur or session_tuteur.utilisateur_id != utilisateur.id:
        return JSONResponse({"statut": "introuvable"}, status_code=404)

    # MODIF : l'API transmet désormais uniquement le texte brut de la
    # réponse IA ; le rendu Markdown/KaTeX est réalisé dans le navigateur.
    contenu = normaliser_structure_tuteur({
        "explication": session_tuteur.explication,
        "exemple": session_tuteur.exemple,
        "exercice": session_tuteur.exercice,
        "correction": session_tuteur.correction,
    })

    def rendu(champ: str) -> str:
        return contenu.get(champ, "")

    return {
        "statut": session_tuteur.statut_verification_ia,
        "erreur": session_tuteur.erreur_verification_ia,
        "date_verification": (
            session_tuteur.date_verification_ia.isoformat()
            if session_tuteur.date_verification_ia
            else None
        ),
        "contenu": {
            "explication": rendu("explication"),
            "exemple": rendu("exemple"),
            "exercice": rendu("exercice"),
            "correction": rendu("correction"),
        },
    }


@router.get("/tuteur/{session_id}")
def page_reponse_tuteur(request: Request, session_id: int, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    session_tuteur = session.get(SessionTuteur, session_id)
    if not session_tuteur or session_tuteur.utilisateur_id != utilisateur.id:
        return RedirectResponse("/tuteur", status_code=303)

    # MODIF : le template reçoit aussi les contenus canonisés pour éviter
    # que les anciennes sessions affichent des marqueurs de transport.
    progression = (
        session.get(ProgressionNotion, session_tuteur.progression_id)
        if session_tuteur.progression_id
        else None
    )

    mission_adaptative = session.exec(
        select(MissionApprentissage).where(
            MissionApprentissage.utilisateur_id == utilisateur.id,
            MissionApprentissage.derniere_session_tuteur_id == session_tuteur.id,
        )
    ).first()
    session_vue = dict(
        utilisateur=utilisateur,
        session_tuteur=session_tuteur,
        progression_tuteur=progression,
        mission_adaptative=mission_adaptative,
        contenu_tuteur=normaliser_structure_tuteur({
            "explication": session_tuteur.explication,
            "exemple": session_tuteur.exemple,
            "exercice": session_tuteur.exercice,
            "correction": session_tuteur.correction,
        }),
    )
    return templates.TemplateResponse(
        request,
        "tuteur_reponse.html",
        session_vue,
    )
