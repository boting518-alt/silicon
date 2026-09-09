import os
from alembic import context
from silicon.shared.db import make_engine


def run_migrations():
    url = os.environ["MIGRATION_DATABASE_URL"]
    if context.is_offline_mode():
        context.configure(url=url, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = make_engine(url)
        with engine.connect() as connection:
            context.configure(connection=connection)
            with context.begin_transaction():
                context.run_migrations()
        engine.dispose()


run_migrations()
