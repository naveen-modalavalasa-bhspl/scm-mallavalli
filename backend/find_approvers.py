import asyncio
import traceback
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from app.database import AsyncSessionLocal
from app.models.indent import Indent
from app.models.approval import ApprovalRequest, ProjectWorkflowConfig
from app.models.settings_master import Position, Employee
from app.models.user import User

async def get_approvers():
    async with AsyncSessionLocal() as db:
        indents = ['BHSPL/26-27/FA-IND/0000214', 'BHSPL/26-27/FA-IND/0000215']
        
        for indent_num in indents:
            print(f"\n=== Investigating {indent_num} ===")
            ind_row = await db.execute(select(Indent).where(Indent.indent_number == indent_num))
            indent = ind_row.scalar_one_or_none()
            if not indent:
                print("Indent not found.")
                continue
                
            req_row = await db.execute(select(ApprovalRequest).where(ApprovalRequest.document_id == indent.id, ApprovalRequest.document_type == 'indent'))
            req = req_row.scalar_one_or_none()
            if not req:
                print("No approval request found.")
                continue
                
            print(f"Status: {req.status}, Current Level: {req.current_level} of {req.total_levels}")
            if req.status != 'pending':
                print("Request is not pending.")
                continue
                
            # Simulate approval chain
            user_row = await db.execute(select(User).where(User.id == req.requested_by))
            user = user_row.scalar_one_or_none()
            
            emp_row = await db.execute(select(Employee).where(Employee.id == user.employee_id))
            emp = emp_row.scalar_one_or_none()
            
            start_pos_id = emp.position_id if emp else None
            if not start_pos_id:
                print("User/Employee has no position.")
                continue
                
            chain = []
            curr_pos_id = start_pos_id
            while curr_pos_id:
                pos_row = await db.execute(select(Position).where(Position.id == curr_pos_id))
                pos = pos_row.scalar_one_or_none()
                if not pos or not pos.parent_position_id:
                    break
                curr_pos_id = pos.parent_position_id
                
                parent_row = await db.execute(select(Position).where(Position.id == curr_pos_id))
                parent = parent_row.scalar_one_or_none()
                if parent:
                    # check config
                    cfg = None
                    if parent.role_id:
                        cfg_row = await db.execute(select(ProjectWorkflowConfig).where(ProjectWorkflowConfig.project_id == indent.project_id, ProjectWorkflowConfig.role_id == parent.role_id))
                        cfg = cfg_row.scalar_one_or_none()
                    
                    if cfg and cfg.indent_approve:
                        chain.append(parent)
                        
            print(f"Computed Approval Chain Length: {len(chain)}")
            if len(chain) >= req.current_level:
                target_pos = chain[req.current_level - 1]
                print(f"Level {req.current_level} Position: ID {target_pos.id}, Name: {target_pos.name}")
                
                # find employee in this position
                target_emp_row = await db.execute(select(Employee).where(Employee.position_id == target_pos.id))
                target_emp = target_emp_row.scalar_one_or_none()
                if target_emp:
                    print(f"--> Approver Employee Code: {target_emp.employee_code}, Name: {target_emp.name}")
                else:
                    print(f"--> No employee found occupying position ID {target_pos.id}")
            else:
                print("Current level exceeds computed chain.")

if __name__ == '__main__':
    asyncio.run(get_approvers())
