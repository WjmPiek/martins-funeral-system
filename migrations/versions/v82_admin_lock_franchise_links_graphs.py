"""Lock Admin role and refresh franchise user links

Revision ID: v82_admin_fix
Revises: v81_graphs_default_landing
Create Date: 2026-06-30
"""
from alembic import op

revision = "v82_admin_fix"
down_revision = "v81_graphs_default_landing"
branch_labels = None
depends_on = None


def upgrade():
    # Render/PostgreSQL databases may still have alembic_version.version_num as varchar(32).
    # Make it wider before Alembic writes this revision id.
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")

    # Ensure franchise users can manage their own employee/manager/agent accounts.
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.name = 'Franchise User'
          AND p.code IN ('franchise_employees:view', 'franchise_employees:manage')
          AND NOT EXISTS (
            SELECT 1 FROM role_permissions rp
            WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """)

    # Admin is reserved for the protected Martins account only.
    op.execute("""
        DELETE FROM user_roles
        WHERE role_id IN (SELECT id FROM roles WHERE name = 'Admin')
          AND user_id NOT IN (SELECT id FROM users WHERE lower(email) = 'wjm@martinsdirect.com')
    """)
    op.execute("""
        INSERT INTO user_roles (user_id, role_id)
        SELECT u.id, r.id
        FROM users u
        CROSS JOIN roles r
        WHERE lower(u.email) = 'wjm@martinsdirect.com'
          AND r.name = 'Admin'
          AND NOT EXISTS (
            SELECT 1 FROM user_roles ur WHERE ur.user_id = u.id AND ur.role_id = r.id
          )
    """)

    # Finance Manager users must be linked to all active franchises for oversight.
    op.execute("""
        INSERT INTO user_franchises (user_id, franchise_id, is_primary)
        SELECT DISTINCT u.id, f.id, false
        FROM users u
        JOIN user_roles ur ON ur.user_id = u.id
        JOIN roles r ON r.id = ur.role_id AND r.name = 'Finance Manager'
        CROSS JOIN franchises f
        WHERE COALESCE(f.is_performance_active, true) = true
          AND NOT EXISTS (
            SELECT 1 FROM user_franchises uf
            WHERE uf.user_id = u.id AND uf.franchise_id = f.id
          )
    """)


def downgrade():
    # Do not automatically restore removed Admin assignments or finance links.
    pass
