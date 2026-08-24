import asyncio
import traceback
from sqlalchemy import select, text
from app.database import AsyncSessionLocal
from app.models.settings_master import Position, Employee, Office
from app.models.user import Project, Role
from sqlalchemy.orm import aliased
from sqlalchemy.sql import func

async def test_list_positions():
    async with AsyncSessionLocal() as db:
        try:
            ParentPosition = aliased(Position)
            q = (
                select(Position, Project.name, Office.name, ParentPosition.name, Role.name, Role.code)
                .join(Project, Position.project_id == Project.id, isouter=True)
                .join(Office, Position.office_id == Office.id, isouter=True)
                .join(ParentPosition, Position.parent_position_id == ParentPosition.id, isouter=True)
                .join(Role, Position.role_id == Role.id, isouter=True)
            )
            count_q = select(func.count(Position.id))
            
            q = q.order_by(Position.name.asc()).offset(0).limit(500)
            
            rows = (await db.execute(q)).all()
            total = await db.scalar(count_q)
            print(f"Success! Total: {total}, fetched {len(rows)} rows.")
            for row in rows[:5]:
                print(row[0].name)
        except Exception as e:
            print("Error executing query:")
            traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_list_positions())
