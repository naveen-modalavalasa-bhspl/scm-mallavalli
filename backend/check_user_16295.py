import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.user import User, Role, UserRole

async def main():
    async with AsyncSessionLocal() as db:
        users_res = await db.execute(
            select(User).where(User.username.like('%HR-EMP-16295%'))
        )
        users = users_res.scalars().all()
        if not users:
            print("User HR-EMP-16295 not found")
            return
            
        for u in users:
            print(f"User: {u.username}, ID: {u.id}, Active Role ID: {u.active_role_id}, is_active: {u.is_active}")
            roles_res = await db.execute(
                select(Role.name, Role.id, Role.is_active).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == u.id)
            )
            roles = roles_res.all()
            print(f"  Mapped Roles: {roles}")
                
if __name__ == "__main__":
    asyncio.run(main())
