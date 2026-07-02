"""Persistent import/job queue

Revision ID: v92_job_queue
Revises: v91_ops_centre
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = 'v92_job_queue'
down_revision = 'v91_ops_centre'
branch_labels = None
depends_on = None


def _has_column(table_name, column_name):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in [col['name'] for col in inspector.get_columns(table_name)]


def upgrade():
    columns = {
        'queue_name': sa.Column('queue_name', sa.String(length=80), nullable=False, server_default='default'),
        'priority': sa.Column('priority', sa.Integer(), nullable=False, server_default='100'),
        'attempts': sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        'max_attempts': sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='1'),
        'available_at': sa.Column('available_at', sa.DateTime(), nullable=True),
        'locked_at': sa.Column('locked_at', sa.DateTime(), nullable=True),
        'locked_by': sa.Column('locked_by', sa.String(length=120), nullable=True),
        'heartbeat_at': sa.Column('heartbeat_at', sa.DateTime(), nullable=True),
        'payload_json': sa.Column('payload_json', sa.Text(), nullable=True),
        'result_json': sa.Column('result_json', sa.Text(), nullable=True),
        'error_json': sa.Column('error_json', sa.Text(), nullable=True),
    }
    for name, column in columns.items():
        if not _has_column('import_jobs', name):
            op.add_column('import_jobs', column)

    op.execute("UPDATE import_jobs SET queue_name = 'default' WHERE queue_name IS NULL")
    op.execute("UPDATE import_jobs SET priority = 100 WHERE priority IS NULL")
    op.execute("UPDATE import_jobs SET attempts = 0 WHERE attempts IS NULL")
    op.execute("UPDATE import_jobs SET max_attempts = 1 WHERE max_attempts IS NULL")
    op.execute("UPDATE import_jobs SET heartbeat_at = started_at WHERE heartbeat_at IS NULL")
    op.execute("UPDATE import_jobs SET available_at = started_at WHERE available_at IS NULL")

    op.execute("CREATE INDEX IF NOT EXISTS ix_import_jobs_queue_status_available ON import_jobs (queue_name, status, available_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_import_jobs_priority ON import_jobs (priority)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_import_jobs_locked_at ON import_jobs (locked_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_import_jobs_locked_by ON import_jobs (locked_by)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_import_jobs_heartbeat_at ON import_jobs (heartbeat_at)")

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'import_job_logs' not in inspector.get_table_names():
        op.create_table(
            'import_job_logs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('import_job_id', sa.Integer(), nullable=False),
            sa.Column('level', sa.String(length=20), nullable=False, server_default='info'),
            sa.Column('message', sa.String(length=1000), nullable=False, server_default=''),
            sa.Column('data_json', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['import_job_id'], ['import_jobs.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_import_job_logs_import_job_id'), 'import_job_logs', ['import_job_id'], unique=False)
        op.create_index(op.f('ix_import_job_logs_level'), 'import_job_logs', ['level'], unique=False)
        op.create_index(op.f('ix_import_job_logs_created_at'), 'import_job_logs', ['created_at'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_import_job_logs_created_at'), table_name='import_job_logs')
    op.drop_index(op.f('ix_import_job_logs_level'), table_name='import_job_logs')
    op.drop_index(op.f('ix_import_job_logs_import_job_id'), table_name='import_job_logs')
    op.drop_table('import_job_logs')
    for idx in ['ix_import_jobs_heartbeat_at', 'ix_import_jobs_locked_by', 'ix_import_jobs_locked_at', 'ix_import_jobs_priority', 'ix_import_jobs_queue_status_available']:
        try:
            op.drop_index(idx, table_name='import_jobs')
        except Exception:
            pass
    for name in ['error_json', 'result_json', 'payload_json', 'heartbeat_at', 'locked_by', 'locked_at', 'available_at', 'max_attempts', 'attempts', 'priority', 'queue_name']:
        if _has_column('import_jobs', name):
            op.drop_column('import_jobs', name)
