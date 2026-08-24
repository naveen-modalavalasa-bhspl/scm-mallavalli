import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.user import Permission, Role, RolePermission

async def main():
    async with AsyncSessionLocal() as db:
        # Check if permission exists
        perm_res = await db.execute(
            select(Permission).where(
                Permission.module == 'system',
                Permission.action == 'view_all',
                Permission.resource == 'data'
            )
        )
        perm = perm_res.scalar_one_or_none()
        
        if not perm:
            print("Adding 'system.view_all.data' permission...")
            perm = Permission(
                module='system',
                action='view_all',
                resource='data',
                description='Grants global visibility across all warehouses and data scopes'
            )
            db.add(perm)
            await db.flush()
        else:
            print("Permission 'system.view_all.data' already exists.")
            
        # Map to scm_head and scm_incharge
        roles_res = await db.execute(select(Role).where(Role.code.in_(['scm_head', 'scm_incharge'])))
        roles = roles_res.scalars().all()
        
        for role in roles:
            # Check if mapping exists
            rp_res = await db.execute(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == perm.id
                )
            )
            rp = rp_res.scalar_one_or_none()
            if not rp:
                print(f"Mapping permission to role '{role.code}'...")
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))
            else:
                print(f"Role '{role.code}' already has this permission.")
                
        await db.commit()
        print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
