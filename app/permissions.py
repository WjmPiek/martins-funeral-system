MODULES = [
    "Dashboard",
    "Franchise Settings",
    "Franchise Details",
    "Franchise Agreement",
    "Royalty Scale",
    "Joinings",
    "Funeral Services",
    "Insurance Claims",
    "Heat Map",
    "Attendance",
    "Royalties",
    "Monthly Figures",
    "Finance",
    "Users",
    "User Roles",
    "Franchise Management",
    "Imports & Data",
    "Audit Logs",
    "System Administration",
    "PDF Templates",
    "Email Templates",
    "Backup Management",
]

ACTIONS = ["view", "add", "edit", "delete", "export", "approve", "import", "manage"]

ROLE_TEMPLATES = {
    "Admin": "Full unrestricted system access.",
    "Regional Manager": "Can view and manage assigned franchise performance and reports.",
    "Finance Manager": "Can manage finance, royalties, monthly figures, and approvals.",
    "Finance Assistant": "Can capture and update finance-related operational records.",
    "Franchise Manager": "Can manage own franchise records and exports, excluding admin settings.",
    "Franchise User": "Can view and capture normal franchise operational records.",
    "Read Only User": "Can view allowed pages and reports only.",
}

ROLE_DEFAULTS = {
    "Admin": "ALL",
    "Regional Manager": {
        "Dashboard": ["view"], "Franchise Settings": ["view"], "Franchise Details": ["view", "export"], "Franchise Management": ["view"],
        "Joinings": ["view", "export"], "Funeral Services": ["view", "export"],
        "Insurance Claims": ["view", "export"], "Heat Map": ["view", "export"], "Attendance": ["view", "add", "edit", "export", "approve", "manage"],
        "Royalties": ["view", "export"], "Monthly Figures": ["view", "export"],
    },
    "Finance Manager": {
        "Dashboard": ["view"], "Franchise Settings": ["view"], "Franchise Details": ["view", "edit", "export"], "Franchise Agreement": ["view"], "Royalty Scale": ["view"], "Franchise Management": ["view", "manage"],
        "Insurance Claims": ["view", "edit", "export", "approve"], "Royalties": ["view", "add", "edit", "export", "approve"],
        "Monthly Figures": ["view", "edit", "delete", "export", "approve"], "Finance": ["view", "add", "edit", "export", "approve"], "Franchise Agreement": ["view", "edit", "manage"], "Royalty Scale": ["view", "edit", "manage"],
    },
    "Finance Assistant": {
        "Dashboard": ["view"], "Franchise Management": ["view", "manage"], "Users": ["view", "edit"], "Insurance Claims": ["view", "add", "edit", "export"],
        "Royalties": ["view", "add", "edit", "export"], "Monthly Figures": ["view", "import", "edit", "export"],
        "Finance": ["view", "add", "edit", "export"],
    },
    "Franchise Manager": {
        "Dashboard": ["view"], "Franchise Settings": ["view"], "Franchise Details": ["view", "edit", "export"],
        "Joinings": ["view", "add", "edit", "export"], "Funeral Services": ["view", "add", "edit", "export"],
        "Insurance Claims": ["view", "add", "edit", "export"], "Heat Map": ["view", "export"], "Attendance": ["view", "add", "edit", "export", "approve", "manage"],
        "Royalties": ["view", "export"], "Monthly Figures": ["view", "edit", "export"],
    },
    "Franchise User": {
        "Dashboard": ["view"], "Franchise Settings": ["view"], "Franchise Details": ["view", "edit", "export"],
        "Joinings": ["view", "add", "edit", "export"], "Funeral Services": ["view", "add", "edit", "export"],
        "Insurance Claims": ["view", "add", "edit", "export"], "Heat Map": ["view"], "Attendance": ["view", "add", "edit", "export"],
        "Royalties": ["view", "export"], "Monthly Figures": ["view", "edit", "export"],
    },
    "Read Only User": {
        "Dashboard": ["view"], "Franchise Settings": ["view"], "Franchise Details": ["view", "export"],
        "Joinings": ["view"], "Funeral Services": ["view"], "Insurance Claims": ["view"],
        "Heat Map": ["view"], "Attendance": ["view"], "Royalties": ["view"], "Monthly Figures": ["view"],
    },
}

def permission_code(module, action):
    return f"{module.lower().replace(' & ', '_').replace(' ', '_')}:{action}"
