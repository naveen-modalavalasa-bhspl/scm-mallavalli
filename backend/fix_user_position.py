import asyncio
from sqlalchemy import select, update
from app.database import AsyncSessionLocal
from app.models.settings_master import Employee
from app.models.user import User

async def main():
    async with AsyncSessionLocal() as db:
        # Find the user
        user = (await db.execute(select(User).where(User.username == 'HR-EMP-152454'))).scalar_one_or_none()
        if not user or not user.employee_id:
            print("User or employee_id not found")
            return
            
        print(f"Updating employee {user.employee_id} to position 4479 (SCM Head)")
        await db.execute(
            update(Employee)
            .where(Employee.id == user.employee_id)
            .values(position_id=4479)
        )
        await db.commit()
        print("Update successful!")

if __name__ == "__main__":
    asyncio.run(main())
