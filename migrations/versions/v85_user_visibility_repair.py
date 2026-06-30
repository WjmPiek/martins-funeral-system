"""Repair legacy user visibility for franchise/admin employee pages

Revision ID: v85_user_visibility
Revises: v84_gdp_standard
Create Date: 2026-06-30
"""
from alembic import op

revision = "v85_user_visibility"
down_revision = "v84_gdp_standard"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.exec_driver_sql("""
        INSERT INTO roles (name, description, is_system_role, created_at)
        SELECT 'Finance Assistant', 'Martins Funerals South Africa finance assistant', TRUE, NOW()
        WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'Finance Assistant')
    """)
    bind.exec_driver_sql("""
        INSERT INTO roles (name, description, is_system_role, created_at)
        SELECT 'Franchise User', 'Franchise owner/user linked to selected franchise data', TRUE, NOW()
        WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'Franchise User')
    """)
    bind.exec_driver_sql("""
        INSERT INTO roles (name, description, is_system_role, created_at)
        SELECT 'Franchise Employee', 'Employee created under a franchise user', TRUE, NOW()
        WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'Franchise Employee')
    """)

    # Make both spellings visible as mother-company finance users if they already exist.
    bind.exec_driver_sql("""
        INSERT INTO user_roles (user_id, role_id)
        SELECT u.id, r.id
        FROM users u
        JOIN roles r ON r.name = 'Finance Assistant'
        WHERE lower(u.email) IN ('lowhann@martinsdirect.com', 'lowhaan@martinsdirect.com')
          AND NOT EXISTS (
              SELECT 1 FROM user_roles ur WHERE ur.user_id = u.id AND ur.role_id = r.id
          )
    """)
    bind.exec_driver_sql("""
        DELETE FROM user_roles ur
        USING users u, roles r
        WHERE ur.user_id = u.id
          AND ur.role_id = r.id
          AND lower(u.email) IN ('lowhann@martinsdirect.com', 'lowhaan@martinsdirect.com')
          AND r.name IN ('Franchise User', 'Franchise Manager', 'Franchise Employee', 'Franchise Agent')
    """)
    bind.exec_driver_sql("""
        UPDATE users SET parent_franchise_user_id = NULL
        WHERE lower(email) IN ('lowhann@martinsdirect.com', 'lowhaan@martinsdirect.com')
    """)

    # If David exists as an unclassified legacy record, make him visible under Franchise Users.
    bind.exec_driver_sql("""
        INSERT INTO user_roles (user_id, role_id)
        SELECT u.id, r.id
        FROM users u
        JOIN roles r ON r.name = 'Franchise User'
        WHERE lower(u.email) = 'david@martinsfunerals.co.za'
          AND NOT EXISTS (SELECT 1 FROM user_roles ur WHERE ur.user_id = u.id)
    """)

    # Legacy employees created by franchise owners must appear under Employees.
    bind.exec_driver_sql("""
        INSERT INTO user_roles (user_id, role_id)
        SELECT employee.id, employee_role.id
        FROM users employee
        JOIN users owner ON owner.id = employee.created_by_user_id
        JOIN user_roles owner_ur ON owner_ur.user_id = owner.id
        JOIN roles owner_role ON owner_role.id = owner_ur.role_id AND owner_role.name = 'Franchise User'
        JOIN roles employee_role ON employee_role.name = 'Franchise Employee'
        WHERE employee.parent_franchise_user_id IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM user_roles ur
              JOIN roles r ON r.id = ur.role_id
              WHERE ur.user_id = employee.id
                AND r.name IN ('Franchise Manager', 'Franchise Employee', 'Franchise Agent')
          )
    """)
    bind.exec_driver_sql("""
        UPDATE users employee
        SET parent_franchise_user_id = employee.created_by_user_id
        FROM users owner
        JOIN user_roles owner_ur ON owner_ur.user_id = owner.id
        JOIN roles owner_role ON owner_role.id = owner_ur.role_id AND owner_role.name = 'Franchise User'
        WHERE employee.created_by_user_id = owner.id
          AND employee.parent_franchise_user_id IS NULL
    """)


def downgrade():
    # Data repair only. Do not remove users or roles on downgrade.
    pass
