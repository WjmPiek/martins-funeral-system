"""Performance cache stabilization

Revision ID: v90_perf_cache
Revises: v89_live_refresh
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = 'v90_perf_cache'
down_revision = 'v89_live_refresh'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'performance_page_cache',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cache_type', sa.String(length=80), nullable=False),
        sa.Column('cache_key', sa.String(length=255), nullable=False),
        sa.Column('scope_type', sa.String(length=40), nullable=False, server_default='global'),
        sa.Column('scope_id', sa.Integer(), nullable=True),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('month', sa.Integer(), nullable=True),
        sa.Column('metric', sa.String(length=80), nullable=True),
        sa.Column('payload_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('row_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('source_version', sa.String(length=80), nullable=False, server_default='phase5'),
        sa.Column('invalidated_at', sa.DateTime(), nullable=True),
        sa.Column('built_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('cache_type', 'cache_key', name='uq_performance_page_cache_key'),
    )
    op.create_index('ix_performance_page_cache_type_period', 'performance_page_cache', ['cache_type', 'year', 'month'])
    op.create_index('ix_performance_page_cache_scope', 'performance_page_cache', ['scope_type', 'scope_id'])
    op.create_index('ix_performance_page_cache_valid', 'performance_page_cache', ['invalidated_at', 'built_at'])
    op.create_index('ix_performance_page_cache_metric', 'performance_page_cache', ['metric'])
    op.execute("CREATE INDEX IF NOT EXISTS ix_performance_results_period_lookup ON performance_results (year, month, metric, franchise_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_monthly_figures_period_franchise_lookup ON monthly_figures (year, month, franchise_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_franchises_performance_active_name ON franchises (is_performance_active, business_name)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_franchises_performance_active_name")
    op.execute("DROP INDEX IF EXISTS ix_monthly_figures_period_franchise_lookup")
    op.execute("DROP INDEX IF EXISTS ix_performance_results_period_lookup")
    op.drop_index('ix_performance_page_cache_metric', table_name='performance_page_cache')
    op.drop_index('ix_performance_page_cache_valid', table_name='performance_page_cache')
    op.drop_index('ix_performance_page_cache_scope', table_name='performance_page_cache')
    op.drop_index('ix_performance_page_cache_type_period', table_name='performance_page_cache')
    op.drop_table('performance_page_cache')
