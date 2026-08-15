"""
Verifie le comportement demande pour le "Theme du jour" :

- meme date -> meme theme (deterministe, pas de random par requete) ;
- date suivante -> theme different (au moins visuellement, pour une
  liste de plusieurs themes) ;
- la date simulee ne touche jamais l'horloge reelle du serveur (on
  passe simplement un objet date() different a la fonction, comme
  demande dans le brief : "Ne modifie pas la date systeme reelle").

Lancer avec :
    python -m unittest tests.test_theme_service -v
"""
import unittest
from datetime import date, timedelta

from app.theme_service import THEMES, DATE_REFERENCE, get_theme_du_jour


class TestThemeDuJour(unittest.TestCase):

    def test_meme_date_donne_toujours_le_meme_theme(self):
        jour = date(2026, 8, 15)
        premier_appel = get_theme_du_jour(jour)
        deuxieme_appel = get_theme_du_jour(jour)
        troisieme_appel = get_theme_du_jour(jour)

        self.assertEqual(premier_appel, deuxieme_appel)
        self.assertEqual(premier_appel, troisieme_appel)

    def test_dates_consecutives_changent_de_theme(self):
        dates_testees = [date(2026, 8, 15), date(2026, 8, 16), date(2026, 8, 17), date(2026, 8, 18)]
        themes_obtenus = [get_theme_du_jour(j)["theme"] for j in dates_testees]

        # Chaque jour doit differer du precedent (rotation reelle, pas
        # bloque sur la meme valeur).
        for i in range(1, len(themes_obtenus)):
            self.assertNotEqual(
                themes_obtenus[i], themes_obtenus[i - 1],
                f"Le theme n'a pas change entre {dates_testees[i-1]} et {dates_testees[i]}",
            )

    def test_la_date_affichee_correspond_a_la_date_demandee(self):
        resultat = get_theme_du_jour(date(2026, 8, 15))
        self.assertEqual(resultat["date"], "2026-08-15")
        self.assertEqual(resultat["date_affichee"], "15 aout 2026")

    def test_rotation_complete_puis_recommence(self):
        """Apres avoir parcouru toute la liste, la rotation doit
        recommencer au debut (jour 1 -> A, ..., jour N+1 -> A a nouveau)."""
        premier_jour = DATE_REFERENCE
        theme_jour_1 = get_theme_du_jour(premier_jour)
        theme_apres_rotation_complete = get_theme_du_jour(premier_jour + timedelta(days=len(THEMES)))
        # Seul le contenu du theme doit se repeter ; la date affichee, elle,
        # differe legitimement (21 jours plus tard).
        self.assertEqual(theme_jour_1["theme"], theme_apres_rotation_complete["theme"])
        self.assertEqual(theme_jour_1["amorce"], theme_apres_rotation_complete["amorce"])

    def test_aucun_appel_reseau_aucune_generation_ia(self):
        """Le module ne doit plus importer/dependre de ai_quiz ou d'un
        client Groq — sinon on retombe dans le bug d'origine (panne
        reseau/cle API = theme fige)."""
        import app.theme_service as module
        self.assertNotIn("ai_quiz", dir(module))
        self.assertNotIn("Groq", dir(module))

    def test_filtrage_par_matiere_reste_deterministe(self):
        jour = date(2026, 9, 1)
        premier = get_theme_du_jour(jour, matiere="Economie")
        deuxieme = get_theme_du_jour(jour, matiere="Economie")
        self.assertEqual(premier, deuxieme)

    def test_matiere_inconnue_retombe_sur_la_liste_complete_sans_erreur(self):
        # Une matiere qui ne correspond a aucune categorie ne doit pas
        # faire planter la fonction : elle retombe sur la liste complete.
        resultat = get_theme_du_jour(date(2026, 8, 15), matiere="Zythologie appliquee")
        self.assertIn(resultat["theme"], [t.theme for t in THEMES])

    def test_liste_de_themes_non_vide_et_pertinente(self):
        self.assertGreater(len(THEMES), 1, "Un seul theme = pas de vraie rotation possible.")
        for t in THEMES:
            self.assertTrue(t.theme.strip())
            self.assertTrue(t.amorce.strip())


if __name__ == "__main__":
    unittest.main()
