"""
Smoke test PostgreSQL du référentiel académique Toamasina.

Ce test vérifie le chemin de production (PostgreSQL + Alembic + startup
FastAPI + import de la source issue du classeur fourni) sur une base neuve,
puis vérifie l'idempotence et une recherche HTTP réelle dans /cercles.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import unicodedata

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select, func

from app.main import app
from app.models import (
    CercleEtude,
    Domaine,
    Faculte,
    Filiere,
    Mention,
    ProgrammeUniversitaire,
    Universite,
    Utilisateur,
)
from scripts.import_academic_data import importer


SOURCE = Path(__file__).resolve().parent.parent / "mahay_toamasina_referentiel_source.json"
SOURCE_SHA256 = "fefcd0e5b0886ec181f74d568378afca87c7f1fd54e0b1a30790b249d89ca2ed"

FACULTES_SOURCE_VERS_BASE = {
    "faculte deg": "droit, economie, gestion, mathematiques et informatique (degmia)",
    "faculte des sciences et technologie": "sciences et technologies",
    "ecole normale superieure": "ecole normale superieure (ens)",
    "faculte des lettres et sciences humaines": "lettres et sciences humaines",
}


def _normaliser(texte: str | None) -> str:
    if not texte:
        return ""
    texte = texte.strip().replace("\u2019", "'")
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texte).lower()


def _source() -> dict:
    assert SOURCE.exists(), f"Source du référentiel absente du dépôt : {SOURCE}"
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    assert payload["sha256"] == SOURCE_SHA256
    assert _normaliser(payload["universite"]) == "universite de toamasina"
    assert payload["hierarchie"] == ["Université", "Composante", "Domaine", "Mention", "Niveau", "Parcours"]
    assert len(payload["formations"]) == 111
    assert {ligne["domaine"] for ligne in payload["formations"]} == {
        "Droit et sciences politiques",
        "Sciences économiques",
        "Sciences de gestion",
        "Sciences et technologie",
        "Sciences de l'éducation et didactique",
        "Lettres et sciences humaines",
    }
    assert len({ligne["mention"] for ligne in payload["formations"]}) == 21
    return payload


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith(("postgresql://", "postgresql+psycopg2://")),
    reason="Smoke test réservé à PostgreSQL",
)
def test_postgres_demarrage_import_referentiel_idempotence_et_recherche():
    payload = _source()

    # Le TestClient déclenche réellement le startup FastAPI :
    # Alembic, import de la source Toamasina exacte, seed et provisionnement.
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        cercles_page = client.get("/cercles")
        assert cercles_page.status_code == 200

    from app.database import engine

    with Session(engine) as session:
        universites = {u.nom for u in session.exec(select(Universite)).all()}
        domaines = {d.nom for d in session.exec(select(Domaine)).all()}
        mentions = session.exec(select(Mention)).all()

        assert any(_normaliser(nom) == "universite de toamasina" for nom in universites)

        domaines_source = {ligne["domaine"] for ligne in payload["formations"]}
        assert domaines_source.issubset(domaines)

        mentions_par_nom: dict[str, list[Mention]] = {}
        for mention in mentions:
            mentions_par_nom.setdefault(_normaliser(mention.nom), []).append(mention)

        for nom in {ligne["mention"] for ligne in payload["formations"]}:
            variantes = mentions_par_nom.get(_normaliser(nom), [])
            assert variantes, f"Mention source absente de la base : {nom}"
            assert any(mention.domaine_id is not None for mention in variantes), (
                f"Mention source sans Domaine après synchronisation : {nom}"
            )

        uto = next(
            u for u in session.exec(select(Universite)).all()
            if _normaliser(u.nom) == "universite de toamasina"
        )

        facs = {
            _normaliser(f.nom): f
            for f in session.exec(select(Faculte).where(Faculte.universite_id == uto.id)).all()
        }
        filieres = session.exec(
            select(Filiere).where(
                Filiere.faculte_id.in_([f.id for f in facs.values()])
            )
        ).all()
        programmes = session.exec(
            select(ProgrammeUniversitaire).where(
                ProgrammeUniversitaire.universite_id == uto.id,
                ProgrammeUniversitaire.est_active.is_(True),
            )
        ).all()

        # Le référentiel exact porte le niveau au niveau du triplet
        # Mention + Niveau + Parcours ; le Tronc commun reste volontairement
        # représenté sans Filiere dans le modèle métier.
        attendues = [
            ligne for ligne in payload["formations"]
            if _normaliser(ligne["type"]) != _normaliser("Tronc commun")
        ]

        mention_ids_par_nom = {
            cle: {mention.id for mention in variantes}
            for cle, variantes in mentions_par_nom.items()
        }
        fac_source_nom_par_id = {}
        for fac in facs.values():
            nom_base = _normaliser(fac.nom)
            fac_source_nom_par_id[fac.id] = next(
                (
                    nom_source for nom_source, nom_base_attendu in FACULTES_SOURCE_VERS_BASE.items()
                    if nom_base == nom_base_attendu
                ),
                nom_base,
            )
        filiere_keys = {
            (
                fil.mention_id,
                _normaliser(fil.niveau),
                _normaliser(fil.nom),
                fac_source_nom_par_id.get(fil.faculte_id, ""),
            )
            for fil in filieres
        }

        expected_keys = set()
        for ligne in attendues:
            mention_ids = mention_ids_par_nom.get(_normaliser(ligne["mention"]), set())
            assert mention_ids, f"Mention inconnue pour {ligne['mention']}"
            fac_key = _normaliser(ligne["composante"])
            key_found = {
                (mid, _normaliser(ligne["niveau"]), _normaliser(ligne["parcours"]), fac_key)
                for mid in mention_ids
            }
            assert filiere_keys & key_found, (
                "Parcours source absent de Filiere : "
                f"{ligne['mention']} / {ligne['niveau']} / {ligne['parcours']}"
            )
            expected_keys.update(key_found)

        expected_filiere_ids = {
            fil.id for fil in filieres
            if (
                fil.mention_id,
                _normaliser(fil.niveau),
                _normaliser(fil.nom),
                fac_nom_par_id.get(fil.faculte_id, ""),
            ) in expected_keys
        }
        assert expected_filiere_ids
        assert expected_filiere_ids.issubset({p.filiere_id for p in programmes})

        createur = session.exec(select(Utilisateur)).first()
        assert createur is not None, "Aucun utilisateur disponible pour créer le cercle de smoke test"

        cca = next(
            fil for fil in filieres
            if _normaliser(fil.nom) == _normaliser("CCA — Comptabilité, Contrôle, Audit")
            and _normaliser(fil.niveau) == "m1"
        )
        smoke = CercleEtude(
            nom="Smoke PostgreSQL — CCA M1 Toamasina",
            createur_id=createur.id,
            mention_id=cca.mention_id,
            filiere_id=cca.id,
            niveau="M1",
        )
        session.add(smoke)
        session.commit()

        rapport_second_passage = importer(str(SOURCE))
        assert rapport_second_passage.domaines_crees == []
        assert rapport_second_passage.mentions_creees == []
        assert rapport_second_passage.filieres_creees == []
        assert rapport_second_passage.programmes_crees == 0

        nb_domaines = session.exec(select(func.count()).select_from(Domaine)).one()
        nb_mentions = session.exec(select(func.count()).select_from(Mention)).one()

        bucket = session.connection().exec_driver_sql(
            "SELECT public, file_size_limit, allowed_mime_types "
            "FROM storage.buckets WHERE id = 'documents'"
        ).one()
        assert bucket[0] is False
        assert bucket[1] == 20 * 1024 * 1024
        assert "application/pdf" in bucket[2]

    with TestClient(app) as client:
        page = client.get("/cercles", params={"q": "CCA M1"})
        assert page.status_code == 200
        assert "Smoke PostgreSQL — CCA M1 Toamasina" in page.text

    assert nb_domaines >= len(domaines_source)
    assert nb_mentions >= len(mentions_par_nom)
