from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.master import Employee, Position
from app.models.user import Role, User, UserRole


async def sync_user_position_role(db: AsyncSession, user: User) -> Role | None:
    """Ensure a login user acts as the role assigned to their employee position."""
    if not user or not user.employee_id:
        return None

    role = (
        await db.execute(
            select(Role)
            .join(Position, Position.role_id == Role.id)
            .join(Employee, Employee.position_id == Position.id)
            .where(Employee.id == user.employee_id, Role.is_active == True)  # noqa: E712
        )
    ).scalar_one_or_none()

    # Check if the user has super_admin or admin roles assigned
    assigned_admin_roles = (
        await db.execute(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id, Role.is_active == True)
            .where(Role.code.in_({"super_admin", "admin"}))
        )
    ).scalars().all()

    if assigned_admin_roles:
        # Ensure the position role is added to UserRole table so they can switch to it if desired
        if role:
            existing = (
                await db.execute(
                    select(UserRole).where(
                        UserRole.user_id == user.id,
                        UserRole.role_id == role.id,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(UserRole(user_id=user.id, role_id=role.id))
                await db.flush()

        # Respect active_role_id if set, otherwise default to their admin/super_admin role
        current_active = None
        if user.active_role_id is not None:
            current_active = (
                await db.execute(
                    select(Role).where(Role.id == user.active_role_id)
                )
            ).scalar_one_or_none()

        if current_active is None:
            super_admin_role = next((r for r in assigned_admin_roles if r.code == "super_admin"), None)
            admin_role = next((r for r in assigned_admin_roles if r.code == "admin"), None)
            user.active_role_id = (super_admin_role or admin_role).id
            await db.flush()
            return super_admin_role or admin_role

        return current_active

    if role is None:
        return None

    existing = (
        await db.execute(
            select(UserRole).where(
                UserRole.user_id == user.id,
                UserRole.role_id == role.id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(UserRole(user_id=user.id, role_id=role.id))
        await db.flush()

    if user.active_role_id is not None:
        valid_role = (
            await db.execute(
                select(UserRole).where(
                    UserRole.user_id == user.id,
                    UserRole.role_id == user.active_role_id,
                )
            )
        ).scalar_one_or_none()
        
        if valid_role is not None:
            current_active = (
                await db.execute(select(Role).where(Role.id == user.active_role_id))
            ).scalar_one_or_none()
            if current_active is not None:
                return current_active

    if user.active_role_id != role.id:
        user.active_role_id = role.id

    await db.flush()
    return role
