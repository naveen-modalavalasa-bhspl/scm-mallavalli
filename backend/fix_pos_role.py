import asyncio
from app.database import AsyncSessionLocal
from app.models.master import Position
from sqlalchemy import update

async def main():
    async with AsyncSessionLocal() as db:
        await db.execute(update(Position).where(Position.id == 4487).values(role_id=57))
        await db.commit()
        print("Updated position 4487 to role 57")

asyncio.run(main())
