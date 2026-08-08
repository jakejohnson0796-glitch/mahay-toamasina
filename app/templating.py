"""
Instance Jinja2Templates PARTAGEE par tout le projet, a importer partout
(from ..templating import templates) plutot que d'en creer une par
router comme avant. Necessaire pour que jeton_csrf() (voir csrf.py) soit
disponible dans absolument tous les templates, quel que soit le router
qui les rend — une instance par router aurait exige d'enregistrer le
global separement dans chacune, avec le risque d'en oublier une.
"""
from pathlib import Path

from fastapi.templating import Jinja2Templates

from .csrf import obtenir_jeton_csrf

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["jeton_csrf"] = obtenir_jeton_csrf
