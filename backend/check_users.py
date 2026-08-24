import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.user import User

async def check_users():
    async with AsyncSessionLocal() as db:
        users = ['emp-george-001', 'test']
        for u in users:
            print(f"\n--- Checking User: {u} ---")
            q = select(User).where((User.username == u) | (User.employee_code == u))
            rows = (await db.execute(q)).scalars().all()
            if not rows:
                print("No user found.")
            for r in rows:
                print(f"ID: {r.id}, Username: {r.username}, Employee Code: {r.employee_code}")
                print(f"Is Active: {r.is_active}, Locked Until: {r.locked_until}, Failed Logins: {r.failed_login_attempts}")
                print(f"Password Hash set: {bool(r.password_hash)}")

if __name__ == '__main__':
    asyncio.run(check_users())
