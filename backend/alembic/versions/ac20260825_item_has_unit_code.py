"""add has_unit_code toggle to items

Unit code generation (serial_numbers.asset_code / consumable_code) used to be
decided entirely by items.item_type: an item typed 'asset' or 'consumable' got
codes at putaway, anything else got none, and there was no way to turn it off.
It is now a per-item toggle in the Tracking tab, alongside has_batch /
has_serial / has_expiry. item_type still decides WHICH column the code lands
in; the toggle decides WHETHER one is generated at all.

The backfill turns the toggle on for every item that generates codes today, so
existing items keep behaving exactly as they do now.

Revision ID: ac20260825_item_has_unit_code
Revises: e5970e8dc9f3
Create Date: 2026-08-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ac20260825_item_has_unit_code'
down_revision: Union[str, Sequence[str], None] = 'e5970e8dc9f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('items', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'has_unit_code', sa.Boolean(), nullable=True,
            server_default=sa.text('0'),
        ))

    # Preserve today's behaviour for existing rows: everything that currently
    # generates codes keeps generating them.
    op.execute(
        "UPDATE items SET has_unit_code = 1 "
        "WHERE item_type IN ('asset', 'consumable')"
    )


def downgrade() -> None:
    with op.batch_alter_table('items', schema=None) as batch_op:
        batch_op.drop_column('has_unit_code')
