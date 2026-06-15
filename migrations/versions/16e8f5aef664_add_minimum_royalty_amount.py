"""Add minimum royalty amount

Revision ID: 16e8f5aef664
Revises: ed82d46edd65
Create Date: 2026-06-11 18:58:36.348010

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '16e8f5aef664'
down_revision = 'ed82d46edd65'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('franchises', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'minimum_royalty_amount',
                sa.Numeric(12, 2),
                nullable=False,
                server_default='0'
            )
        )


def downgrade():
    with op.batch_alter_table('franchises', schema=None) as batch_op:
        batch_op.drop_column('minimum_royalty_amount')
