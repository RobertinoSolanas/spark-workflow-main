import alembic.config


def run_alembic_upgrade() -> None:
    """
    Run Alembic migrations to ensure the database schema is up to date.
    This is called at application startup to apply any pending migrations.
    Raises a RuntimeError if the migration fails.
    """
    alembic_args = [
        "--raiseerr",
        "upgrade",
        "head",
    ]
    alembic.config.main(argv=alembic_args)


def run_alembic_downgrade() -> None:
    """
    Run Alembic downgrade migrations.
    Raises a RuntimeError if the migration fails.
    """
    alembic_args = [
        "--raiseerr",
        "downgrade",
        "base",
    ]
    alembic.config.main(argv=alembic_args)
