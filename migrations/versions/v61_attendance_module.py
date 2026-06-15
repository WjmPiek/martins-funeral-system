"""attendance module

Revision ID: v61_attendance_module
Revises: v60_heatmap_records
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = 'v61_attendance_module'
down_revision = 'v60_heatmap_records'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('attendance_staff',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('franchise_id', sa.Integer(), sa.ForeignKey('franchises.id'), nullable=True),
        sa.Column('first_name', sa.String(length=120), nullable=False, server_default=''),
        sa.Column('surname', sa.String(length=120), nullable=False, server_default=''),
        sa.Column('email', sa.String(length=255), nullable=True, server_default=''),
        sa.Column('phone', sa.String(length=80), nullable=True, server_default=''),
        sa.Column('id_number', sa.String(length=80), nullable=True, server_default=''),
        sa.Column('employee_number', sa.String(length=80), nullable=True, server_default=''),
        sa.Column('position', sa.String(length=120), nullable=True, server_default=''),
        sa.Column('staff_type', sa.String(length=40), nullable=True, server_default='Employee'),
        sa.Column('website_url', sa.String(length=255), nullable=True, server_default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_attendance_staff_franchise_id','attendance_staff',['franchise_id'])
    op.create_index('ix_attendance_staff_employee_number','attendance_staff',['employee_number'])
    op.create_index('ix_attendance_staff_is_active','attendance_staff',['is_active'])

    op.create_table('attendance_offices',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('franchise_id', sa.Integer(), sa.ForeignKey('franchises.id'), nullable=True),
        sa.Column('name', sa.String(length=160), nullable=False, server_default='Office'),
        sa.Column('address', sa.String(length=255), nullable=True, server_default=''),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('allowed_radius_m', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('qr_token', sa.String(length=120), nullable=False, unique=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_attendance_offices_franchise_id','attendance_offices',['franchise_id'])
    op.create_index('ix_attendance_offices_qr_token','attendance_offices',['qr_token'])

    op.create_table('attendance_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('staff_id', sa.Integer(), sa.ForeignKey('attendance_staff.id'), nullable=False),
        sa.Column('franchise_id', sa.Integer(), sa.ForeignKey('franchises.id'), nullable=True),
        sa.Column('office_id', sa.Integer(), sa.ForeignKey('attendance_offices.id'), nullable=True),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.Column('event_time', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('accuracy_meters', sa.Float(), nullable=True),
        sa.Column('distance_from_site_m', sa.Float(), nullable=True),
        sa.Column('gps_status', sa.String(length=50), nullable=True, server_default=''),
        sa.Column('work_location_type', sa.String(length=50), nullable=True, server_default='Office'),
        sa.Column('source', sa.String(length=50), nullable=True, server_default='web'),
        sa.Column('device_info', sa.Text(), nullable=True),
        sa.Column('employee_note', sa.Text(), nullable=True),
        sa.Column('manager_note', sa.Text(), nullable=True),
        sa.Column('approval_status', sa.String(length=30), nullable=False, server_default='pending'),
        sa.Column('approved_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('rejected_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_attendance_events_staff_id','attendance_events',['staff_id'])
    op.create_index('ix_attendance_events_franchise_id','attendance_events',['franchise_id'])
    op.create_index('ix_attendance_events_event_time','attendance_events',['event_time'])
    op.create_index('ix_attendance_events_approval_status','attendance_events',['approval_status'])

    op.create_table('attendance_leave_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('staff_id', sa.Integer(), sa.ForeignKey('attendance_staff.id'), nullable=False),
        sa.Column('franchise_id', sa.Integer(), sa.ForeignKey('franchises.id'), nullable=True),
        sa.Column('leave_type', sa.String(length=80), nullable=False, server_default='Annual Leave'),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='pending'),
        sa.Column('manager_note', sa.Text(), nullable=True),
        sa.Column('decided_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_attendance_leave_requests_staff_id','attendance_leave_requests',['staff_id'])
    op.create_index('ix_attendance_leave_requests_status','attendance_leave_requests',['status'])

    modules = ['Attendance']
    actions = ['view','add','edit','delete','export','approve','import','manage']
    for module in modules:
        for idx, action in enumerate(actions):
            code = f"{module.lower().replace(' & ', '_').replace(' ', '_')}:{action}"
            op.execute(sa.text("""
                INSERT INTO permissions (module, action, code, label, sort_order)
                SELECT :module, :action, :code, :label, :sort_order
                WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)
            """).bindparams(module=module, action=action, code=code, label=f"{module} - {action.title()}", sort_order=900+idx))
    op.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.name = 'Admin' AND p.module = 'Attendance'
        ON CONFLICT DO NOTHING
    """))


def downgrade():
    op.drop_table('attendance_leave_requests')
    op.drop_table('attendance_events')
    op.drop_table('attendance_offices')
    op.drop_table('attendance_staff')
    op.execute("DELETE FROM permissions WHERE module = 'Attendance'")
