import asyncio
from sqlalchemy import select, text
from app.db.session import async_session
from app.models.user import User
from app.models.settings_master import Employee, Position

async def main():
    async with async_session() as db:
        users = await db.execute(select(User).where(User.employee_code.in_(['HR-EMP-15672', 'HR-EMP-07549'])))
        for u in users.scalars().all():
            print(f"User: {u.employee_code}")
            emp = await db.execute(select(Employee).where(Employee.id == u.employee_id))
            emp = emp.scalar_one_or_none()
            if emp:
                pos = await db.execute(select(Position).where(Position.id == emp.position_id))
                pos = pos.scalar_one_or_none()
                if pos:
                    print(f"  Position: {pos.name} (Parent ID: {pos.parent_position_id})")
                    
                    # Trace up hierarchy
                    curr_pos = pos
                    level = 1
                    while curr_pos and curr_pos.parent_position_id:
                        parent = await db.execute(select(Position).where(Position.id == curr_pos.parent_position_id))
                        curr_pos = parent.scalar_one_or_none()
                        if curr_pos:
                            print(f"    Level {level} Manager Position: {curr_pos.name} (ID: {curr_pos.id})")
                            level += 1
                        else:
                            break

if __name__ == '__main__':
    asyncio.run(main())
