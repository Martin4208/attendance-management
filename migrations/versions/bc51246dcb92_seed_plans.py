"""seed plans

Revision ID: bc51246dcb92
Revises: 6b27b0c69fd9
Create Date: 2026-10-04 16:40:42.253259

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bc51246dcb92'
down_revision: Union[str, Sequence[str], None] = '6b27b0c69fd9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    plans = sa.table(
        "plans",
        sa.column("name", sa.Text),
        sa.column("user_limit", sa.Integer),
    )
    op.bulk_insert(plans, [
        {"name": "free", "user_limit": 5},
        {"name": "pro", "user_limit": None},
    ])


def downgrade() -> None:
    op.execute("DELETE FROM plans WHERE name IN ('free', 'pro')")
