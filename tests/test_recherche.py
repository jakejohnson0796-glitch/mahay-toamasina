import unittest

from app.recherche import racines_francaises, termes_recherche
from app.texte_normalise import normaliser


class TestRechercheNormalisee(unittest.TestCase):

    def test_normalisation_supprime_accents_et_casse(self):
        self.assertEqual(normaliser("RéVISION Économique"), "revision economique")

    def test_termes_recherche_dedoublonne_et_ignore_mots_vides(self):
        self.assertEqual(
            termes_recherche("de Finance et finance"),
            ["finance"],
        )

    def test_stemming_francais_reconnait_une_flexion(self):
        variantes = racines_francaises("révisions")
        self.assertIn("revisions", variantes)
        self.assertTrue(any(v.startswith("revis") for v in variantes))

