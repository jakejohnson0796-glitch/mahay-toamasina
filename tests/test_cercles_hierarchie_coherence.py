"""Tests for academic-circle consistency and the sidebar language preference."""

from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from app.models import (
    CercleEtude,
    Faculte,
    Filiere,
    Mention,
    ProgrammeUniversitaire,
    RoleUtilisateur,
    Universite,
    Utilisateur,
)
from app.referentiel_academique import type_cercle
from app.routers.academique_router import lister_parcours_nationaux


ROOT = Path(__file__).resolve().parents[1]


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _student(session: Session) -> Utilisateur:
    user = Utilisateur(
        nom="Etudiant test",
        telephone="0347000001",
        mot_de_passe_hash="test",
        role=RoleUtilisateur.ETUDIANT,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _offer(session: Session, university_name: str, faculty_name: str, mention: Mention,
           pathway_name: str, level: str | None):
    university = Universite(nom=university_name, est_active=True)
    session.add(university)
    session.commit()
    session.refresh(university)

    faculty = Faculte(nom=faculty_name, universite_id=university.id)
    session.add(faculty)
    session.commit()
    session.refresh(faculty)

    pathway = Filiere(
        nom=pathway_name,
        faculte_id=faculty.id,
        mention_id=mention.id,
        niveau=level,
    )
    session.add(pathway)
    session.commit()
    session.refresh(pathway)

    offer = ProgrammeUniversitaire(
        universite_id=university.id,
        filiere_id=pathway.id,
        est_active=True,
    )
    session.add(offer)
    session.commit()
    return university, faculty, pathway


def test_circle_type_rejects_a_pathway_attached_to_another_mention_or_level():
    engine = _engine()
    with Session(engine) as session:
        user = _student(session)
        mention_ok = Mention(nom="Gestion cohérence")
        mention_wrong = Mention(nom="Droit cohérence")
        session.add(mention_ok)
        session.add(mention_wrong)
        session.commit()
        session.refresh(mention_ok)
        session.refresh(mention_wrong)

        _, _, pathway = _offer(
            session, "Université cohérence", "Faculté cohérence",
            mention_ok, "Finance", "L3",
        )
        valid = CercleEtude(
            nom="Finance L3", createur_id=user.id,
            mention_id=mention_ok.id, filiere_id=pathway.id, niveau="L3",
        )
        wrong_mention = CercleEtude(
            nom="Finance sous mauvaise mention", createur_id=user.id,
            mention_id=mention_wrong.id, filiere_id=pathway.id, niveau="L3",
        )
        wrong_level = CercleEtude(
            nom="Finance mauvais niveau", createur_id=user.id,
            mention_id=mention_ok.id, filiere_id=pathway.id, niveau="M1",
        )
        invalid_level = CercleEtude(
            nom="Finance niveau inconnu", createur_id=user.id,
            mention_id=mention_ok.id, filiere_id=pathway.id, niveau="X9",
        )
        assert type_cercle(valid, session) == "parcours"
        assert type_cercle(wrong_mention, session) == "incomplet"
        assert type_cercle(wrong_level, session) == "incomplet"
        assert type_cercle(invalid_level, session) == "incomplet"
    engine.dispose()


def test_national_pathway_api_prefers_exact_level_over_legacy_generic_row():
    engine = _engine()
    with Session(engine) as session:
        mention = Mention(nom="Gestion cascade test")
        session.add(mention)
        session.commit()
        session.refresh(mention)

        _u1, _f1, generic = _offer(
            session, "Université générique", "Faculté générique",
            mention, "Finance et comptabilité", None,
        )
        _u2, _f2, exact = _offer(
            session, "Université L3", "Faculté L3",
            mention, "Finance et comptabilité", "L3",
        )

        rows = lister_parcours_nationaux(mention.id, "L3", session)
        assert len(rows) == 1
        assert rows[0]["id"] == exact.id
        assert rows[0]["niveau"] == "L3"
        assert rows[0]["id"] != generic.id
        assert lister_parcours_nationaux(mention.id, "NIVEAU_FAUX", session) == []
    engine.dispose()


def test_create_circle_endpoint_rejects_partial_or_mismatched_hierarchy():
    source = (ROOT / "app" / "routers" / "cercles_router.py").read_text(encoding="utf-8")
    assert 'if (mention_id_nettoye or filiere_id_nettoye) and not niveau_nettoye:' in source
    assert 'if niveau_nettoye and not (mention_id_nettoye or filiere_id_nettoye):' in source
    assert 'erreur=mention_parcours_incoherents' in source
    assert 'filiere_canonique_pour_cercle(session, filiere, niveau_nettoye)' in source


def test_circle_cards_use_human_level_names_and_one_consistent_hierarchy_order():
    template = (ROOT / "app" / "templates" / "cercles_list.html").read_text(encoding="utf-8")
    assert 'class="carte-claire-avatar carte-claire-avatar-couleur-' in template
    assert 'class="carte-claire-avatar" aria-hidden="true" class=' not in template
    assert '{{ libelles_niveaux.get(info.cercle.niveau, info.cercle.niveau) }}' in template
    path_card = template.split('{% if info.type_cercle == "parcours" %}', 1)[1]
    assert path_card.index('libelles_niveaux.get(info.cercle.niveau') < path_card.index('{{ info.filiere.nom }}')
    assert 'Cercle de parcours' in template
    assert 'Référentiel à vérifier : mention, niveau ou parcours incohérent' in template


def test_language_selector_is_in_sidebar_preferences_not_above_primary_navigation():
    base = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
    css = (ROOT / "app" / "static" / "sidebar.css").read_text(encoding="utf-8")
    assert base.count('id="select-langue"') == 1
    assert 'aria-label="Préférences de langue"' in base
    selector = base.index('id="select-langue"')
    sidebar_end = base.index("</aside>", selector)
    assert selector < sidebar_end
    assert base.rfind("</nav>", 0, selector) > base.index('<aside class="tb-sidebar"')
    assert ".tb-sidebar-langue-icone" in css
    assert "body.sidebar-compact .tb-sidebar-langue" in css
    assert css.count("{") == css.count("}")
