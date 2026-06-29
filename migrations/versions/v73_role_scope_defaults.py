"""Role scope defaults for Regional Manager and Franchise users

Revision ID: v73_role_scope
Revises: v72_perf_inactive
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa

revision = "v73_role_scope"
down_revision = "v72_perf_inactive"
branch_labels = None
depends_on = None

ACTIONS = ["view", "add", "edit", "delete", "export", "approve", "import", "manage"]

ROLE_ACCESS = {
    "Regional Manager": {
        "Dashboard": ["view"],
        "Franchise Settings": ["view"],
        "Franchise Details": ["view", "edit", "export"],
        "Franchise Agreement": ["view"],
        "Royalty Scale": ["view"],
        "Performance": ["view", "export"],
        "Royalties": ["view", "export"],
        "Monthly Figures": ["view", "export"],
        "Heat Map": ["view", "export"],
        "Manuals": ["view"],
    },
    "Franchise Manager": {
        "Dashboard": ["view"],
        "Franchise Settings": ["view"],
        "Franchise Details": ["view", "edit", "export"],
        "Franchise Agreement": ["view"],
        "Royalty Scale": ["view"],
        "Performance": ["view", "export"],
        "Royalties": ["view", "export"],
        "Monthly Figures": ["view", "export"],
        "Heat Map": ["view"],
        "Manuals": ["view"],
    },
    "Franchise User": {
        "Dashboard": ["view"],
        "Franchise Settings": ["view"],
        "Franchise Details": ["view", "edit", "export"],
        "Franchise Agreement": ["view"],
        "Royalty Scale": ["view"],
        "Performance": ["view", "export"],
        "Royalties": ["view", "export"],
        "Monthly Figures": ["view", "export"],
        "Heat Map": ["view"],
        "Manuals": ["view"],
    },
}

MODULE_ORDER = [
    "Dashboard", "Franchise Settings", "Franchise Details", "Franchise Agreement", "Royalty Scale",
    "Performance", "Heat Map", "Manuals", "Royalties", "Monthly Figures", "Joinings",
    "Funeral Services", "Insurance Claims", "Attendance", "Finance", "Users", "User Roles",
    "Franchise Management", "Imports & Data", "Audit Logs", "System Administration",
]


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


def upgrade():
    bind = op.get_bind()

    for role_name, modules in ROLE_ACCESS.items():
        role_id = bind.execute(sa.text("SELECT id FROM roles WHERE name = :name LIMIT 1"), {"name": role_name}).scalar()
        if not role_id:
            continue

        allowed_codes = []
        for module, actions in modules.items():
            for action in actions:
                allowed_codes.append(ensure_permission(bind, module, action))

        # Clear this role's current permissions so Regional Manager and Franchise users only see the approved tabs.
        bind.execute(sa.text("DELETE FROM role_permissions WHERE role_id = :role_id"), {"role_id": role_id})

        for code in allowed_codes:
            permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :code LIMIT 1"), {"code": code}).scalar()
            if permission_id:
                bind.execute(sa.text("""
                    INSERT INTO role_permissions (role_id, permission_id)
                    SELECT :role_id, :permission_id
                    WHERE NOT EXISTS (
                        SELECT 1 FROM role_permissions WHERE role_id = :role_id AND permission_id = :permission_id
                    )
                """), {"role_id": role_id, "permission_id": permission_id})


def downgrade():
    # Do not try to reconstruct the previous custom role assignments.
    pass
