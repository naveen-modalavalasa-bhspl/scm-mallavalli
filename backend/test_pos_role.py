import asyncio
from app.database import AsyncSessionLocal
from app.models.master import Position
from app.models.user import Role
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Position.name, Role.code).join(Role, Role.id == Position.role_id).where(Position.id == 4487))
        print(res.all())

asyncio.run(main())
