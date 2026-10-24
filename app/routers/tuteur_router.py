from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form
from typing import Optional
import json
import re
from fastapi.responses import RedirectResponse
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from ..database import get_session
from ..templating import templates
from ..csrf import verifier_csrf
from ..auth import utilisateur_courant
from ..dependencies import acces_ia_ou_redirection
from ..models import (
    Document, MembreCercle, MissionApprentissage, SessionTuteur, ProgressionNotion,
    StatutDocument, NiveauScolaire, OptionScolaire, ReferentielScolaire,
)
from ..storage import ouvrir_fichier_local
from ..text_extraction import extraire_texte, extraire_passages_avec_sources
from ..ia_transport import normaliser_structure_tuteur
from .. import ai_queue, ai_quiz
from ..rate_limit import limite_depassee
from .. import quiz as quiz_module
from .. import gamification
from ..apprentissage_memoire import interactions_tuteur_recentes, formater_memoire_tuteur

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


def _contexte_scolaire_tuteur(utilisateur, session: Session) -> Optional[dict]:
    """Valide le parcours collège/lycée avant de l'utiliser dans le Tuteur IA."""
    cycle = getattr(utilisateur, "cycle_education", None)
    if cycle not in {"college", "lycee"}:
        return None

    niveau_id = getattr(utilisateur, "niveau_scolaire_id", None)
    if not niveau_id:
        return {}
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
        or niveau.cycle != cycle
    ):
        return {}

    option_id = getattr(utilisateur, "option_scolaire_id", None)
    option = session.get(OptionScolaire, option_id) if option_id else None
    parent = (
        session.get(OptionScolaire, option.parent_option_id)
        if option and option.parent_option_id else None
    )
    if option_id and (
        not option
        or option.referentiel_id != referentiel.id
        or option.niveau_id != niveau.id
        or not option.est_active
        or option.statut_validation != "verifie"
        or (
            option.parent_option_id is not None
            and (
                not parent
                or parent.referentiel_id != referentiel.id
                or parent.niveau_id != niveau.id
                or parent.parent_option_id is not None
                or not parent.est_active
                or parent.statut_validation != "verifie"
            )
        )
    ):
        return {}

    options_compatibles = {option.id} if option else set()
    if parent:
        options_compatibles.add(parent.id)
    return {
        "niveau": niveau.libelle,
        "cycle_education": niveau.cycle,
        "niveau_scolaire_id": niveau.id,
        "option_scolaire_id": option.id if option else None,
        "options_compatibles": options_compatibles,
        "etablissement_scolaire_id": getattr(utilisateur, "etablissement_scolaire_id", None),
    }


def _document_scolaire_compatible(document: Document, contexte: dict) -> bool:
    """Évite de tutoriser un document d'une autre classe/série/école."""
    if getattr(document, "portee_academique", "universitaire") != "scolaire":
        return True
    if getattr(document, "niveau_scolaire_id", None) != contexte.get("niveau_scolaire_id"):
        return False
    option_id = getattr(document, "option_scolaire_id", None)
    if option_id and option_id not in contexte.get("options_compatibles", set()):
        return False
    etablissement_id = getattr(document, "etablissement_scolaire_id", None)
    profil_etablissement_id = contexte.get("etablissement_scolaire_id")
    if etablissement_id and etablissement_id != profil_etablissement_id:
        return False
    return True


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


def _contexte_historique_tuteur(
    session: Session,
    utilisateur_id: int,
    progression: Optional[ProgressionNotion],
) -> str:
    """Réutilise les échanges antérieurs du même étudiant sur cette notion."""
    if not progression or progression.id is None:
        return ""
    interactions = interactions_tuteur_recentes(
        session,
        utilisateur_id,
        progression_id=progression.id,
        limite=3,
    )
    return formater_memoire_tuteur(interactions, limite_caracteres=1700)


def _extrait_document_pertinent(document: Document, question: str) -> tuple[str, list[str]]:
    """Extrait quelques passages d'un document approuvé en gardant leurs repères.

    Un repère n'est renvoyé que si l'extracteur peut l'associer au passage :
    numéro de page pour un PDF textuel, diapositive pour un PPTX ou repère de
    paragraphe pour un DOCX dont la pagination n'est pas disponible.
    """
    try:
        with ouvrir_fichier_local(document.chemin_fichier) as chemin_local:
            passages = extraire_passages_avec_sources(str(chemin_local))
            if not passages:
                texte = extraire_texte(str(chemin_local)) or ""
                if texte.strip():
                    passages = [{
                        "reference": "document (pagination indisponible)",
                        "texte": texte,
                    }]
    except Exception:
        return "", []

    blocs = []
    longueur_totale = 0
    for passage in passages:
        reference = str(passage.get("reference") or "document (pagination indisponible)")[:120]
        texte = re.sub(r"\s+", " ", str(passage.get("texte") or "")).strip()
        if not texte:
            continue
        for debut in range(0, len(texte), 1800):
            if longueur_totale >= 18000:
                break
            morceau = texte[debut:debut + 1800]
            blocs.append({"references": [reference], "texte": morceau})
            longueur_totale += len(morceau)
        if longueur_totale >= 18000:
            break

    if not blocs:
        return "", []

    termes = {
        mot.lower()
        for mot in re.findall(r"[A-Za-zÀ-ÿ0-9]{4,}", question or "")
        if mot.lower() not in {"avec", "pour", "dans", "cette", "comme", "donne", "aide-moi"}
    }

    def score(bloc: dict) -> int:
        bas = bloc["texte"].lower()
        return sum(bas.count(mot) for mot in termes)

    blocs_scores = sorted(
        enumerate(blocs),
        key=lambda item: (score(item[1]), -item[0]),
        reverse=True,
    )
    selection = [bloc for _, bloc in blocs_scores if score(bloc) > 0][:3]
    if not selection:
        selection = blocs[:3]

    references = []
    morceaux = []
    for bloc in selection:
        for reference in bloc["references"]:
            if reference not in references:
                references.append(reference)
        libelle_references = ", ".join(bloc["references"])
        morceaux.append(f"[Référence source : {libelle_references}]\n{bloc['texte']}")

    return "\n\n".join(morceaux)[:MAX_EXTRAIT_DOCUMENT], references


def _charger_sources_documentaires(session_tuteur: SessionTuteur) -> list[dict]:
    """Charge les références enregistrées sans faire confiance au JSON historique."""
    try:
        sources = json.loads(session_tuteur.sources_documentaires_json or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(sources, list):
        return []
    resultat = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        titre = str(source.get("titre") or "").strip()[:300]
        references = source.get("references")
        if not isinstance(references, list):
            references = []
        references = [str(ref).strip()[:120] for ref in references if str(ref).strip()]
        if titre:
            resultat.append({"titre": titre, "references": references[:10]})
    return resultat[:5]


@router.get("/tuteur")
def page_tuteur(request: Request, session: Session = Depends(get_session)):
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    contexte_scolaire = _contexte_scolaire_tuteur(utilisateur, session)
    if getattr(utilisateur, "cycle_education", None) in {"college", "lycee"} and not contexte_scolaire:
        return RedirectResponse(
            "/profil/academique?erreur=profil_scolaire_incomplet",
            status_code=303,
        )

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

    contexte_scolaire = _contexte_scolaire_tuteur(utilisateur, session)
    if getattr(utilisateur, "cycle_education", None) in {"college", "lycee"} and not contexte_scolaire:
        return RedirectResponse(
            "/profil/academique?erreur=profil_scolaire_incomplet",
            status_code=303,
        )

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
            # Un ancien résultat universitaire ne doit pas guider un profil
            # scolaire, ni mélanger les difficultés de deux classes.
            if contexte_scolaire:
                niveau_progression = (candidat_progression.niveau or "").strip().casefold()
                if niveau_progression and niveau_progression != contexte_scolaire["niveau"].casefold():
                    return RedirectResponse(
                        "/tuteur?erreur=notion_hors_niveau_scolaire",
                        status_code=303,
                    )
            progression = candidat_progression

    document_source = None
    if document_id:
        candidat = session.get(Document, document_id)
        if (
            candidat
            and candidat.statut == StatutDocument.APPROUVE
            and _utilisateur_membre_cercle(session, candidat.cercle_id, utilisateur.id)
            and (
                getattr(candidat, "portee_academique", "universitaire") != "scolaire"
                or (
                    contexte_scolaire
                    and _document_scolaire_compatible(candidat, contexte_scolaire)
                )
            )
        ):
            if candidat.fiche_validation_statut != "validee":
                return RedirectResponse(
                    f"/documents/{candidat.id}/apprendre?erreur=fiche_a_verifier#fiche-verification",
                    status_code=303,
                )
            document_source = candidat

    question_pour_ia = question
    matiere_pour_ia = progression.matiere if progression else None
    extrait_document = ""
    references_source: list[str] = []

    if progression:
        question_pour_ia = (
            f"{question}\n\n"
            f"{_contexte_progression_tuteur(progression)}"
        )
        memoire_tuteur = _contexte_historique_tuteur(
            session, utilisateur.id, progression
        )
        if memoire_tuteur:
            question_pour_ia = f"{question_pour_ia}\n\n{memoire_tuteur}"

    if document_source:
        extrait_document, references_source = _extrait_document_pertinent(document_source, question)
        matiere_pour_ia = matiere_pour_ia or document_source.matiere
        if extrait_document:
            question_pour_ia = (
                f"{question}\n\n"
                f"SOURCE DOCUMENTAIRE — {document_source.titre} "
                f"({document_source.matiere}, {document_source.annee})\n"
                "Utilise prioritairement cet extrait comme source de contexte. "
                "Les passages portent leur repère [Référence source : ...] : lorsque tu t'appuies "
                "sur un passage, reprends exactement son repère dans l'explication. "
                "N'invente jamais une page, une diapositive ou une référence. "
                "Ne présente pas une information comme provenant du document si elle n'y figure pas. "
                "Si l'extrait est insuffisant, indique-le clairement.\n\n"
                f"EXTRAIT :\n{extrait_document}"
            )

    if document_source and progression:
        question_pour_ia = (
            f"{question_pour_ia}\n\n"
            "Le contexte documentaire et la mémoire d'apprentissage sont complémentaires : "
            "utilise le document comme source de contenu et l'historique comme source de personnalisation."
        )

    if contexte_scolaire:
        question_pour_ia = (
            "CONTEXTE PÉDAGOGIQUE VALIDÉ — "
            f"élève de {contexte_scolaire['cycle_education']} en classe "
            f"{contexte_scolaire['niveau']}. Adapte les prérequis, les exemples "
            "et les exercices au programme de cette classe ; n'utilise pas de "
            "notions universitaires non expliquées.\n\n"
            + question_pour_ia
        )
        reponse = ai_quiz.generer_reponse_tuteur(
            question_pour_ia,
            notion=progression.notion if progression else None,
            matiere=matiere_pour_ia,
            niveau=contexte_scolaire["niveau"],
            cycle_education=contexte_scolaire["cycle_education"],
            verifier=False,
        )
    else:
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

    # L'indice est capturé séparément des quatre sections canoniques.
    indice_tuteur = str(reponse.get("indice") or "").strip()[:2400]
    if not indice_tuteur:
        indice_tuteur = (
            "Indice de méthode : repère les données utiles et ce que l'on cherche. "
            "Identifie la règle pertinente, puis essaie une première étape avant la correction."
        )
    # Canonisation finale avant tout stockage, même en cas de secours ou
    # d'arbitrage multi-modèles partiel.
    reponse = normaliser_structure_tuteur(reponse)

    session_tuteur = SessionTuteur(
        utilisateur_id=utilisateur.id,
        notion=progression.notion if progression else None,
        progression_id=progression.id if progression else None,
        question=question,
        indice=indice_tuteur,
        explication=reponse["explication"],
        exemple=reponse["exemple"],
        exercice=reponse["exercice"],
        correction=reponse["correction"],
        sources_documentaires_json=json.dumps(
            [{
                "titre": document_source.titre,
                "references": references_source,
            }] if document_source and extrait_document and references_source else [],
            ensure_ascii=False,
        ),
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
    indice = str(session_tuteur.indice or "")

    def rendu(champ: str) -> str:
        return contenu.get(champ, "")

    # Ne pas compter sur le masquage HTML : l'API ne doit jamais livrer
    # l'exercice ni sa correction avant la vérification de compréhension.
    comprehension_ok = bool(getattr(session_tuteur, "comprehension_validee", False))

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
            "exercice": rendu("exercice") if comprehension_ok else "",
            "correction": rendu("correction") if comprehension_ok else "",
            "indice": indice,
        },
    }



@router.post("/tuteur/{session_id}/verifier-comprehension")
def verifier_comprehension_tuteur_session(
    request: Request,
    session_id: int,
    reponse: str = Form(...),
    session: Session = Depends(get_session),
    _csrf: None = Depends(verifier_csrf),
):
    """Vérifie la compréhension de l'étudiant sans exposer la correction."""
    utilisateur = utilisateur_courant(request, session)
    redirection = acces_ia_ou_redirection(utilisateur, session)
    if redirection:
        return redirection

    session_tuteur = session.get(SessionTuteur, session_id)
    if not session_tuteur or session_tuteur.utilisateur_id != utilisateur.id:
        return RedirectResponse("/tuteur", status_code=303)
    if session_tuteur.comprehension_validee:
        return RedirectResponse(f"/tuteur/{session_id}#comprehension-tuteur", status_code=303)

    reponse = str(reponse or "").strip()[:2000]
    if not reponse:
        return RedirectResponse(
            f"/tuteur/{session_id}?erreur=comprehension_requise#comprehension-tuteur",
            status_code=303,
        )
    host = request.client.host if request.client else "inconnu"
    if limite_depassee(f"ia-tuteur-comprehension:user:{utilisateur.id}", 10, 300) or limite_depassee(
        f"ia-tuteur-comprehension:ip:{host}", 30, 300
    ):
        return RedirectResponse(
            f"/tuteur/{session_id}?erreur=trop_de_questions#comprehension-tuteur",
            status_code=303,
        )

    matiere = None
    if session_tuteur.progression_id:
        progression = session.get(ProgressionNotion, session_tuteur.progression_id)
        if progression:
            matiere = progression.matiere

    evaluation = ai_quiz.verifier_comprehension_tuteur(
        question=session_tuteur.question,
        notion=session_tuteur.notion,
        matiere=matiere,
        explication=session_tuteur.explication,
        exemple=session_tuteur.exemple,
        indice_precedent=session_tuteur.indice,
        reponse_etudiant=reponse,
    )
    session_tuteur.comprehension_reponse = reponse
    session_tuteur.comprehension_feedback = str(evaluation.get("feedback") or "")[:900]
    session_tuteur.comprehension_indice = (
        str(evaluation.get("indice_suivant") or "")[:900]
        if not evaluation.get("compris")
        else ""
    )
    session_tuteur.comprehension_validee = bool(
        evaluation.get("compris") and evaluation.get("verification_disponible", True)
    )
    session.add(session_tuteur)
    session.commit()

    return RedirectResponse(f"/tuteur/{session_id}#comprehension-tuteur", status_code=303)


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
        sources_documentaires=_charger_sources_documentaires(session_tuteur),
    )
    return templates.TemplateResponse(
        request,
        "tuteur_reponse.html",
        session_vue,
    )
