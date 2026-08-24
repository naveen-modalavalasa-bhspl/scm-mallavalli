import asyncio
from sqlalchemy import select, text
from app.db.session import async_session
from app.models.user import User
from app.models.settings_master import Employee, Position

async def main():
    async with async_session() as db:
        pos = await db.execute(select(Position).order_by(Position.id.desc()).limit(10))
        print("Latest Positions:")
        for p in pos.scalars().all():
            print(f"ID: {p.id}, Name: {p.name}, Code: {p.code}, Parent: {p.parent_position_id}")
            
if __name__ == '__main__':
    asyncio.run(main())
