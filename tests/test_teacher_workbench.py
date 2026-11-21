import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import Environment, FileSystemLoader

from app.models import RoleUtilisateur
from app.routers.suivi_academique_router import (
    MAX_POINTAGES_LOT,
    _peut_gerer,
    normaliser_pointages_lot,
)

ROOT = Path(__file__).resolve().parents[1]


def test_pointages_lot_normalise_statuts_et_justificatifs():
    lignes = normaliser_pointages_lot(json.dumps([
        {"utilisateur_id": "12", "statut": "present", "justificatif": "  "},
        {"utilisateur_id": 15, "statut": "absent", "justificatif": "Maladie"},
    ]))
    assert lignes == [
        {"utilisateur_id": 12, "statut": "present", "justificatif": None},
        {"utilisateur_id": 15, "statut": "absent", "justificatif": "Maladie"},
    ]


@pytest.mark.parametrize("payload", [
    "not-json",
    "{}",
    "[]",
    json.dumps([{"utilisateur_id": 0, "statut": "present"}]),
    json.dumps([{"utilisateur_id": 1, "statut": "admin"}]),
    json.dumps([
        {"utilisateur_id": 1, "statut": "present"},
        {"utilisateur_id": 1, "statut": "absent"},
    ]),
    json.dumps([{"utilisateur_id": True, "statut": "present"}]),
    json.dumps([{"utilisateur_id": 12.5, "statut": "present"}]),
    json.dumps([{"utilisateur_id": 1, "statut": "present", "justificatif": 123}]),
])
def test_pointages_lot_refuse_donnees_invalides(payload):
    with pytest.raises(ValueError):
        normaliser_pointages_lot(payload)


def test_pointages_lot_est_borne_a_cinq_cents_lignes():
    payload = json.dumps([
        {"utilisateur_id": index + 1, "statut": "present"}
        for index in range(MAX_POINTAGES_LOT + 1)
    ])
    with pytest.raises(ValueError):
        normaliser_pointages_lot(payload)


def test_gestion_classe_exige_un_professeur_approuve_ou_un_admin():
    cours = SimpleNamespace(professeur_id=42)
    professeur_approuve = SimpleNamespace(
        id=42,
        role=RoleUtilisateur.PROFESSEUR,
        statut_verification_enseignant="approuve",
    )
    professeur_non_verifie = SimpleNamespace(
        id=42,
        role=RoleUtilisateur.PROFESSEUR,
        statut_verification_enseignant="en_attente",
    )
    compte_revoque = SimpleNamespace(
        id=42,
        role=RoleUtilisateur.ETUDIANT,
        statut_verification_enseignant="approuve",
    )
    admin = SimpleNamespace(id=99, role=RoleUtilisateur.ADMIN)

    assert _peut_gerer(cours, professeur_approuve)
    assert _peut_gerer(cours, admin)
    assert not _peut_gerer(cours, professeur_non_verifie)
    assert not _peut_gerer(cours, compte_revoque)


def test_templates_registre_et_tableau_enseignant_se_compilent():
    env = Environment(loader=FileSystemLoader(ROOT / "app" / "templates"))
    assert env.get_template("registre_presences.html")
    assert env.get_template("dashboard_enseignant.html")


def test_registre_presence_utilise_un_enregistrement_groupe_avec_csrf():
    source = (ROOT / "app" / "templates" / "registre_presences.html").read_text(encoding="utf-8")
    script = (ROOT / "app" / "static" / "registre-presences.js").read_text(encoding="utf-8")
    route = (ROOT / "app" / "routers" / "suivi_academique_router.py").read_text(encoding="utf-8")

    assert 'action="/classe/seances/{{ seance.id }}/registre-presences/lot"' in source
    assert 'name="_csrf"' in source
    assert "data-presence-all-present" in source
    assert "data-presence-payload" in source
    assert "JSON.stringify(lignes)" in script
    assert 'Depends(verifier_csrf)' in route
    assert "InscriptionCours.utilisateur_id.in_(identifiants)" in route
    assert "MAX_POINTAGES_LOT = 500" in route



def test_tableau_de_bord_compte_aussi_les_corrections_inachevees():
    source = (ROOT / "app" / "routers" / "dashboard_router.py").read_text(encoding="utf-8")
    assert "RenduDevoir.note.is_(None) | RenduDevoir.date_correction.is_(None)" in source

def test_tableau_enseignant_affiche_les_actions_reelles_a_traiter():
    source = (ROOT / "app" / "templates" / "dashboard_enseignant.html").read_text(encoding="utf-8")
    assert "actions_a_traiter.corrections" in source
    assert "actions_a_traiter.pointages" in source
    assert "/registre-presences" in source
