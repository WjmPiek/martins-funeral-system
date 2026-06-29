"""Franchise employee users

Revision ID: v74_franchise_employees
Revises: v73_role_scope
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "v74_franchise_employees"
down_revision = "v73_role_scope"
branch_labels = None
depends_on = None

ACTIONS = ["view", "add", "edit", "delete", "export", "approve", "import", "manage"]
MODULE_ORDER = [
    "Dashboard", "Franchise Settings", "Franchise Details", "Franchise Agreement", "Royalty Scale",
    "Performance", "Heat Map", "Manuals", "Royalties", "Monthly Figures", "Joinings",
    "Funeral Services", "Insurance Claims", "Attendance", "Finance", "Users", "Franchise Employees",
    "User Roles", "Franchise Management", "Imports & Data", "Audit Logs", "System Administration",
]

ROLE_ACCESS = {
    "Franchise Manager": {
        "Franchise Employees": ["view", "add", "edit", "delete", "manage"],
    },
    "Franchise User": {
        "Franchise Employees": ["view", "add", "edit", "delete", "manage"],
    },
    "Franchise Employee": {
        "Dashboard": ["view"],
        "Franchise Settings": ["view"],
        "Franchise Details": ["view", "export"],
        "Franchise Agreement": ["view"],
        "Royalty Scale": ["view"],
        "Performance": ["view"],
        "Royalties": ["view"],
        "Monthly Figures": ["view"],
        "Heat Map": ["view"],
        "Manuals": ["view"],
    },
}


def permission_code(module, action):
    return f"{module.lower().replace(' & ', '_').replace(' ', '_')}:{action}"


def ensure_permission(bind, module, action):
    code = permission_code(module, action)
    label = f"{action.title()} {module}"
    sort_order = (MODULE_ORDER.index(module) if module in MODULE_ORDER else 999) * 100 + (ACTIONS.index(action) if action in ACTIONS else 99)
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
    return code


def add_permission_to_role(bind, role_id, code):
    permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :code LIMIT 1"), {"code": code}).scalar()
    if not permission_id:
        return
    bind.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT :role_id, :permission_id
        WHERE NOT EXISTS (
            SELECT 1 FROM role_permissions WHERE role_id = :role_id AND permission_id = :permission_id
        )
    """), {"role_id": role_id, "permission_id": permission_id})


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}

    if "parent_franchise_user_id" not in user_columns:
        op.add_column("users", sa.Column("parent_franchise_user_id", sa.Integer(), nullable=True))
        op.create_index("ix_users_parent_franchise_user_id", "users", ["parent_franchise_user_id"])
        op.create_foreign_key("fk_users_parent_franchise_user_id_users", "users", "users", ["parent_franchise_user_id"], ["id"])

    if "created_by_user_id" not in user_columns:
        op.add_column("users", sa.Column("created_by_user_id", sa.Integer(), nullable=True))
        op.create_index("ix_users_created_by_user_id", "users", ["created_by_user_id"])
        op.create_foreign_key("fk_users_created_by_user_id_users", "users", "users", ["created_by_user_id"], ["id"])

    bind.execute(sa.text("""
        INSERT INTO roles (name, description, is_system_role, created_at)
        SELECT 'Franchise Employee', 'Employee created by a franchise user and limited to that franchise data.', true, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'Franchise Employee')
    """))

    for role_name, modules in ROLE_ACCESS.items():
        role_id = bind.execute(sa.text("SELECT id FROM roles WHERE name = :name LIMIT 1"), {"name": role_name}).scalar()
        if not role_id:
            continue
        for module, actions in modules.items():
            for action in actions:
                code = ensure_permission(bind, module, action)
                add_permission_to_role(bind, role_id, code)

    # Admin keeps access to the new Franchise Employees module even if role defaults were customized.
    admin_id = bind.execute(sa.text("SELECT id FROM roles WHERE name = 'Admin' LIMIT 1")).scalar()
    if admin_id:
        for action in ["view", "add", "edit", "delete", "manage"]:
            add_permission_to_role(bind, admin_id, ensure_permission(bind, "Franchise Employees", action))


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "created_by_user_id" in user_columns:
        try:
            op.drop_constraint("fk_users_created_by_user_id_users", "users", type_="foreignkey")
        except Exception:
            pass
        try:
            op.drop_index("ix_users_created_by_user_id", table_name="users")
        except Exception:
            pass
        op.drop_column("users", "created_by_user_id")
    if "parent_franchise_user_id" in user_columns:
        try:
            op.drop_constraint("fk_users_parent_franchise_user_id_users", "users", type_="foreignkey")
        except Exception:
            pass
        try:
            op.drop_index("ix_users_parent_franchise_user_id", table_name="users")
        except Exception:
            pass
        op.drop_column("users", "parent_franchise_user_id")
