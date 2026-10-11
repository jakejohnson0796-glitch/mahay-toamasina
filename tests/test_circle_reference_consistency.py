"""Regression tests for global language preferences and circle-reference consistency."""

import unittest

from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

from app.models import (
    CercleEtude,
    Domaine,
    Faculte,
    Filiere,
    Mention,
    ProgrammeUniversitaire,
    RoleUtilisateur,
    Universite,
    Utilisateur,
)
from app.referentiel_academique import (
    cercle_est_national,
    condition_cercles_disponibles,
    filiere_canonique_pour_cercle,
    profil_correspond_au_cercle,
    type_cercle,
)
from app.routers.academique_router import lister_parcours_nationaux


ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
BASE = ROOT / "app" / "templates" / "base.html"
SIDEBAR_CSS = ROOT / "app" / "static" / "sidebar.css"
CIRCLE_TEMPLATE = ROOT / "app" / "templates" / "cercles_list.html"
CIRCLE_JS = ROOT / "app" / "static" / "js" / "cercles-list.js"
CIRCLE_ROUTER = ROOT / "app" / "routers" / "cercles_router.py"


def _engine_sqlite():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine


class TestCircleReferenceConsistency(unittest.TestCase):
    def setUp(self):
        self.engine = _engine_sqlite()
        with Session(self.engine) as session:
            university = Universite(nom="Université Test Cohérence")
            session.add(university)
            session.commit()
            session.refresh(university)
            faculty = Faculte(nom="Composante Test Cohérence", universite_id=university.id)
            session.add(faculty)
            session.commit()
            session.refresh(faculty)
            domain = Domaine(nom="Domaine Test Cohérence")
            session.add(domain)
            session.commit()
            session.refresh(domain)
            mention = Mention(nom="Mention Test Cohérence", domaine_id=domain.id)
            session.add(mention)
            session.commit()
            session.refresh(mention)
            pathway = Filiere(
                nom="Parcours Test Cohérence",
                faculte_id=faculty.id,
                mention_id=mention.id,
                niveau="L3",
            )
            session.add(pathway)
            session.commit()
            session.refresh(pathway)
            session.add(ProgrammeUniversitaire(
                universite_id=university.id, filiere_id=pathway.id, est_active=True
            ))
            creator = Utilisateur(
                nom="Créateur Test",
                telephone="0340007101",
                mot_de_passe_hash="test",
                role=RoleUtilisateur.ETUDIANT,
            )
            student = Utilisateur(
                nom="Étudiant Test",
                telephone="0340007102",
                mot_de_passe_hash="test",
                role=RoleUtilisateur.ETUDIANT,
                universite_id=university.id,
                faculte_id=faculty.id,
                mention_id=mention.id,
                filiere_id=pathway.id,
                niveau="L3",
            )
            session.add(creator)
            session.add(student)
            session.commit()
            session.refresh(creator)
            session.refresh(student)
            self.university_id = university.id
            self.faculty_id = faculty.id
            self.mention_id = mention.id
            self.pathway_id = pathway.id
            self.creator_id = creator.id
            self.student_id = student.id

    def tearDown(self):
        self.engine.dispose()

    def test_legacy_circle_derives_its_mention_from_its_pathway(self):
        with Session(self.engine) as session:
            pathway = session.get(Filiere, self.pathway_id)
            student = session.get(Utilisateur, self.student_id)
            circle = CercleEtude(
                nom="Cercle historique L3",
                createur_id=self.creator_id,
                mention_id=None,
                filiere_id=self.pathway_id,
                niveau="L3",
            )
            session.add(circle)
            session.commit()
            session.refresh(circle)

            self.assertEqual(type_cercle(circle, pathway), "parcours")
            self.assertTrue(cercle_est_national(circle, pathway))
            self.assertTrue(profil_correspond_au_cercle(student, circle, session))
            available = session.exec(
                select(CercleEtude).where(condition_cercles_disponibles(student, session))
            ).all()
            self.assertIn(circle.id, {item.id for item in available})

    def test_legacy_student_pathway_without_level_matches_the_exact_national_level(self):
        with Session(self.engine) as session:
            legacy_pathway = Filiere(
                nom="Parcours Test Cohérence",
                faculte_id=self.faculty_id,
                mention_id=self.mention_id,
                niveau=None,
            )
            session.add(legacy_pathway)
            session.commit()
            session.refresh(legacy_pathway)
            session.add(ProgrammeUniversitaire(
                universite_id=self.university_id,
                filiere_id=legacy_pathway.id,
                est_active=True,
            ))
            student = session.get(Utilisateur, self.student_id)
            student.filiere_id = legacy_pathway.id
            session.add(student)
            circle = CercleEtude(
                nom="Cercle national niveau précis",
                createur_id=self.creator_id,
                mention_id=self.mention_id,
                filiere_id=self.pathway_id,
                niveau="L3",
            )
            session.add(circle)
            session.commit()
            session.refresh(circle)

            self.assertTrue(profil_correspond_au_cercle(student, circle, session))
            available = session.exec(
                select(CercleEtude).where(condition_cercles_disponibles(student, session))
            ).all()
            self.assertIn(circle.id, {item.id for item in available})

    def test_explicitly_conflicting_mention_is_not_a_valid_pathway_circle(self):
        with Session(self.engine) as session:
            other_mention = Mention(nom="Autre Mention Test")
            session.add(other_mention)
            session.commit()
            session.refresh(other_mention)
            pathway = session.get(Filiere, self.pathway_id)
            student = session.get(Utilisateur, self.student_id)
            circle = CercleEtude(
                nom="Cercle contradictoire",
                createur_id=self.creator_id,
                mention_id=other_mention.id,
                filiere_id=self.pathway_id,
                niveau="L3",
            )
            self.assertEqual(type_cercle(circle, pathway), "incomplet")
            self.assertFalse(cercle_est_national(circle, pathway))
            self.assertFalse(profil_correspond_au_cercle(student, circle, session))

    def test_canonical_pathway_prefers_the_requested_explicit_level(self):
        with Session(self.engine) as session:
            # Simulate imported data with the same pathway represented as L2,
            # L3 and an old, undated row. An L3 circle must never pick the L2 row.
            l2 = Filiere(
                nom="Parcours Canonique Test",
                faculte_id=self.faculty_id,
                mention_id=self.mention_id,
                niveau="L2",
            )
            legacy = Filiere(
                nom="Parcours Canonique Test",
                faculte_id=self.faculty_id,
                mention_id=self.mention_id,
                niveau=None,
            )
            l3 = Filiere(
                nom="Parcours Canonique Test",
                faculte_id=self.faculty_id,
                mention_id=self.mention_id,
                niveau="L3",
            )
            session.add(l2)
            session.add(legacy)
            session.add(l3)
            session.commit()
            for pathway in (l2, legacy, l3):
                session.add(ProgrammeUniversitaire(
                    universite_id=self.university_id,
                    filiere_id=pathway.id,
                    est_active=True,
                ))
            session.commit()
            session.refresh(legacy)
            session.refresh(l3)

            chosen = filiere_canonique_pour_cercle(session, legacy, "L3")
            self.assertEqual(chosen.niveau, "L3")
            self.assertEqual(chosen.id, l3.id)

    def test_national_pathway_api_ignores_offer_linked_to_the_wrong_university(self):
        with Session(self.engine) as session:
            other_university = Universite(nom="Université Test Incorrecte")
            session.add(other_university)
            session.commit()
            session.refresh(other_university)
            wrongly_offered = Filiere(
                nom="Parcours lié à la mauvaise université",
                faculte_id=self.faculty_id,
                mention_id=self.mention_id,
                niveau="L2",
            )
            session.add(wrongly_offered)
            session.commit()
            session.refresh(wrongly_offered)
            # The database permits this historical mismatch: the programme says
            # University B while the pathway belongs to a component of A.
            session.add(ProgrammeUniversitaire(
                universite_id=other_university.id,
                filiere_id=wrongly_offered.id,
                est_active=True,
            ))
            session.commit()

            results = lister_parcours_nationaux(self.mention_id, "L2", session)
            self.assertNotIn(
                "Parcours lié à la mauvaise université",
                {item["nom"] for item in results},
            )
            self.assertEqual(lister_parcours_nationaux(self.mention_id, "NIVEAU_INVALIDE", session), [])


class TestLanguageAndCircleUiContracts(unittest.TestCase):
    def test_language_picker_is_in_the_sidebar_preferences_footer(self):
        base = BASE.read_text(encoding="utf-8")
        css = SIDEBAR_CSS.read_text(encoding="utf-8")
        self.assertEqual(base.count('id="select-langue"'), 1)
        self.assertLess(base.index('class="tb-toggle-theme"'), base.index('class="tb-sidebar-langue"'))
        self.assertLess(base.index('class="tb-sidebar-langue"'), base.index("</aside>"))
        self.assertIn("tb-sidebar-langue-globe", base)
        self.assertIn("body.sidebar-compact .tb-sidebar-langue", css)
        self.assertIn("grid-template-columns: 1.15rem auto minmax(0, 1fr)", css)

    def test_circle_cards_use_clear_categories_and_distinct_academic_metadata(self):
        template = CIRCLE_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("Parcours national", template)
        self.assertIn("Tronc commun", template)
        self.assertIn("Groupe libre", template)
        self.assertIn("cercle-parcours-detail", template)
        self.assertIn('class="carte-claire-avatar carte-claire-avatar-couleur-', template)
        self.assertNotIn('aria-hidden="true" class="carte-claire-avatar-couleur-', template)
        self.assertIn('id="creation-info-tronc-commun" hidden', template)
        self.assertNotIn('id="creation-info-tronc-commun" style="display:none;"', template)

    def test_creation_does_not_silently_downgrade_partial_academic_selection(self):
        router = CIRCLE_ROUTER.read_text(encoding="utf-8")
        creation = router.split('def creer_cercle(', 1)[1].split(
            '@router.post("/cercles/{cercle_id}/demander")', 1
        )[0]
        self.assertIn("champs_academiques", creation)
        self.assertIn("erreur=infos_academiques_incompletes", creation)
        self.assertIn("erreur=parcours_mention_incoherents", creation)
        self.assertIn("filiere_canonique_pour_cercle(session, filiere, niveau_nettoye)", creation)

    def test_pathway_loading_failure_is_not_reported_as_a_real_empty_offering(self):
        js = CIRCLE_JS.read_text(encoding="utf-8")
        self.assertIn("if (!response.ok) return null", js)
        self.assertIn("if (!Array.isArray(rows))", js)
        self.assertIn("Chargement impossible — réessayez", js)
        self.assertIn("doit être confirmé pour ton établissement", js)


if __name__ == "__main__":
    unittest.main()
