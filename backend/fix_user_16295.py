import asyncio
from sqlalchemy import update
from app.database import AsyncSessionLocal
from app.models.user import User

async def main():
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(User)
            .where(User.username == 'hr-emp-16295')
            .values(active_role_id=68)
        )
        await db.commit()
        print("Updated active_role_id to 68 (SCM HEAD)")

if __name__ == "__main__":
    asyncio.run(main())
