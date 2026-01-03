"""Add job_description to interviews

Revision ID: add_job_desc_001
Revises: 4243cd47bcce
Create Date: 2026-01-02 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_job_desc_001'
down_revision: Union[str, None] = '4243cd47bcce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add job_description column to interviews table
    op.add_column('interviews', sa.Column('job_description', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove job_description column
    op.drop_column('interviews', 'job_description')


