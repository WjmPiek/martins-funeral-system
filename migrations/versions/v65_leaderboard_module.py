"""Add franchise leaderboard and monthly targets

Revision ID: v65_leaderboard_module
Revises: v64_sidebar_permissions_fix
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = "v65_leaderboard_module"
down_revision = "v64_sidebar_permissions_fix"
branch_labels = None
depends_on = None

LEADERBOARD_PERMISSIONS = [
    ("Leaderboard", "view", "leaderboard:view", "Leaderboard - View", 95),
    ("Leaderboard", "manage_targets", "leaderboard:manage_targets", "Leaderboard - Manage Targets", 96),
]


def upgrade():
    op.create_table(
        "franchise_targets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("franchise_id", sa.Integer(), sa.ForeignKey("franchises.id"), nullable=False),
        sa.Column("metric", sa.String(length=80), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("target_value", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("franchise_id", "metric", "year", "month", name="uq_franchise_target_period_metric"),
    )
    op.create_index("ix_franchise_targets_franchise_id", "franchise_targets", ["franchise_id"])
    op.create_index("ix_franchise_targets_metric", "franchise_targets", ["metric"])
    op.create_index("ix_franchise_targets_year", "franchise_targets", ["year"])
    op.create_index("ix_franchise_targets_month", "franchise_targets", ["month"])

    bind = op.get_bind()
    for module, action, code, label, sort_order in LEADERBOARD_PERMISSIONS:
        bind.execute(sa.text("""
            INSERT INTO permissions (module, action, code, label, sort_order)
            SELECT :module, :action, :code, :label, :sort_order
            WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)
        """), {
            "module": module,
            "action": action,
            "code": code,
            "label": label,
            "sort_order": sort_order,
        })

    bind.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.name = 'Admin'
          AND p.code IN ('leaderboard:view', 'leaderboard:manage_targets')
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """))

    bind.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.name IN ('Franchise User', 'Franchise Manager', 'Read Only User', 'Finance Manager', 'Finance Assistant')
          AND p.code = 'leaderboard:view'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """))


def downgrade():
    op.drop_index("ix_franchise_targets_month", table_name="franchise_targets")
    op.drop_index("ix_franchise_targets_year", table_name="franchise_targets")
    op.drop_index("ix_franchise_targets_metric", table_name="franchise_targets")
    op.drop_index("ix_franchise_targets_franchise_id", table_name="franchise_targets")
    op.drop_table("franchise_targets")
