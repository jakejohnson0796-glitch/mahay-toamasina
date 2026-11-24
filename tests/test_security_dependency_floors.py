from importlib.metadata import version
from packaging.version import Version


def test_runtime_dependencies_meet_security_floors():
    # Floors conservés comme garde-fou lorsque Dependabot met à jour les paquets.
    assert Version(version("fastapi")) >= Version("0.162.7")
    assert Version(version("starlette")) >= Version("0.46.0")
    assert Version(version("jinja2")) >= Version("3.1.5")
    assert Version(version("python-dotenv")) >= Version("1.2.2")
    assert Version(version("Pillow")) >= Version("13.0.0")
    assert Version(version("pdfplumber")) >= Version("0.11.10")
    assert Version(version("pdfminer.six")) >= Version("20260107")
    assert Version(version("pytest")) >= Version("9.0.3")


def test_fastapi_resolves_starlette_as_a_dependency_not_a_direct_pin():
    from pathlib import Path

    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    lignes = [
        ligne.strip()
        for ligne in requirements.splitlines()
        if ligne.strip() and not ligne.lstrip().startswith("#")
    ]
    assert any(ligne.startswith("fastapi==") for ligne in lignes)
    assert not any(ligne.lower().startswith("starlette") for ligne in lignes)
