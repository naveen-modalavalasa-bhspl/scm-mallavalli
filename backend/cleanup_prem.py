import asyncio
from sqlalchemy import select, update, delete
from app.database import AsyncSessionLocal
from app.models.user import User, UserRole, Role
from app.models.settings_master import Employee

async def main():
    async with AsyncSessionLocal() as db:
        user_res = await db.execute(select(User).where(User.username == 'HR-EMP-152454'))
        user = user_res.scalar_one_or_none()
        if not user:
            print("User HR-EMP-152454 not found")
            return
            
        print(f"User ID: {user.id}, Employee ID: {user.employee_id}")
        
        # 1. Undo the position_id hack
        if user.employee_id:
            await db.execute(
                update(Employee)
                .where(Employee.id == user.employee_id)
                .values(position_id=None)
            )
            print("Set position_id = None for employee")
            
        # 2. Check current roles
        roles_res = await db.execute(
            select(Role.id, Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id)
        )
        roles = roles_res.all()
        print(f"Current roles: {roles}")
        
        # The user said he is only assigned to Warehouse Incharge in DB.
        # But sync_user_position_role might have auto-assigned SCM HEAD.
        # Let's remove SCM HEAD (id=68) if it exists, so we respect what's truly assigned.
        scm_head_role_id = None
        wh_incharge_role_id = None
        for r in roles:
            if 'SCM HEAD' in r[1].upper():
                scm_head_role_id = r[0]
            if 'INCHARGE' in r[1].upper():
                wh_incharge_role_id = r[0]
                
        if scm_head_role_id:
            await db.execute(
                delete(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == scm_head_role_id)
            )
            print(f"Deleted SCM HEAD role ({scm_head_role_id}) from user_roles")
            
            # If active_role_id was SCM HEAD, reset it
            if user.active_role_id == scm_head_role_id:
                new_active = wh_incharge_role_id if wh_incharge_role_id else None
                user.active_role_id = new_active
                print(f"Reset active_role_id to {new_active}")

        await db.commit()
        print("Done cleaning up.")

if __name__ == "__main__":
    asyncio.run(main())
