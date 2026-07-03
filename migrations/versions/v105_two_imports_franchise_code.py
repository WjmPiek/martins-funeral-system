"""Two-import workflow and franchise-code matching

Revision ID: v105_two_imports_franchise_code
Revises: v104_master_data_management
Create Date: 2026-07-03
"""

revision = "v105_two_imports_franchise_code"
down_revision = "v104_master_data_management"
branch_labels = None
depends_on = None


def upgrade():
    # UI/workflow release only. Franchise-code columns already exist.
    pass


def downgrade():
    pass
