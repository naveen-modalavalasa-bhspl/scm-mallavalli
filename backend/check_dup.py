import asyncio
from sqlalchemy import select, text
from app.database import AsyncSessionLocal
from app.models.settings_master import Position

async def check_duplicates():
    async with AsyncSessionLocal() as db:
        q = select(Position).where(Position.name == 'George (SCM Head)')
        rows = (await db.execute(q)).scalars().all()
        print(f"Found {len(rows)} rows for 'George (SCM Head)':")
        for r in rows:
            print(f"ID: {r.id}, Name: {r.name}, Code: {r.code}, Parent: {r.parent_position_id}")

if __name__ == '__main__':
    asyncio.run(check_duplicates())
