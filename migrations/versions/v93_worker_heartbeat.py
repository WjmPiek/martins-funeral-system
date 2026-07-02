"""Worker heartbeat monitoring

Revision ID: v93_worker_heartbeat
Revises: v92_job_queue
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = 'v93_worker_heartbeat'
down_revision = 'v92_job_queue'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'worker_heartbeats' not in inspector.get_table_names():
        op.create_table(
            'worker_heartbeats',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('worker_id', sa.String(length=120), nullable=False),
            sa.Column('queue_name', sa.String(length=80), nullable=False, server_default='default'),
            sa.Column('status', sa.String(length=30), nullable=False, server_default='idle'),
            sa.Column('current_job_id', sa.Integer(), nullable=True),
            sa.Column('hostname', sa.String(length=160), nullable=True),
            sa.Column('process_id', sa.Integer(), nullable=True),
            sa.Column('last_message', sa.String(length=255), nullable=True),
            sa.Column('started_at', sa.DateTime(), nullable=False),
            sa.Column('heartbeat_at', sa.DateTime(), nullable=False),
            sa.Column('stopped_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['current_job_id'], ['import_jobs.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('worker_id', name='uq_worker_heartbeats_worker_id'),
        )
        op.create_index(op.f('ix_worker_heartbeats_worker_id'), 'worker_heartbeats', ['worker_id'], unique=True)
        op.create_index(op.f('ix_worker_heartbeats_queue_name'), 'worker_heartbeats', ['queue_name'], unique=False)
        op.create_index(op.f('ix_worker_heartbeats_status'), 'worker_heartbeats', ['status'], unique=False)
        op.create_index(op.f('ix_worker_heartbeats_current_job_id'), 'worker_heartbeats', ['current_job_id'], unique=False)
        op.create_index(op.f('ix_worker_heartbeats_started_at'), 'worker_heartbeats', ['started_at'], unique=False)
        op.create_index(op.f('ix_worker_heartbeats_heartbeat_at'), 'worker_heartbeats', ['heartbeat_at'], unique=False)
        op.create_index(op.f('ix_worker_heartbeats_stopped_at'), 'worker_heartbeats', ['stopped_at'], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'worker_heartbeats' in inspector.get_table_names():
        op.drop_index(op.f('ix_worker_heartbeats_stopped_at'), table_name='worker_heartbeats')
        op.drop_index(op.f('ix_worker_heartbeats_heartbeat_at'), table_name='worker_heartbeats')
        op.drop_index(op.f('ix_worker_heartbeats_started_at'), table_name='worker_heartbeats')
        op.drop_index(op.f('ix_worker_heartbeats_current_job_id'), table_name='worker_heartbeats')
        op.drop_index(op.f('ix_worker_heartbeats_status'), table_name='worker_heartbeats')
        op.drop_index(op.f('ix_worker_heartbeats_queue_name'), table_name='worker_heartbeats')
        op.drop_index(op.f('ix_worker_heartbeats_worker_id'), table_name='worker_heartbeats')
        op.drop_table('worker_heartbeats')
