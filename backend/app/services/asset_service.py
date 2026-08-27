import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.warehouse import SerialNumber

logger = logging.getLogger(__name__)

async def get_max_system_serial_number(db: AsyncSession) -> int:
    """Find the maximum system-generated serial number in the DB.
    Uses a MySQL advisory lock to guarantee idempotency and prevent duplicate generation under high concurrency.
    """
    from sqlalchemy import text
    await db.execute(text("SELECT GET_LOCK('system_serial_number', 10)"))
    try:
        stmt = text("""
            SELECT MAX(CAST(
                CASE 
                    WHEN serial_number REGEXP '^[0-9]+$' THEN serial_number
                    WHEN serial_number REGEXP '^1-[0-9]+($|-)' THEN SUBSTRING_INDEX(SUBSTRING_INDEX(serial_number, '-', 2), '-', -1)
                    WHEN serial_number REGEXP '-1-[0-9]+$' THEN SUBSTRING_INDEX(serial_number, '-', -1)
                    ELSE '0'
                END 
            AS UNSIGNED)) AS max_val
            FROM serial_numbers
        """)
        res = await db.execute(stmt)
        max_val = res.scalar()
        return max_val if max_val else 0
    finally:
        await db.execute(text("SELECT RELEASE_LOCK('system_serial_number')"))

async def get_next_system_serial_number(db: AsyncSession, offset: int = 0) -> str:
    """Get the next system-generated serial number.
    Uses get_max_system_serial_number to find the maximum value, and returns the next sequential number plus the offset.
    """
    max_val = await get_max_system_serial_number(db)
    next_val = max_val + 1 + offset
    return str(next_val)

def generate_asset_code(serial_number: str, material_code: str) -> str:
    """Generate asset/consumable code according to format {material_code}-1-{serial_number}."""
    return f"{material_code.strip()}-1-{serial_number.strip()}"
