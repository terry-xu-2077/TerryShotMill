"""Keep deleted source identities for downstream missing-reference warnings."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_names = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
_source_fk = "fk_generation_context_links_source_task_id_generation_tasks"


def upgrade():
    with op.batch_alter_table("generation_context_links", naming_convention=_names) as batch:
        batch.drop_constraint(_source_fk, type_="foreignkey")
        batch.add_column(sa.Column("source_deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("source_task_title", sa.String(240), nullable=True))


def downgrade():
    # Old schema cannot represent a missing source. Refuse lossy downgrade.
    count = op.get_bind().scalar(sa.text(
        "SELECT COUNT(*) FROM generation_context_links WHERE source_task_id NOT IN "
        "(SELECT id FROM generation_tasks)"
    ))
    if count:
        raise RuntimeError("Cannot downgrade while missing context references exist")
    with op.batch_alter_table("generation_context_links", naming_convention=_names) as batch:
        batch.drop_column("source_task_title")
        batch.drop_column("source_deleted_at")
        batch.create_foreign_key(
            _source_fk, "generation_tasks", ["source_task_id"], ["id"], ondelete="CASCADE"
        )
