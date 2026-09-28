from pathlib import Path

from alembic import command
from shotmill.persistence.migrations import alembic_config, upgrade_database
from sqlalchemy import create_engine, inspect, text


def test_alembic_builds_empty_database(tmp_path: Path) -> None:
    db = tmp_path / "migration.db"
    url = f"sqlite+pysqlite:///{db.as_posix()}"
    upgrade_database(url)
    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert {
        "projects",
        "assets",
        "generation_tasks",
        "task_asset_bindings",
        "scenes",
        "task_placements",
        "generation_context_links",
        "jobs",
        "results",
        "ai_prompt_revisions",
        "alembic_version",
    } <= tables


def test_transfer_requirements_upgrade_preserves_existing_projects(tmp_path):
    url = f"sqlite+pysqlite:///{(tmp_path / 'upgrade.db').as_posix()}"
    command.upgrade(alembic_config(url), "0014")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO projects
                (id, title, description, use_description_for_ai_prompt, created_at, updated_at)
                VALUES ('old', 'Existing project', '', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """))
        upgrade_database(url)
        with engine.connect() as connection:
            row = connection.execute(text(
                "SELECT title, transfer_requirements FROM projects WHERE id = 'old'"
            )).one()
            assert row == ("Existing project", "[]")
    finally:
        engine.dispose()
