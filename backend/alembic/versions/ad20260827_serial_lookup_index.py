"""add serial_numbers lookup index for stock-balance enrichment

serial_numbers had only PRIMARY(id), uq_item_serial(item_id, serial_number)
and batch_id. Every stock-balance page enriches rows by querying

    item_id = ? AND warehouse_id = ? AND status = 'available'
              AND bin_id = ? AND batch_id = ?

so MySQL could only use the item_id prefix of uq_item_serial and then filtered
the rest by hand — EXPLAIN showed ~9000 rows examined per item at filtered=0.2%.
With 87 items x 5000 units that is a 430k-row scan on every request.

This composite index covers the whole predicate. Column order puts the two
always-present equality columns first, then status, then the two that are NULL
for non-central warehouses.

Revision ID: ad20260827_serial_lookup_index
Revises: ac20260825_item_has_unit_code
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'ad20260827_serial_lookup_index'
down_revision: Union[str, Sequence[str], None] = 'ac20260825_item_has_unit_code'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'idx_sn_item_wh_status',
        'serial_numbers',
        ['item_id', 'warehouse_id', 'status', 'bin_id', 'batch_id'],
    )


def downgrade() -> None:
    op.drop_index('idx_sn_item_wh_status', table_name='serial_numbers')
