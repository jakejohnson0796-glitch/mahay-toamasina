"""Validation statique de la chaine Alembic avant une publication.

Le but est de faire echouer la CI avant Render si le graphe de migrations
redevient ambigu ou reference une revision absente.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]


def charger_script_directory() -> ScriptDirectory:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return ScriptDirectory.from_config(config)


def verifier_graphe() -> tuple[str, int]:
    script = charger_script_directory()
    heads = script.get_heads()

    if len(heads) != 1:
        raise RuntimeError(
            "Le graphe Alembic doit avoir exactement une tete. "
            f"Tetes detectees: {heads!r}"
        )

    head = heads[0]
    revisions = list(script.walk_revisions(head=head, base="base"))

    if not revisions:
        raise RuntimeError("Aucune revision Alembic n'a ete trouvee.")

    connus = {revision.revision for revision in revisions}
    for revision in revisions:
        parents = revision.down_revision
        if parents is None:
            parents = ()
        elif isinstance(parents, str):
            parents = (parents,)
        for parent in parents:
            if parent not in connus:
                raise RuntimeError(
                    f"La revision {revision.revision} reference une revision "
                    f"parente introuvable: {parent}"
                )

    return head, len(revisions)


def main() -> int:
    head, total = verifier_graphe()
    print(f"[MIGRATIONS] graphe valide: {total} revision(s), head={head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
