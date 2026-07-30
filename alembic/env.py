import sys
from logging.config import fileConfig
from pathlib import Path

from sqlmodel import SQLModel

from alembic import context

# Permet d'importer le package "app" quand alembic est lance depuis la
# racine du projet (cas normal en dev comme dans le futur build de prod).
sys.path.append(str(Path(__file__).resolve().parents[1]))

# On reutilise le moteur et l'URL deja construits par l'app (meme logique
# SQLite/Postgres, meme lecture de .env via app.config) plutot que de la
# dupliquer ici : une seule source de verite pour la connexion.
from app.database import engine  # noqa: E402

# Importer app.models (meme si le nom n'est pas utilise directement) est
# indispensable : c'est ce qui enregistre toutes les tables sur
# SQLModel.metadata avant qu'Alembic ne compare ce metadata a la base.
from app import models  # noqa: F401,E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = str(engine.url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
