"""Live enterprise system notifications and import publishing

Revision ID: v88_live_system
Revises: v87_import_progress_ui_currency
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = 'v88_live_system'
down_revision = 'v87_import_progress_ui_currency'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'live_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('kind', sa.String(length=80), nullable=False, server_default='system'),
        sa.Column('title', sa.String(length=160), nullable=False, server_default=''),
        sa.Column('message', sa.String(length=500), nullable=True, server_default=''),
        sa.Column('visibility', sa.String(length=40), nullable=False, server_default='admin_finance'),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('import_job_id', sa.Integer(), nullable=True),
        sa.Column('franchise_id', sa.Integer(), nullable=True),
        sa.Column('month', sa.Integer(), nullable=True),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('payload_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['import_job_id'], ['import_jobs.id']),
        sa.ForeignKeyConstraint(['franchise_id'], ['franchises.id']),
    )
    op.create_index('ix_live_events_kind', 'live_events', ['kind'])
    op.create_index('ix_live_events_visibility', 'live_events', ['visibility'])
    op.create_index('ix_live_events_user_id', 'live_events', ['user_id'])
    op.create_index('ix_live_events_import_job_id', 'live_events', ['import_job_id'])
    op.create_index('ix_live_events_franchise_id', 'live_events', ['franchise_id'])
    op.create_index('ix_live_events_period', 'live_events', ['year', 'month'])
    op.create_index('ix_live_events_created_at', 'live_events', ['created_at'])

    op.create_table(
        'live_notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False, server_default=''),
        sa.Column('message', sa.String(length=500), nullable=True, server_default=''),
        sa.Column('category', sa.String(length=40), nullable=False, server_default='system'),
        sa.Column('franchise_id', sa.Integer(), nullable=True),
        sa.Column('import_job_id', sa.Integer(), nullable=True),
        sa.Column('payload_json', sa.Text(), nullable=True),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['franchise_id'], ['franchises.id']),
        sa.ForeignKeyConstraint(['import_job_id'], ['import_jobs.id']),
    )
    op.create_index('ix_live_notifications_user_id', 'live_notifications', ['user_id'])
    op.create_index('ix_live_notifications_category', 'live_notifications', ['category'])
    op.create_index('ix_live_notifications_franchise_id', 'live_notifications', ['franchise_id'])
    op.create_index('ix_live_notifications_import_job_id', 'live_notifications', ['import_job_id'])
    op.create_index('ix_live_notifications_read_at', 'live_notifications', ['read_at'])
    op.create_index('ix_live_notifications_created_at', 'live_notifications', ['created_at'])

    # Existing imported records should be visible in the live system immediately.
    op.execute("UPDATE monthly_figures SET status='Published' WHERE status IN ('Imported','Calculated','Approved','Submitted')")


def downgrade():
    op.drop_index('ix_live_notifications_created_at', table_name='live_notifications')
    op.drop_index('ix_live_notifications_read_at', table_name='live_notifications')
    op.drop_index('ix_live_notifications_import_job_id', table_name='live_notifications')
    op.drop_index('ix_live_notifications_franchise_id', table_name='live_notifications')
    op.drop_index('ix_live_notifications_category', table_name='live_notifications')
    op.drop_index('ix_live_notifications_user_id', table_name='live_notifications')
    op.drop_table('live_notifications')
    op.drop_index('ix_live_events_created_at', table_name='live_events')
    op.drop_index('ix_live_events_period', table_name='live_events')
    op.drop_index('ix_live_events_franchise_id', table_name='live_events')
    op.drop_index('ix_live_events_import_job_id', table_name='live_events')
    op.drop_index('ix_live_events_user_id', table_name='live_events')
    op.drop_index('ix_live_events_visibility', table_name='live_events')
    op.drop_index('ix_live_events_kind', table_name='live_events')
    op.drop_table('live_events')
