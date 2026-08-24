import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.user import Role

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Role.name, Role.code))
        roles = result.all()
        for r in roles:
            if "scm" in r[0].lower() or "scm" in r[1].lower():
                print(f"Name: {r[0]}, Code: {r[1]}")

if __name__ == "__main__":
    asyncio.run(main())
