"""v77 user hierarchy database repair

Revision ID: v77_user_hierarchy_fix
Revises: v76_user_creation_scope
Create Date: 2026-06-29

This migration repairs data for the Martins mother-company / franchise-user hierarchy:
- Ensures required roles exist.
- Ensures core permissions exist with the current permissions schema.
- Gives Admin all permissions so Admin screens do not 403 because of missing rows.
- Ensures the protected Martins administrator is active and has the Admin role.
- Removes franchise links from mother-company finance/admin users.
- Keeps Regional Manager and Franchise User franchise assignments intact.
- Keeps franchise employees under their parent franchise user.
"""
from alembic import op
import sqlalchemy as sa

revision = "v77_user_hierarchy_fix"
down_revision = "v76_user_creation_scope"
branch_labels = None
depends_on = None

ADMIN_EMAIL = "wjm@martinsdirect.com"

MOTHER_COMPANY_ROLES = (
    "Admin",
    "Finance Manager",
    "Finance Assistant",
    "Regional Manager",
)

FRANCHISE_OWNER_ROLES = (
    "Franchise User",
)

FRANCHISE_EMPLOYEE_ROLES = (
    "Franchise Manager",
    "Franchise Employee",
    "Franchise Agent",
)

ROLE_DESCRIPTIONS = {
    "Admin": "Martins Funerals South Africa administrator",
    "Finance Manager": "Martins Funerals South Africa finance manager",
    "Finance Assistant": "Martins Funerals South Africa finance assistant",
    "Regional Manager": "Martins regional manager linked to selected franchises",
    "Franchise User": "Franchise owner/user linked to one or more selected franchises",
    "Franchise Manager": "Manager created by a franchise user",
    "Franchise Employee": "Employee created by a franchise user",
    "Franchise Agent": "Agent created by a franchise user",
}

CORE_PERMISSIONS = [
    ("Users", "view", "users:view", "View users"),
    ("Users", "add", "users:add", "Create users"),
    ("Users", "edit", "users:edit", "Edit users"),
    ("Users", "delete", "users:delete", "Delete or deactivate users"),
    ("Users", "manage", "users:manage", "Manage users"),
    ("User Roles", "view", "user_roles:view", "View user roles"),
    ("User Roles", "edit", "user_roles:edit", "Edit user roles"),
    ("User Roles", "manage", "user_roles:manage", "Manage user roles"),
    ("Franchise Management", "view", "franchise_management:view", "View franchise management"),
    ("Franchise Management", "manage", "franchise_management:manage", "Manage franchises"),
    ("Franchise Details", "view", "franchise_details:view", "View franchise details"),
    ("Franchise Details", "edit", "franchise_details:edit", "Edit franchise details"),
    ("Franchise Agreement", "view", "franchise_agreement:view", "View franchise agreement"),
    ("Franchise Agreement", "edit", "franchise_agreement:edit", "Edit franchise agreement"),
    ("Royalty Scale", "view", "royalty_scale:view", "View royalty scale"),
    ("Royalty Scale", "edit", "royalty_scale:edit", "Edit royalty scale"),
    ("Monthly Figures", "view", "monthly_figures:view", "View monthly figures"),
    ("Monthly Figures", "edit", "monthly_figures:edit", "Edit monthly figures"),
    ("Monthly Figures", "import", "monthly_figures:import", "Import monthly figures"),
    ("Royalties", "view", "royalties:view", "View royalties"),
    ("Royalties", "edit", "royalties:edit", "Edit royalties"),
    ("Finance", "view", "finance:view", "View finance"),
    ("Finance", "edit", "finance:edit", "Edit finance"),
    ("Performance", "view", "performance:view", "View performance"),
    ("Performance", "manage", "performance:manage", "Manage performance"),
    ("Heat Map", "view", "heat_map:view", "View heat map"),
    ("Manuals", "view", "manuals:view", "View manuals"),
    ("Franchise Employees", "view", "franchise_employees:view", "View franchise employees"),
    ("Franchise Employees", "manage", "franchise_employees:manage", "Manage franchise employees"),
]


def table_exists(bind, table_name):
    return bool(bind.execute(sa.text("""
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = :table_name
        LIMIT 1
    """), {"table_name": table_name}).scalar())


def column_exists(bind, table_name, column_name):
    return bool(bind.execute(sa.text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :table_name
          AND column_name = :column_name
        LIMIT 1
    """), {"table_name": table_name, "column_name": column_name}).scalar())


def scalar(bind, sql, params=None):
    return bind.execute(sa.text(sql), params or {}).scalar()


def execute(bind, sql, params=None):
    bind.execute(sa.text(sql), params or {})


def ensure_roles(bind):
    has_description = column_exists(bind, "roles", "description")
    has_system_role = column_exists(bind, "roles", "is_system_role")
    has_created_at = column_exists(bind, "roles", "created_at")

    for name, description in ROLE_DESCRIPTIONS.items():
        role_id = scalar(bind, "SELECT id FROM roles WHERE name = :name", {"name": name})
        if role_id:
            updates = []
            params = {"id": role_id, "description": description}
            if has_description:
                updates.append("description = COALESCE(NULLIF(description, ''), :description)")
            if has_system_role:
                updates.append("is_system_role = TRUE")
            if updates:
                execute(bind, "UPDATE roles SET " + ", ".join(updates) + " WHERE id = :id", params)
            continue

        cols = ["name"]
        values = [":name"]
        params = {"name": name, "description": description}
        if has_description:
            cols.append("description")
            values.append(":description")
        if has_system_role:
            cols.append("is_system_role")
            values.append("TRUE")
        if has_created_at:
            cols.append("created_at")
            values.append("NOW()")
        execute(bind, f"INSERT INTO roles ({', '.join(cols)}) VALUES ({', '.join(values)})", params)


def ensure_permissions(bind):
    if not table_exists(bind, "permissions"):
        return

    has_label = column_exists(bind, "permissions", "label")
    has_sort_order = column_exists(bind, "permissions", "sort_order")
    has_description = column_exists(bind, "permissions", "description")

    for index, (module, action, code, label) in enumerate(CORE_PERMISSIONS, start=1):
        permission_id = scalar(bind, "SELECT id FROM permissions WHERE code = :code", {"code": code})
        if permission_id:
            updates = ["module = :module"]
            params = {"id": permission_id, "module": module, "action": action, "code": code, "label": label, "sort_order": index}
            if column_exists(bind, "permissions", "action"):
                updates.append("action = :action")
            if has_label:
                updates.append("label = COALESCE(NULLIF(label, ''), :label)")
            if has_description:
                updates.append("description = COALESCE(NULLIF(description, ''), :label)")
            if has_sort_order:
                updates.append("sort_order = COALESCE(sort_order, :sort_order)")
            execute(bind, "UPDATE permissions SET " + ", ".join(updates) + " WHERE id = :id", params)
            continue

        cols = ["module", "code"]
        vals = [":module", ":code"]
        params = {"module": module, "action": action, "code": code, "label": label, "sort_order": index}
        if column_exists(bind, "permissions", "action"):
            cols.append("action")
            vals.append(":action")
        if has_label:
            cols.append("label")
            vals.append(":label")
        if has_description:
            cols.append("description")
            vals.append(":label")
        if has_sort_order:
            cols.append("sort_order")
            vals.append(":sort_order")
        execute(bind, f"INSERT INTO permissions ({', '.join(cols)}) VALUES ({', '.join(vals)})", params)


def give_admin_all_permissions(bind):
    if not (table_exists(bind, "role_permissions") and table_exists(bind, "permissions")):
        return
    admin_id = scalar(bind, "SELECT id FROM roles WHERE name = 'Admin' LIMIT 1")
    if not admin_id:
        return
    execute(bind, """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT :role_id, p.id
        FROM permissions p
        WHERE NOT EXISTS (
            SELECT 1 FROM role_permissions rp
            WHERE rp.role_id = :role_id AND rp.permission_id = p.id
        )
    """, {"role_id": admin_id})


def ensure_protected_admin(bind):
    admin_id = scalar(bind, "SELECT id FROM roles WHERE name = 'Admin' LIMIT 1")
    if not admin_id:
        return

    where_clause = "LOWER(email) = :email"
    params = {"email": ADMIN_EMAIL}
    if column_exists(bind, "users", "name") and column_exists(bind, "users", "surname"):
        where_clause = "(" + where_clause + " OR (LOWER(name) = 'wjm' AND LOWER(surname) = 'piek'))"

    user_ids = [row[0] for row in bind.execute(sa.text(f"SELECT id FROM users WHERE {where_clause}"), params).fetchall()]
    for user_id in user_ids:
        execute(bind, """
            INSERT INTO user_roles (user_id, role_id)
            SELECT :user_id, :role_id
            WHERE NOT EXISTS (
                SELECT 1 FROM user_roles WHERE user_id = :user_id AND role_id = :role_id
            )
        """, {"user_id": user_id, "role_id": admin_id})
        if column_exists(bind, "users", "is_active"):
            execute(bind, "UPDATE users SET is_active = TRUE WHERE id = :user_id", {"user_id": user_id})
        if column_exists(bind, "users", "is_active_account"):
            execute(bind, "UPDATE users SET is_active_account = TRUE WHERE id = :user_id", {"user_id": user_id})
        if column_exists(bind, "users", "deactivated_at"):
            execute(bind, "UPDATE users SET deactivated_at = NULL WHERE id = :user_id", {"user_id": user_id})
        if column_exists(bind, "users", "deactivation_reason"):
            execute(bind, "UPDATE users SET deactivation_reason = '' WHERE id = :user_id", {"user_id": user_id})


def clear_mother_company_franchise_links(bind):
    role_names = tuple(MOTHER_COMPANY_ROLES)
    if table_exists(bind, "user_franchises"):
        execute(bind, """
            DELETE FROM user_franchises uf
            USING user_roles ur, roles r
            WHERE uf.user_id = ur.user_id
              AND ur.role_id = r.id
              AND r.name IN ('Admin', 'Finance Manager', 'Finance Assistant')
        """)

    if column_exists(bind, "users", "parent_franchise_user_id"):
        execute(bind, """
            UPDATE users
            SET parent_franchise_user_id = NULL
            WHERE id IN (
                SELECT ur.user_id
                FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                WHERE r.name IN ('Admin', 'Finance Manager', 'Finance Assistant', 'Regional Manager', 'Franchise User')
            )
        """)


def repair_role_assignments(bind):
    # If old plain Manager/Employee/Agent roles exist from testing, keep them, but also
    # make sure the canonical franchise role names exist.  Code displays these without
    # the "Franchise" prefix, so users still see Manager, Employee and Agent.
    for old_name, canonical_name in [
        ("Manager", "Franchise Manager"),
        ("Employee", "Franchise Employee"),
        ("Agent", "Franchise Agent"),
    ]:
        old_id = scalar(bind, "SELECT id FROM roles WHERE name = :name", {"name": old_name})
        canonical_id = scalar(bind, "SELECT id FROM roles WHERE name = :name", {"name": canonical_name})
        if old_id and canonical_id:
            execute(bind, """
                INSERT INTO user_roles (user_id, role_id)
                SELECT ur.user_id, :canonical_id
                FROM user_roles ur
                WHERE ur.role_id = :old_id
                  AND NOT EXISTS (
                    SELECT 1 FROM user_roles x
                    WHERE x.user_id = ur.user_id AND x.role_id = :canonical_id
                  )
            """, {"old_id": old_id, "canonical_id": canonical_id})


def upgrade():
    bind = op.get_bind()
    ensure_roles(bind)
    ensure_permissions(bind)
    give_admin_all_permissions(bind)
    ensure_protected_admin(bind)
    clear_mother_company_franchise_links(bind)
    repair_role_assignments(bind)


def downgrade():
    # Data repair migration; downgrade intentionally does not remove roles,
    # permissions, or user assignments.
    pass
