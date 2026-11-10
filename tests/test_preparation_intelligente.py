from datetime import datetime, timedelta

from app.models import ProgressionNotion
from app.preparation_intelligente import construire_bilans_matieres


def _progression(matiere, niveau, score, questions=5, reussites=2, revision=None):
    return ProgressionNotion(
        utilisateur_id=7,
        matiere=matiere,
        notion=f"Notion {matiere}",
        niveau=niveau,
        nb_questions=questions,
        nb_reussites=reussites,
        nb_erreurs=max(0, questions - reussites),
        score_maitrise=score,
        prochaine_revision_le=revision,
        preuves_apprentissage_json="{}",
    )


def test_matiere_sans_historique_reste_a_evaluer_et_non_faible():
    bilans = construire_bilans_matieres(
        ["Mathématiques", "Français"],
        [],
        niveau="T5",
    )

    assert [bilan["statut"] for bilan in bilans] == ["a_evaluer", "a_evaluer"]
    assert all(bilan["score"] is None for bilan in bilans)
    assert all(bilan["nb_questions"] == 0 for bilan in bilans)
    assert all(bilan["libelle_action"] == "Commencer le diagnostic" for bilan in bilans)


def test_bilan_ne_melange_pas_les_resultats_d_une_ancienne_classe():
    ancienne_classe = _progression("Mathématiques", "4e", 20)
    bilans = construire_bilans_matieres(
        ["Mathématiques"],
        [ancienne_classe],
        niveau="3e",
    )

    assert bilans[0]["statut"] == "a_evaluer"
    assert bilans[0]["score"] is None


def test_bilan_pondere_les_notions_et_signale_les_revisions_echues():
    maintenant = datetime.utcnow()
    progression_a = _progression(
        "Mathématiques", "Terminale", 35, questions=4, reussites=1,
        revision=maintenant - timedelta(hours=1),
    )
    progression_b = _progression(
        "Mathématiques", "Terminale", 65, questions=6, reussites=4,
        revision=maintenant + timedelta(days=2),
    )
    bilans = construire_bilans_matieres(
        ["Mathématiques"],
        [progression_a, progression_b],
        niveau="Terminale",
        maintenant=maintenant,
    )

    bilan = bilans[0]
    assert bilan["nb_questions"] == 10
    assert bilan["nb_notions"] == 2
    assert bilan["nb_a_revoir"] == 2
    assert bilan["score"] == 53
    assert bilan["statut"] == "a_renforcer"
    assert "1 révision arrivée à échéance" in bilan["resume"]


def test_bilan_ignore_les_matieres_dupliquees_sans_creer_de_fausse_progression():
    bilans = construire_bilans_matieres(
        ["Physique", " physique ", "", None, "Chimie"],
        [],
        niveau="Terminale",
    )

    assert [bilan["matiere"] for bilan in bilans] == ["Chimie", "Physique"]
