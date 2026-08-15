"""
Verifie la migration e1a4c9d2b7f5 (referentiel academique national) :
- applicable proprement par-dessus des donnees reelles preexistantes
  (Faculte/Filiere/Utilisateur/CercleEtude/MembreCercle, comme en prod) ;
- backfill correct (Universite de Toamasina, ProgrammeUniversitaire par
  filiere, role CREATEUR/MEMBRE sur MembreCercle) ;
- aucune donnee inventee : mention_id, universite_id (utilisateur),
  niveau restent NULL apres migration (rien devine a la place de Jake) ;
- reversible (downgrade restaure l'etat d'origine).

Ce test manipule directement des fichiers SQLite temporaires et invoque
Alembic par sous-processus (isole du process courant, pour eviter tout
conflit d'import entre le paquet 'alembic' installe et le dossier local
'alembic/' du projet — voir le commentaire dans _executer_alembic).

Lancer avec :
    python -m unittest tests.test_migration_referentiel_academique -v
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
    """Invoque `alembic {commande} {cible}` dans un sous-processus avec
    cwd hors du repo : lance depuis /tmp evite que le dossier local
    'alembic/' (script_location) ne masque le paquet pip 'alembic' au
    moment de l'import (sys.path[0] = '' sinon)."""
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


class TestMigrationReferentielAcademique(unittest.TestCase):

    def setUp(self):
        self.fichier_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.fichier_db.close()
        self.chemin_db = self.fichier_db.name

        # Etat AVANT ma migration (= etat actuel de prod)
        _executer_alembic("upgrade", "6a1c8e4b7f30", self.chemin_db)

        # Donnees reelles de test, ecrites en SQL brut pour coller
        # exactement a l'ancien schema (aucune des nouvelles colonnes
        # n'existe encore a ce stade).
        conn = sqlite3.connect(self.chemin_db)
        cur = conn.cursor()
        cur.execute("INSERT INTO faculte (nom) VALUES ('DEGMIA')")
        self.fac_id = cur.lastrowid
        cur.execute("INSERT INTO filiere (nom, faculte_id) VALUES ('Gestion', ?)", (self.fac_id,))
        self.filiere_id = cur.lastrowid
        cur.execute(
            "INSERT INTO utilisateur (nom, telephone, mot_de_passe_hash, role, filiere_id, date_creation, banni, totp_active) "
            "VALUES ('Jake', '0340000001', 'x', 'ETUDIANT', ?, '2026-01-01T00:00:00', 0, 0)",
            (self.filiere_id,),
        )
        self.jake_id = cur.lastrowid
        cur.execute(
            "INSERT INTO utilisateur (nom, telephone, mot_de_passe_hash, role, filiere_id, date_creation, banni, totp_active) "
            "VALUES ('Autre', '0340000002', 'x', 'ETUDIANT', ?, '2026-01-01T00:00:00', 0, 0)",
            (self.filiere_id,),
        )
        self.autre_id = cur.lastrowid
        cur.execute(
            "INSERT INTO cercleetude (nom, createur_id, filiere_id, date_creation) VALUES ('Cercle test', ?, ?, '2026-01-01T00:00:00')",
            (self.jake_id, self.filiere_id),
        )
        self.cercle_id = cur.lastrowid
        cur.execute("INSERT INTO membrecercle (cercle_id, utilisateur_id, date_adhesion) VALUES (?, ?, '2026-01-01T00:00:00')", (self.cercle_id, self.jake_id))
        cur.execute("INSERT INTO membrecercle (cercle_id, utilisateur_id, date_adhesion) VALUES (?, ?, '2026-01-01T00:00:00')", (self.cercle_id, self.autre_id))
        conn.commit()
        conn.close()

    def tearDown(self):
        os.unlink(self.chemin_db)

    def _connexion(self):
        return sqlite3.connect(self.chemin_db)

    def test_migration_s_applique_sans_erreur_sur_donnees_reelles(self):
        _executer_alembic("upgrade", "head", self.chemin_db)  # ne doit pas lever

    def test_universite_toamasina_creee_et_facultes_rattachees(self):
        _executer_alembic("upgrade", "head", self.chemin_db)
        conn = self._connexion()
        cur = conn.cursor()
        cur.execute("SELECT id, nom FROM universite")
        universites = cur.fetchall()
        self.assertEqual(len(universites), 1)
        self.assertEqual(universites[0][1], "Universite de Toamasina")

        cur.execute("SELECT universite_id FROM faculte WHERE id = ?", (self.fac_id,))
        self.assertEqual(cur.fetchone()[0], universites[0][0])
        conn.close()

    def test_programme_universitaire_backfille_pour_chaque_filiere(self):
        _executer_alembic("upgrade", "head", self.chemin_db)
        conn = self._connexion()
        cur = conn.cursor()
        cur.execute("SELECT universite_id, filiere_id FROM programmeuniversitaire WHERE filiere_id = ?", (self.filiere_id,))
        lignes = cur.fetchall()
        self.assertEqual(len(lignes), 1, "Une ligne ProgrammeUniversitaire par filiere existante")
        conn.close()

    def test_role_membre_cercle_backfille_correctement(self):
        _executer_alembic("upgrade", "head", self.chemin_db)
        conn = self._connexion()
        cur = conn.cursor()
        cur.execute("SELECT utilisateur_id, role FROM membrecercle WHERE cercle_id = ?", (self.cercle_id,))
        roles = dict(cur.fetchall())
        self.assertEqual(roles[self.jake_id], "CREATEUR", "Le createur du cercle doit avoir role=CREATEUR")
        self.assertEqual(roles[self.autre_id], "MEMBRE")
        conn.close()

    def test_rien_n_est_invente_pour_mention_universite_niveau(self):
        """Regle explicite du brief (§44) : ne jamais deviner un
        classement. mention_id, universite_id (utilisateur) et niveau
        doivent rester NULL apres la migration — a completer plus tard
        via l'admin, jamais auto-devine."""
        _executer_alembic("upgrade", "head", self.chemin_db)
        conn = self._connexion()
        cur = conn.cursor()
        cur.execute("SELECT mention_id FROM filiere WHERE id = ?", (self.filiere_id,))
        self.assertIsNone(cur.fetchone()[0])
        cur.execute("SELECT universite_id, niveau FROM utilisateur WHERE id = ?", (self.jake_id,))
        universite_id, niveau = cur.fetchone()
        self.assertIsNone(universite_id)
        self.assertIsNone(niveau)
        conn.close()

    def test_cercle_existant_devient_actif_par_defaut(self):
        _executer_alembic("upgrade", "head", self.chemin_db)
        conn = self._connexion()
        cur = conn.cursor()
        cur.execute("SELECT statut, niveau FROM cercleetude WHERE id = ?", (self.cercle_id,))
        statut, niveau = cur.fetchone()
        self.assertEqual(statut, "ACTIF")
        self.assertIsNone(niveau)
        conn.close()

    def test_downgrade_restaure_exactement_l_etat_d_origine(self):
        _executer_alembic("upgrade", "head", self.chemin_db)
        _executer_alembic("downgrade", "6a1c8e4b7f30", self.chemin_db)
        conn = self._connexion()
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {t[0] for t in cur.fetchall()}
        self.assertNotIn("universite", tables)
        self.assertNotIn("mention", tables)
        self.assertNotIn("programmeuniversitaire", tables)
        self.assertNotIn("demandecreationcercle", tables)
        self.assertNotIn("demandechangementfiliere", tables)

        cur.execute("SELECT id, nom FROM faculte WHERE id = ?", (self.fac_id,))
        self.assertEqual(cur.fetchone(), (self.fac_id, "DEGMIA"))
        conn.close()


if __name__ == "__main__":
    unittest.main()
