"""
Verifie la migration f2b8e6a1c9d3 (5 universites manquantes) :
- les 6 universites existent au total apres migration ;
- des facultes de meme nom ("Faculte des Sciences") peuvent coexister
  dans des universites differentes (l'ancien index unique global sur
  Faculte.nom aurait empeche ca — c'est le bug corrige par cette
  migration) ;
- tous les utilisateurs existants sont rattaches a l'Universite de
  Toamasina (fait deja vrai avant la migration, pas une supposition).

Lancer avec :
    python -m unittest tests.test_migration_universites_manquantes -v
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _executer_alembic(commande: str, cible: str, chemin_db: str) -> None:
    script = f"""
import os
os.environ["DATABASE_URL"] = "sqlite:///{chemin_db}"
from alembic import command
from alembic.config import Config
config = Config("{REPO}/alembic.ini")
config.set_main_option("script_location", "{REPO}/alembic")
config.config_file_name = None
command.{commande}(config, "{cible}")
"""
    resultat = subprocess.run(
        [sys.executable, "-c", script], cwd=tempfile.gettempdir(),
        capture_output=True, text=True,
    )
    if resultat.returncode != 0:
        raise RuntimeError(f"alembic {commande} {cible} a echoue :\n{resultat.stderr}")


class TestMigrationUniversitesManquantes(unittest.TestCase):

    def setUp(self):
        self.fichier_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.fichier_db.close()
        self.chemin_db = self.fichier_db.name

        # Etat juste avant cette migration (= etat reel de prod au
        # moment ou Jake a signale le probleme).
        _executer_alembic("upgrade", "6a1c8e4b7f30", self.chemin_db)
        conn = sqlite3.connect(self.chemin_db)
        cur = conn.cursor()
        cur.execute("INSERT INTO faculte (nom) VALUES ('DEGMIA')")
        fac_id = cur.lastrowid
        cur.execute("INSERT INTO filiere (nom, faculte_id) VALUES ('Gestion', ?)", (fac_id,))
        cur.execute(
            "INSERT INTO utilisateur (nom, telephone, mot_de_passe_hash, role, date_creation, banni, totp_active) "
            "VALUES ('Jake', '0340000001', 'x', 'ETUDIANT', '2026-01-01T00:00:00', 0, 0)"
        )
        conn.commit()
        conn.close()

        _executer_alembic("upgrade", "e1a4c9d2b7f5", self.chemin_db)

    def tearDown(self):
        os.unlink(self.chemin_db)

    def _connexion(self):
        return sqlite3.connect(self.chemin_db)

    def test_migration_s_applique_sans_erreur(self):
        _executer_alembic("upgrade", "head", self.chemin_db)

    def test_six_universites_existent_apres_migration(self):
        _executer_alembic("upgrade", "head", self.chemin_db)
        conn = self._connexion()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM universite")
        self.assertEqual(cur.fetchone()[0], 6)
        conn.close()

    def test_facultes_de_meme_nom_coexistent_dans_universites_differentes(self):
        """C'est LE bug corrige par cette migration : avant, l'index
        unique global sur faculte.nom aurait rejete une 2e 'Faculte des
        Sciences'."""
        _executer_alembic("upgrade", "head", self.chemin_db)
        conn = self._connexion()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM faculte WHERE nom = 'Faculte des Sciences'")
        nb = cur.fetchone()[0]
        self.assertGreaterEqual(nb, 2, "Faculte des Sciences doit exister dans au moins 2 universites")
        conn.close()

    def test_utilisateurs_existants_rattaches_a_toamasina(self):
        _executer_alembic("upgrade", "head", self.chemin_db)
        conn = self._connexion()
        cur = conn.cursor()
        cur.execute("""
            SELECT u.nom FROM utilisateur ut JOIN universite u ON ut.universite_id = u.id
            WHERE ut.nom = 'Jake'
        """)
        self.assertEqual(cur.fetchone()[0], "Universite de Toamasina")
        conn.close()

    def test_downgrade_restaure_l_etat_d_origine(self):
        _executer_alembic("upgrade", "head", self.chemin_db)
        _executer_alembic("downgrade", "e1a4c9d2b7f5", self.chemin_db)
        conn = self._connexion()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM universite")
        self.assertEqual(cur.fetchone()[0], 1)
        # universite_id de l'utilisateur redevient NULL : ce champ n'est
        # backfille QUE par f2b8e6a1c9d3 (e1a4c9d2b7f5 ajoute la colonne
        # mais la laisse vide, voir sa propre docstring).
        cur.execute("SELECT universite_id FROM utilisateur WHERE nom = 'Jake'")
        self.assertIsNone(cur.fetchone()[0])
        conn.close()


if __name__ == "__main__":
    unittest.main()
