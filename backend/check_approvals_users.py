import asyncio
from sqlalchemy import select, text
from app.database import AsyncSessionLocal
from app.models.user import User, Role, UserRole
from app.models.approval import ApprovalWorkflow, ApprovalLevel

async def main():
    async with AsyncSessionLocal() as db:
        users_res = await db.execute(
            select(User).where(User.username.in_(['HR-EMP-152454', 'emp_george_001']))
        )
        users = users_res.scalars().all()
        for u in users:
            print(f"User: {u.username}, ID: {u.id}, Active Role ID: {u.active_role_id}")
            roles_res = await db.execute(
                select(Role.name, Role.id).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == u.id)
            )
            roles = roles_res.all()
            print(f"  Roles mapped in UserRole: {roles}")
            
        print("\n--- Workflows ---")
        wf_res = await db.execute(select(ApprovalWorkflow).where(ApprovalWorkflow.document_type == 'indent', ApprovalWorkflow.is_active == True))
        wfs = wf_res.scalars().all()
        for wf in wfs:
            print(f"Workflow: {wf.name} (ID: {wf.id}, Project: {wf.project_id})")
            levels_res = await db.execute(select(ApprovalLevel).where(ApprovalLevel.workflow_id == wf.id))
            for l in levels_res.scalars().all():
                print(f"  Level {l.level}: Role ID: {l.approver_role_id}, User ID: {l.approver_user_id}")
                
if __name__ == "__main__":
    asyncio.run(main())
