import asyncio
from sqlalchemy import text
from app.database import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("DESCRIBE roles"))
        for row in result.all():
            print(row)

if __name__ == "__main__":
    asyncio.run(main())
