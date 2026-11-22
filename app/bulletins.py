"""Calculs et génération PDF des bulletins officiels MITARIDALA."""

from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from sqlmodel import Session, select

from .models import (
    Cours,
    CoefficientMatiereEtablissement,
    Devoir,
    ParametresAcademiquesEtablissement,
    PointagePresence,
    RenduDevoir,
    Seance,
    StatutPointage,
    Utilisateur,
)


_STATUTS_PRESENCE = ("present", "absent", "retard", "excuse")


def normaliser_periode(valeur: str | None) -> str:
    """Normalise le libellé sans modifier sa signification."""
    return " ".join((valeur or "").split())[:40]


def construire_snapshot_bulletin(
    session: Session,
    cours: Cours,
    eleve: Utilisateur,
    periode: str,
    appreciation: str | None,
    *,
    publie_le: datetime | None = None,
) -> dict[str, Any]:
    """Construit les données figées d'un bulletin à partir des notes corrigées.

    Une correction est comptée uniquement si note et date_correction sont
    présentes. Les notes sont normalisées selon le barème de l'établissement,
    pondérées par coefficient d'évaluation et converties sur 20 pour la moyenne
    générale. La présence est affichée en cumul du cours :
    les séances ne portent pas encore de période pédagogique normalisée.
    """
    periode_normalisee = normaliser_periode(periode)
    if not periode_normalisee:
        raise ValueError("La période est obligatoire.")

    devoirs = session.exec(
        select(Devoir).where(
            Devoir.cours_id == cours.id,
            Devoir.archive == False,  # noqa: E712
        ).order_by(Devoir.date_creation, Devoir.id)
    ).all()
    devoirs_periode = [
        devoir for devoir in devoirs
        if normaliser_periode(devoir.periode).casefold() == periode_normalisee.casefold()
        and float(devoir.bareme or 0) > 0
    ]
    if not devoirs_periode:
        raise ValueError("Aucune évaluation n'est associée à cette période.")

    configuration = None
    coefficient_matiere = 1.0
    if cours.etablissement_scolaire_id is not None:
        configuration = session.exec(
            select(ParametresAcademiquesEtablissement)
            .where(
                ParametresAcademiquesEtablissement.etablissement_id == cours.etablissement_scolaire_id,
                ParametresAcademiquesEtablissement.est_actif == True,  # noqa: E712
            )
            .order_by(
                ParametresAcademiquesEtablissement.date_modification.desc(),
                ParametresAcademiquesEtablissement.id.desc(),
            )
            .limit(1)
        ).first()
        if configuration and cours.niveau_scolaire_id and cours.matiere_scolaire_id:
            criteres_coefficient = [
                CoefficientMatiereEtablissement.parametres_id == configuration.id,
                CoefficientMatiereEtablissement.niveau_id == cours.niveau_scolaire_id,
                CoefficientMatiereEtablissement.matiere_id == cours.matiere_scolaire_id,
            ]
            if cours.option_scolaire_id is not None:
                coefficient_exact = session.exec(
                    select(CoefficientMatiereEtablissement)
                    .where(
                        *criteres_coefficient,
                        CoefficientMatiereEtablissement.option_id == cours.option_scolaire_id,
                    )
                    .limit(1)
                ).first()
                coefficient_general = session.exec(
                    select(CoefficientMatiereEtablissement)
                    .where(
                        *criteres_coefficient,
                        CoefficientMatiereEtablissement.option_id.is_(None),
                    )
                    .limit(1)
                ).first()
                regle_coefficient = coefficient_exact or coefficient_general
            else:
                regle_coefficient = session.exec(
                    select(CoefficientMatiereEtablissement)
                    .where(
                        *criteres_coefficient,
                        CoefficientMatiereEtablissement.option_id.is_(None),
                    )
                    .limit(1)
                ).first()
            if regle_coefficient:
                coefficient_matiere = float(regle_coefficient.coefficient or 1.0)

    note_maximale = float(configuration.note_maximale) if configuration else 20.0
    seuil_reussite = float(configuration.seuil_reussite) if configuration else 10.0
    bareme_bulletin = note_maximale if note_maximale > 0 else 20.0

    devoirs_par_id = {devoir.id: devoir for devoir in devoirs_periode}
    rendus = session.exec(
        select(RenduDevoir).where(
            RenduDevoir.utilisateur_id == eleve.id,
            RenduDevoir.devoir_id.in_(sorted(devoirs_par_id)),
            RenduDevoir.note.is_not(None),
            RenduDevoir.date_correction.is_not(None),
        ).order_by(RenduDevoir.date_correction, RenduDevoir.id)
    ).all()

    evaluations: list[dict[str, Any]] = []
    total_pondere = 0.0
    poids_total = 0.0
    for rendu in rendus:
        devoir = devoirs_par_id.get(rendu.devoir_id)
        if not devoir or rendu.note is None or float(devoir.bareme) <= 0:
            continue
        note = float(rendu.note)
        bareme = float(devoir.bareme)
        coefficient = max(float(devoir.coefficient or 1), 0.1)
        if note < 0 or note > bareme:
            continue
        note_sur_20 = round(note / bareme * 20, 2)
        note_sur_echelle = round(note / bareme * bareme_bulletin, 2)
        total_pondere += note_sur_echelle * coefficient
        poids_total += coefficient
        evaluations.append({
            "evaluation": devoir.titre,
            "note": round(note, 2),
            "bareme": round(bareme, 2),
            "coefficient": round(coefficient, 2),
            "note_sur_20": note_sur_20,
            "note_sur_echelle": note_sur_echelle,
            "appreciation": (rendu.appreciation_prof or "").strip(),
        })

    if not evaluations or poids_total <= 0:
        raise ValueError("Aucune note corrigée n'est disponible pour cette période.")

    seances = session.exec(
        select(Seance).where(Seance.cours_id == cours.id)
    ).all()
    ids_seances = [seance.id for seance in seances if seance.id is not None]
    pointages = (
        session.exec(
            select(PointagePresence).where(
                PointagePresence.utilisateur_id == eleve.id,
                PointagePresence.seance_id.in_(ids_seances),
            )
        ).all()
        if ids_seances else []
    )
    presences = {statut: 0 for statut in _STATUTS_PRESENCE}
    for pointage in pointages:
        statut = (
            pointage.statut.value
            if hasattr(pointage.statut, "value")
            else str(pointage.statut)
        )
        if statut in presences:
            presences[statut] += 1

    professeur = session.get(Utilisateur, cours.professeur_id)
    publie_le = publie_le or datetime.utcnow()
    return {
        "version": 1,
        "eleve": eleve.nom,
        "cours_id": cours.id,
        "cours": cours.nom,
        "matiere": cours.matiere,
        "niveau": cours.niveau,
        "periode": periode_normalisee,
        "professeur": professeur.nom if professeur else "Équipe pédagogique",
        "moyenne": round(total_pondere / poids_total, 2),
        "moyenne_sur": round(bareme_bulletin, 2),
        "seuil_reussite": round(seuil_reussite, 2),
        "coefficient_matiere": round(coefficient_matiere, 4),
        "annee_scolaire": configuration.annee_scolaire if configuration else None,
        "poids_total": round(poids_total, 2),
        "nb_notes": len(evaluations),
        "evaluations": evaluations,
        "appreciation_generale": (appreciation or "").strip(),
        "presences": presences,
        "nb_pointages": sum(presences.values()),
        "nb_seances": len(seances),
        "date_publication": publie_le.isoformat(timespec="minutes"),
    }


def lire_snapshot_bulletin(contenu: str | None) -> dict[str, Any] | None:
    """Lit un snapshot JSON sans faire confiance à son contenu."""
    import json

    try:
        donnees = json.loads(contenu or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(donnees, dict) or donnees.get("version") != 1:
        return None
    if not isinstance(donnees.get("evaluations"), list):
        return None
    return donnees


def _texte_paragraphe(valeur: Any) -> str:
    texte = escape(str(valeur or "—"))
    return texte.replace("\n", "<br/>")


def generer_pdf_bulletin(snapshot: dict[str, Any]) -> bytes:
    """Génère le PDF d'un snapshot publié, sans relire les notes modifiables."""
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("evaluations"), list):
        raise ValueError("Le contenu du bulletin est invalide.")

    sortie = BytesIO()
    document = SimpleDocTemplate(
        sortie,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Bulletin scolaire - {snapshot.get('eleve', 'Élève')}",
        author="MITARIDALA",
        subject=f"Bulletin {snapshot.get('periode', '')}",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="BulletinSubTitle",
        parent=styles["Heading2"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#334155"),
        spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        name="BulletinSmall",
        parent=styles["BodyText"],
        fontSize=8,
        leading=11,
    ))
    styles.add(ParagraphStyle(
        name="BulletinNote",
        parent=styles["BodyText"],
        fontSize=9,
        leading=13,
    ))

    story = [
        Paragraph("MITARIDALA", styles["Title"]),
        Paragraph("BULLETIN SCOLAIRE OFFICIEL", styles["BulletinSubTitle"]),
        Spacer(1, 4 * mm),
    ]

    identite = [
        [Paragraph("<b>Élève</b>", styles["BodyText"]), Paragraph(_texte_paragraphe(snapshot.get("eleve")), styles["BodyText"])],
        [Paragraph("<b>Classe / niveau</b>", styles["BodyText"]), Paragraph(_texte_paragraphe(snapshot.get("niveau")), styles["BodyText"])],
        [Paragraph("<b>Matière</b>", styles["BodyText"]), Paragraph(_texte_paragraphe(snapshot.get("matiere")), styles["BodyText"])],
        [Paragraph("<b>Cours</b>", styles["BodyText"]), Paragraph(_texte_paragraphe(snapshot.get("cours")), styles["BodyText"])],
        [Paragraph("<b>Période</b>", styles["BodyText"]), Paragraph(_texte_paragraphe(snapshot.get("periode")), styles["BodyText"])],
        [Paragraph("<b>Année scolaire</b>", styles["BodyText"]), Paragraph(_texte_paragraphe(snapshot.get("annee_scolaire")), styles["BodyText"])],
        [Paragraph("<b>Enseignant</b>", styles["BodyText"]), Paragraph(_texte_paragraphe(snapshot.get("professeur")), styles["BodyText"])],
    ]
    table_identite = Table(identite, colWidths=[38 * mm, 130 * mm], hAlign="LEFT")
    table_identite.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef2f7")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([table_identite, Spacer(1, 6 * mm)])

    moyenne = float(snapshot.get("moyenne") or 0)
    story.append(Paragraph(
        f"<b>Moyenne de la période : {moyenne:.2f} / {float(snapshot.get('moyenne_sur') or 20):g}</b> "
        f"({int(snapshot.get('nb_notes') or 0)} évaluation(s) corrigée(s))",
        styles["Heading2"],
    ))
    story.append(Spacer(1, 2 * mm))

    lignes = [[
        Paragraph("<b>Évaluation</b>", styles["BulletinSmall"]),
        Paragraph("<b>Note</b>", styles["BulletinSmall"]),
        Paragraph("<b>Barème</b>", styles["BulletinSmall"]),
        Paragraph("<b>Coeff.</b>", styles["BulletinSmall"]),
        Paragraph(f"<b>/{float(snapshot.get('moyenne_sur') or 20):g}</b>", styles["BulletinSmall"]),
    ]]
    for evaluation in snapshot["evaluations"]:
        lignes.append([
            Paragraph(_texte_paragraphe(evaluation.get("evaluation")), styles["BulletinSmall"]),
            f"{float(evaluation.get('note') or 0):.2f}",
            f"{float(evaluation.get('bareme') or 0):.2f}",
            f"{float(evaluation.get('coefficient') or 1):.2f}",
            f"{float(evaluation.get('note_sur_echelle', evaluation.get('note_sur_20')) or 0):.2f}",
        ])
    table_notes = Table(
        lignes,
        colWidths=[82 * mm, 22 * mm, 22 * mm, 20 * mm, 22 * mm],
        repeatRows=1,
        hAlign="LEFT",
    )
    table_notes.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([table_notes, Spacer(1, 6 * mm)])

    story.append(Paragraph("Appréciation de l'enseignant", styles["Heading3"]))
    appreciation = _texte_paragraphe(snapshot.get("appreciation_generale"))
    story.append(Paragraph(appreciation, styles["BulletinNote"]))
    story.append(Spacer(1, 5 * mm))

    presences = snapshot.get("presences") or {}
    story.append(Paragraph("Assiduité — cumul des séances du cours", styles["Heading3"]))
    presence_data = [[
        "Séances", "Pointages", "Présent", "Absent", "Retard", "Excusé",
    ], [
        str(int(snapshot.get("nb_seances") or 0)),
        str(int(snapshot.get("nb_pointages") or 0)),
        str(int(presences.get("present") or 0)),
        str(int(presences.get("absent") or 0)),
        str(int(presences.get("retard") or 0)),
        str(int(presences.get("excuse") or 0)),
    ]]
    table_presence = Table(presence_data, colWidths=[27 * mm] * 6, hAlign="LEFT")
    table_presence.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([table_presence, Spacer(1, 9 * mm)])
    story.append(Paragraph(
        f"Publié le {_texte_paragraphe(snapshot.get('date_publication'))}. "
        "Document généré depuis le bulletin validé dans MITARIDALA.",
        styles["BulletinSmall"],
    ))

    document.build(story)
    return sortie.getvalue()



def calculer_moyenne_generale(
    snapshots: list[dict[str, Any]],
    periode: str,
    annee_scolaire: str | None = None,
) -> float:
    """Calcule la moyenne générale sur 20 avec coefficients matière.

    Les anciens snapshots sans coefficient ou barème utilisent les valeurs
    historiques (coefficient 1, moyenne sur 20).
    """
    periode_normalisee = normaliser_periode(periode)
    uniques: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        if not isinstance(snapshot, dict) or snapshot.get("version") != 1:
            continue
        if not isinstance(snapshot.get("evaluations"), list):
            continue
        if normaliser_periode(str(snapshot.get("periode") or "")).casefold() != periode_normalisee.casefold():
            continue
        if annee_scolaire is not None and str(snapshot.get("annee_scolaire") or "") != annee_scolaire:
            continue
        cle = str(snapshot.get("cours_id") or snapshot.get("cours") or snapshot.get("matiere") or "").casefold()
        uniques.setdefault(cle, snapshot)

    total_pondere = 0.0
    poids_total = 0.0
    for snapshot in uniques.values():
        moyenne = float(snapshot.get("moyenne") or 0)
        bareme = max(float(snapshot.get("moyenne_sur") or 20), 0.01)
        coefficient = max(float(snapshot.get("coefficient_matiere") or 1), 0.01)
        total_pondere += (moyenne / bareme * 20) * coefficient
        poids_total += coefficient
    return round(total_pondere / poids_total, 2) if poids_total else 0.0


def generer_pdf_bulletin_general(
    snapshots: list[dict[str, Any]],
    periode: str,
    annee_scolaire: str | None = None,
) -> bytes:
    """Génère le bulletin récapitulatif multi-matières d'une période.

    Les moyennes par matière sont ramenées sur 20 puis pondérées par
    les coefficients configurés par l'établissement. Les anciens snapshots
    restent compatibles avec le coefficient neutre 1.
    """
    periode_normalisee = normaliser_periode(periode)
    valides = [
        snapshot for snapshot in snapshots
        if isinstance(snapshot, dict)
        and snapshot.get("version") == 1
        and isinstance(snapshot.get("evaluations"), list)
        and normaliser_periode(str(snapshot.get("periode") or "")).casefold()
            == periode_normalisee.casefold()
        and (
            annee_scolaire is None
            or str(snapshot.get("annee_scolaire") or "") == annee_scolaire
        )
    ]
    if not valides or not periode_normalisee:
        raise ValueError("Aucun bulletin publié pour cette période.")

    eleves = {str(item.get("eleve") or "") for item in valides}
    if len(eleves) != 1:
        raise ValueError("Les bulletins ne concernent pas le même élève.")

    # Il ne peut y avoir qu'un bulletin par cours et par période ; on
    # déduplique néanmoins le snapshot pour résister à des données incohérentes.
    uniques: dict[str, dict[str, Any]] = {}
    for snapshot in valides:
        cle = str(snapshot.get("cours_id") or snapshot.get("cours") or snapshot.get("matiere") or "").casefold()
        uniques.setdefault(cle, snapshot)
    matieres = list(uniques.values())
    if not matieres:
        raise ValueError("Aucun bulletin exploitable.")

    moyenne_generale = calculer_moyenne_generale(
        matieres, periode_normalisee, annee_scolaire
    )
    eleve = next(iter(eleves)) or "Élève"
    sortie = BytesIO()
    document = SimpleDocTemplate(
        sortie,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Bulletin scolaire général - {eleve}",
        author="MITARIDALA",
        subject=f"Bulletin général {periode_normalisee}",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="BulletinGeneralSubTitle",
        parent=styles["Heading2"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#334155"),
        spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        name="BulletinGeneralSmall",
        parent=styles["BodyText"],
        fontSize=8,
        leading=11,
    ))
    styles.add(ParagraphStyle(
        name="BulletinGeneralBody",
        parent=styles["BodyText"],
        fontSize=9,
        leading=13,
    ))

    story = [
        Paragraph("MITARIDALA", styles["Title"]),
        Paragraph("BULLETIN SCOLAIRE — RÉCAPITULATIF GÉNÉRAL", styles["BulletinGeneralSubTitle"]),
        Spacer(1, 3 * mm),
        Paragraph(f"<b>Élève :</b> {_texte_paragraphe(eleve)}", styles["BodyText"]),
        Paragraph(f"<b>Période :</b> {_texte_paragraphe(periode_normalisee)}", styles["BodyText"]),
        *([Paragraph(f"<b>Année scolaire :</b> {_texte_paragraphe(annee_scolaire)}", styles["BodyText"])] if annee_scolaire else []),
        Spacer(1, 4 * mm),
        Paragraph(
            f"<b>Moyenne générale : {moyenne_generale:.2f} / 20</b> "
            f"— {len(matieres)} matière(s) publiée(s)",
            styles["Heading2"],
        ),
        Paragraph(
            "La moyenne générale est ramenée sur 20 et pondérée par les coefficients de matière "
            "configurés par l'établissement. Les évaluations sont pondérées dans chaque matière.",
            styles["BulletinGeneralSmall"],
        ),
        Spacer(1, 4 * mm),
    ]

    lignes = [[
        Paragraph("<b>Matière</b>", styles["BulletinGeneralSmall"]),
        Paragraph("<b>Cours / niveau</b>", styles["BulletinGeneralSmall"]),
        Paragraph("<b>Enseignant</b>", styles["BulletinGeneralSmall"]),
        Paragraph("<b>Moyenne</b>", styles["BulletinGeneralSmall"]),
        Paragraph("<b>Notes</b>", styles["BulletinGeneralSmall"]),
    ]]
    for snapshot in matieres:
        lignes.append([
            Paragraph(_texte_paragraphe(snapshot.get("matiere")), styles["BulletinGeneralSmall"]),
            Paragraph(
                _texte_paragraphe(
                    " · ".join(
                        part for part in [
                            str(snapshot.get("cours") or ""),
                            str(snapshot.get("niveau") or ""),
                        ] if part
                    )
                ),
                styles["BulletinGeneralSmall"],
            ),
            Paragraph(_texte_paragraphe(snapshot.get("professeur")), styles["BulletinGeneralSmall"]),
            f"{(float(snapshot.get('moyenne') or 0) / max(float(snapshot.get('moyenne_sur') or 20), 0.01) * 20):.2f}/20",
            str(int(snapshot.get("nb_notes") or 0)),
        ])
    table = Table(
        lignes,
        colWidths=[33 * mm, 49 * mm, 36 * mm, 27 * mm, 17 * mm],
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("ALIGN", (3, 1), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([table, Spacer(1, 5 * mm)])

    for snapshot in matieres:
        titre = " · ".join(
            part for part in [
                str(snapshot.get("matiere") or "Matière"),
                str(snapshot.get("cours") or ""),
            ] if part
        )
        story.append(Paragraph(_texte_paragraphe(titre), styles["Heading3"]))
        appreciation = snapshot.get("appreciation_generale") or "Aucune appréciation générale."
        story.append(Paragraph(_texte_paragraphe(appreciation), styles["BulletinGeneralBody"]))
        for evaluation in snapshot.get("evaluations", []):
            if not isinstance(evaluation, dict):
                continue
            detail = (
                f"{_texte_paragraphe(evaluation.get('evaluation'))} — "
                f"{float(evaluation.get('note') or 0):.2f}/"
                f"{float(evaluation.get('bareme') or 0):.2f} "
                f"({float(evaluation.get('note_sur_20') or 0):.2f}/20)"
            )
            story.append(Paragraph(detail, styles["BulletinGeneralSmall"]))
        story.append(Spacer(1, 2 * mm))

    presence_total = {statut: 0 for statut in _STATUTS_PRESENCE}
    seances_total = 0
    pointages_total = 0
    for snapshot in matieres:
        seances_total += int(snapshot.get("nb_seances") or 0)
        pointages_total += int(snapshot.get("nb_pointages") or 0)
        presence = snapshot.get("presences") or {}
        for statut in _STATUTS_PRESENCE:
            presence_total[statut] += int(presence.get(statut) or 0)

    story.extend([
        Spacer(1, 4 * mm),
        Paragraph("Assiduité — cumul des séances des cours publiés", styles["Heading3"]),
        Paragraph(
            f"Séances : {seances_total} · Pointages : {pointages_total} · "
            f"Présences : {presence_total['present']} · "
            f"Absences : {presence_total['absent']} · "
            f"Retards : {presence_total['retard']} · "
            f"Excusées : {presence_total['excuse']}",
            styles["BulletinGeneralSmall"],
        ),
        Spacer(1, 6 * mm),
        Paragraph(
            "Ce récapitulatif compile les bulletins publiés dans MITARIDALA. "
            "Il ne contient aucune matière dont le bulletin n'a pas été publié.",
            styles["BulletinGeneralSmall"],
        ),
    ])
    document.build(story)
    return sortie.getvalue()
