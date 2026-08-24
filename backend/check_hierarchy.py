import asyncio
from sqlalchemy import select, text
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.settings_master import Employee, Position

async def main():
    async with AsyncSessionLocal() as db:
        for uname in ['HR-EMP-152454', 'emp_george_001']:
            u = (await db.execute(select(User).where(User.username == uname))).scalar_one_or_none()
            if not u:
                print(f"User {uname} not found")
                continue
            
            print(f"\nUser: {u.username} (ID: {u.id}, active_role_id: {u.active_role_id})")
            if not u.employee_id:
                print("  No employee_id linked!")
                continue
                
            emp = (await db.execute(select(Employee).where(Employee.id == u.employee_id))).scalar_one_or_none()
            if not emp:
                print(f"  Employee {u.employee_id} not found!")
                continue
                
            print(f"  Employee: {emp.employee_code} (ID: {emp.id}, position_id: {emp.position_id})")
            
            if not emp.position_id:
                print("  No position_id linked to employee!")
                continue
                
            pos = (await db.execute(select(Position).where(Position.id == emp.position_id))).scalar_one_or_none()
            if not pos:
                print(f"  Position {emp.position_id} not found!")
                continue
                
            print(f"  Position: {pos.name} (ID: {pos.id}, role_id: {pos.role_id}, project_id: {pos.project_id}, employee_id: {pos.employee_id})")
            
            # check descendants reporting to this position
            children_res = await db.execute(text("SELECT position_id FROM position_reporting WHERE parent_position_id = :pid"), {"pid": pos.id})
            children = children_res.all()
            print(f"  Direct children in position_reporting: {len(children)}")
            
            # Also check if there are other positions linked directly via employee_id instead of Position master's default
            other_pos = (await db.execute(select(Position).where(Position.employee_id == emp.id))).scalars().all()
            if len(other_pos) > 1 or (len(other_pos) == 1 and other_pos[0].id != pos.id):
                print("  Other positions mapped to this employee:")
                for op in other_pos:
                    print(f"    - {op.name} (ID: {op.id}, role_id: {op.role_id})")

if __name__ == "__main__":
    asyncio.run(main())
