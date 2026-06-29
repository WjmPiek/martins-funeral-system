"""v78 security growth targets

Revision ID: v78_security_growth
Revises: v77_user_hierarchy_fix
Create Date: 2026-06-29

Repairs user hierarchy permissions and seeds fair growth target brackets.
"""
from alembic import op
import sqlalchemy as sa

revision = "v78_security_growth"
down_revision = "v77_user_hierarchy_fix"
branch_labels = None
depends_on = None

ADMIN_EMAIL = "wjm@martinsdirect.com"

ROLE_DESCRIPTIONS = {
    "Admin": "Martins Funerals South Africa administrator",
    "Finance Manager": "Martins Funerals South Africa finance manager",
    "Finance Assistant": "Martins Funerals South Africa finance assistant",
    "Regional Manager": "Martins regional manager linked to selected franchises",
    "Franchise User": "Franchise owner/user linked to franchise data",
    "Franchise Manager": "Manager created by a franchise user",
    "Franchise Employee": "Employee created by a franchise user",
    "Franchise Agent": "Agent created by a franchise user",
}

CORE_PERMISSIONS = [
    ("Users", "view", "users:view", "View users"),
    ("Users", "add", "users:add", "Create users"),
    ("Users", "edit", "users:edit", "Edit users"),
    ("Users", "delete", "users:delete", "Delete users"),
    ("Users", "manage", "users:manage", "Manage users"),
    ("User Roles", "view", "user_roles:view", "View user roles"),
    ("User Roles", "edit", "user_roles:edit", "Edit user roles"),
    ("User Roles", "manage", "user_roles:manage", "Manage user roles"),
    ("Franchise Details", "view", "franchise_details:view", "View franchise details"),
    ("Franchise Details", "edit", "franchise_details:edit", "Edit franchise details"),
    ("Franchise Agreement", "view", "franchise_agreement:view", "View franchise agreement"),
    ("Royalty Scale", "view", "royalty_scale:view", "View royalty scale"),
    ("Performance", "view", "performance:view", "View performance"),
    ("Performance", "manage_targets", "performance:manage_targets", "Manage performance targets"),
    ("Performance", "manage_inactive", "performance:manage_inactive", "Manage old/inactive franchises"),
    ("Monthly Figures", "view", "monthly_figures:view", "View monthly figures"),
    ("Royalties", "view", "royalties:view", "View royalties"),
    ("Finance", "view", "finance:view", "View finance"),
    ("Heat Map", "view", "heatmap:view", "View heat map"),
    ("Manuals", "view", "manuals:view", "View manuals"),
    ("Franchise Employees", "view", "franchise_employees:view", "View franchise employees"),
    ("Franchise Employees", "manage", "franchise_employees:manage", "Manage franchise employees"),
]

MONEY_BRACKETS = [
    (0, 150000, 15),
    (150000, 300000, 12),
    (300000, 500000, 10),
    (500000, 750000, 8),
    (750000, 1200000, 6),
    (1200000, None, 5),
]
COUNT_BRACKETS = [
    (0, 10, 15),
    (10, 20, 12),
    (20, 30, 10),
    (30, 45, 8),
    (45, 60, 6),
    (60, None, 5),
]


def scalar(bind, sql, params=None):
    return bind.execute(sa.text(sql), params or {}).scalar()


def execute(bind, sql, params=None):
    bind.execute(sa.text(sql), params or {})


def table_exists(bind, table_name):
    return bool(scalar(bind, """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name=:table_name
        LIMIT 1
    """, {"table_name": table_name}))


def column_exists(bind, table_name, column_name):
    return bool(scalar(bind, """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:table_name AND column_name=:column_name
        LIMIT 1
    """, {"table_name": table_name, "column_name": column_name}))


def ensure_roles(bind):
    if not table_exists(bind, "roles"):
        return
    has_description = column_exists(bind, "roles", "description")
    has_system_role = column_exists(bind, "roles", "is_system_role")
    for role_name, description in ROLE_DESCRIPTIONS.items():
        role_id = scalar(bind, "SELECT id FROM roles WHERE name=:name", {"name": role_name})
        if not role_id:
            cols = ["name"]
            vals = [":name"]
            params = {"name": role_name}
            if has_description:
                cols.append("description")
                vals.append(":description")
                params["description"] = description
            if has_system_role:
                cols.append("is_system_role")
                vals.append("TRUE")
            execute(bind, f"INSERT INTO roles ({', '.join(cols)}) VALUES ({', '.join(vals)})", params)


def ensure_permissions(bind):
    if not table_exists(bind, "permissions"):
        return
    has_label = column_exists(bind, "permissions", "label")
    has_sort_order = column_exists(bind, "permissions", "sort_order")
    for idx, (module, action, code, label) in enumerate(CORE_PERMISSIONS, start=1):
        permission_id = scalar(bind, "SELECT id FROM permissions WHERE code=:code", {"code": code})
        if permission_id:
            continue
        cols = ["module", "action", "code"]
        vals = [":module", ":action", ":code"]
        params = {"module": module, "action": action, "code": code}
        if has_label:
            cols.append("label")
            vals.append(":label")
            params["label"] = label
        if has_sort_order:
            cols.append("sort_order")
            vals.append(":sort_order")
            params["sort_order"] = idx
        execute(bind, f"INSERT INTO permissions ({', '.join(cols)}) VALUES ({', '.join(vals)})", params)


def grant_admin_all_permissions(bind):
    if not (table_exists(bind, "roles") and table_exists(bind, "permissions") and table_exists(bind, "role_permissions")):
        return
    for role_name in ("Admin", "Super Admin"):
        role_id = scalar(bind, "SELECT id FROM roles WHERE name=:name", {"name": role_name})
        if not role_id:
            continue
        execute(bind, """
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT :role_id, p.id
            FROM permissions p
            WHERE NOT EXISTS (
                SELECT 1 FROM role_permissions rp
                WHERE rp.role_id=:role_id AND rp.permission_id=p.id
            )
        """, {"role_id": role_id})


def repair_protected_admin(bind):
    if not (table_exists(bind, "users") and table_exists(bind, "roles") and table_exists(bind, "user_roles")):
        return
    user_id = scalar(bind, "SELECT id FROM users WHERE lower(email)=:email", {"email": ADMIN_EMAIL})
    role_id = scalar(bind, "SELECT id FROM roles WHERE name='Admin'")
    if user_id and role_id:
        if column_exists(bind, "users", "is_active"):
            execute(bind, "UPDATE users SET is_active=TRUE WHERE id=:id", {"id": user_id})
        if column_exists(bind, "users", "is_active_account"):
            execute(bind, "UPDATE users SET is_active_account=TRUE WHERE id=:id", {"id": user_id})
        execute(bind, """
            INSERT INTO user_roles (user_id, role_id)
            SELECT :user_id, :role_id
            WHERE NOT EXISTS (
                SELECT 1 FROM user_roles WHERE user_id=:user_id AND role_id=:role_id
            )
        """, {"user_id": user_id, "role_id": role_id})


def clean_mother_company_links(bind):
    if not (table_exists(bind, "users") and table_exists(bind, "roles") and table_exists(bind, "user_roles")):
        return
    mother_roles = ["Admin", "Finance Manager", "Finance Assistant"]
    role_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM roles WHERE name = ANY(:names)"), {"names": mother_roles}).all()]
    if not role_ids:
        return
    user_ids = [row[0] for row in bind.execute(sa.text("SELECT DISTINCT user_id FROM user_roles WHERE role_id = ANY(:role_ids)"), {"role_ids": role_ids}).all()]
    if not user_ids:
        return
    if column_exists(bind, "users", "parent_franchise_user_id"):
        execute(bind, "UPDATE users SET parent_franchise_user_id=NULL WHERE id = ANY(:ids)", {"ids": user_ids})
    if table_exists(bind, "user_franchises"):
        execute(bind, "DELETE FROM user_franchises WHERE user_id = ANY(:ids)", {"ids": user_ids})


def seed_growth_brackets(bind):
    if not table_exists(bind, "performance_growth_brackets"):
        return
    metrics = {
        "cash": ("cash", MONEY_BRACKETS),
        "sales": ("sales", MONEY_BRACKETS),
        "insurance_premiums": ("insurance_premiums", MONEY_BRACKETS),
        "joinings": ("joinings", COUNT_BRACKETS),
        "funerals": ("funerals", COUNT_BRACKETS),
    }
    for metric, (basis_metric, brackets) in metrics.items():
        for amount_from, amount_to, growth_percent in brackets:
            exists = scalar(bind, """
                SELECT id FROM performance_growth_brackets
                WHERE metric=:metric AND basis_metric=:basis_metric AND amount_from=:amount_from
                  AND ((amount_to IS NULL AND :amount_to IS NULL) OR amount_to=:amount_to)
                LIMIT 1
            """, {"metric": metric, "basis_metric": basis_metric, "amount_from": amount_from, "amount_to": amount_to})
            if exists:
                execute(bind, """
                    UPDATE performance_growth_brackets
                    SET growth_percent=:growth_percent, is_active=TRUE
                    WHERE id=:id
                """, {"growth_percent": growth_percent, "id": exists})
            else:
                execute(bind, """
                    INSERT INTO performance_growth_brackets
                    (metric, basis_metric, amount_from, amount_to, growth_percent, is_active)
                    VALUES (:metric, :basis_metric, :amount_from, :amount_to, :growth_percent, TRUE)
                """, {"metric": metric, "basis_metric": basis_metric, "amount_from": amount_from, "amount_to": amount_to, "growth_percent": growth_percent})


def upgrade():
    bind = op.get_bind()
    ensure_roles(bind)
    ensure_permissions(bind)
    grant_admin_all_permissions(bind)
    repair_protected_admin(bind)
    clean_mother_company_links(bind)
    seed_growth_brackets(bind)


def downgrade():
    # Data repair migration; keep repaired roles/permissions and target brackets.
    pass
