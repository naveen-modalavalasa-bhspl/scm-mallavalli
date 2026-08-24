import asyncio
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from app.db.session import async_session
from app.models.indent import Indent
from app.models.approval import ApprovalRequest, ApprovalHistory
from app.models.settings_master import Position

async def main():
    async with async_session() as db:
        print("=== Checking Indent ===")
        ind = await db.execute(select(Indent).where(Indent.indent_number == 'BHSPL/26-27/FA-IND/0000211'))
        indent = ind.scalar_one_or_none()
        if indent:
            print(f"Indent ID: {indent.id}, Status: {indent.status}, Raised By: {indent.raised_by}")
            ar = await db.execute(select(ApprovalRequest).where(ApprovalRequest.document_id == indent.id, ApprovalRequest.document_type == 'indent'))
            request = ar.scalar_one_or_none()
            if request:
                print(f"ApprovalRequest ID: {request.id}, Status: {request.status}, Current Level: {request.current_level}, Total Levels: {request.total_levels}")
                # check history
                history = await db.execute(select(ApprovalHistory).where(ApprovalHistory.request_id == request.id).order_by(ApprovalHistory.id))
                for h in history.scalars().all():
                    print(f"  Level {h.level}: Action {h.action} by {h.action_by} at {h.action_date}")
            else:
                print("No ApprovalRequest found.")
        else:
            print("Indent not found.")

        print("\n=== Checking Positions ===")
        pos = await db.execute(select(Position).order_by(Position.id.desc()).limit(10))
        for p in pos.scalars().all():
            print(f"ID: {p.id}, Name: {p.name}, Code: {p.code}, Parent ID: {p.parent_position_id}")
            
if __name__ == '__main__':
    asyncio.run(main())
