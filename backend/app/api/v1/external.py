from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
import json
from typing import Optional

from app.database import get_db
from app.models.user import User
from app.utils.dependencies import require_api_key_scope, require_stock_balance_scope, require_items_scope

router = APIRouter()

@router.get("/masters/items")
async def get_items(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_items_scope()),
):
    """Get all items (Master Data). Requires 'masters:items:read' or granular scope."""
    from app.models.master import Item, RoleItemPermission
    from app.models.user import UserRole
    
    scopes = []
    if getattr(user, "used_api_key", None) and user.used_api_key.scopes:
        try:
            scopes = json.loads(user.used_api_key.scopes)
        except Exception:
            scopes = []

    stmt = select(Item)
    
    # Granular Scopes Filtering (based on Item Types)
    # Only filter if "masters:items:read" is NOT in scopes
    if "masters:items:read" not in scopes:
        allowed_types = []
        for s in scopes:
            if s.startswith("masters:items:") and s.endswith(":read"):
                item_type = s[len("masters:items:"):-len(":read")]
                allowed_types.append(item_type)
        if allowed_types:
            stmt = stmt.filter(Item.item_type.in_(allowed_types))
        else:
            # If they have no matching granular scopes, return empty results
            stmt = stmt.filter(False)

    linked_ids = getattr(user, "used_api_key", None) and user.used_api_key.linked_user_ids
    if linked_ids:
        if isinstance(linked_ids, str):
            try:
                import json as _json
                linked_ids = _json.loads(linked_ids)
            except Exception:
                linked_ids = []
        if linked_ids:
            stmt = stmt.join(
                UserRole,
                UserRole.user_id.in_(linked_ids)
            ).join(
                RoleItemPermission,
                (RoleItemPermission.role_id == UserRole.role_id) &
                (
                    ((RoleItemPermission.entity_type == "item") & (RoleItemPermission.entity_id == Item.id)) |
                    ((RoleItemPermission.entity_type == "item_category") & (RoleItemPermission.entity_id == Item.category_id))
                )
            )
    
    result = await db.execute(stmt.limit(limit).offset(offset))
    items = result.scalars().unique().all()
    
    return [
        {
            "id": item.id,
            "item_code": item.item_code,
            "name": item.name,
            "description": item.description,
            "item_type": item.item_type,
            "is_active": item.is_active,
        }
        for item in items
    ]

@router.get("/masters/vendors")
async def get_vendors(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_api_key_scope("masters:vendors:read")),
):
    """Get all vendors (Master Data). Requires 'masters:read' scope."""
    from app.models.master import Vendor
    
    result = await db.execute(select(Vendor).limit(limit).offset(offset))
    vendors = result.scalars().all()
    
    return [
        {
            "id": vendor.id,
            "vendor_code": vendor.vendor_code,
            "name": vendor.name,
            "email": vendor.email,
            "phone": vendor.phone,
            "vendor_type": vendor.vendor_type,
            "is_active": vendor.is_active,
        }
        for vendor in vendors
    ]

@router.get("/inventory/stock")
async def get_stock(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_stock_balance_scope()),
):
    """Get stock balances (Inventory Data). Supports general or segregated scopes.
    Returns item_code, item_name, warehouse_name, available_qty, and serial numbers.
    """
    from app.models.stock import StockBalance
    from app.models.master import Item, RoleItemPermission
    from app.models.warehouse import SerialNumber
    from app.models.user import UserRole

    stmt = (
        select(StockBalance)
        .options(
            selectinload(StockBalance.item),
            selectinload(StockBalance.warehouse),
            selectinload(StockBalance.batch),
        )
    )

    # Determine scope filtering
    scopes = []
    if getattr(user, "used_api_key", None) and user.used_api_key.scopes:
        try:
            scopes = json.loads(user.used_api_key.scopes)
        except Exception:
            scopes = []

    is_item_joined = False

    # 1. User Warehouse/Role Item Filtering (if linked_user_ids is present)
    linked_ids = getattr(user, "used_api_key", None) and user.used_api_key.linked_user_ids
    if linked_ids:
        if isinstance(linked_ids, str):
            try:
                import json as _json
                linked_ids = _json.loads(linked_ids)
            except Exception:
                linked_ids = []
        if linked_ids:
            stmt = stmt.join(Item, Item.id == StockBalance.item_id).join(
                UserRole,
                UserRole.user_id.in_(linked_ids)
            ).join(
                RoleItemPermission,
                (RoleItemPermission.role_id == UserRole.role_id) &
                (
                    ((RoleItemPermission.entity_type == "item") & (RoleItemPermission.entity_id == Item.id)) |
                    ((RoleItemPermission.entity_type == "item_category") & (RoleItemPermission.entity_id == Item.category_id))
                )
            )
            is_item_joined = True

    # 2. Granular Scopes Filtering (based on Item Types only)
    if "inventory:stock-balance:read" not in scopes:
        allowed_types = []
        for s in scopes:
            if s.startswith("inventory:stock-balance:") and s.endswith(":read"):
                item_type = s[len("inventory:stock-balance:"):-len(":read")]
                allowed_types.append(item_type)

        if allowed_types:
            if not is_item_joined:
                stmt = stmt.join(Item, Item.id == StockBalance.item_id)
                is_item_joined = True
            stmt = stmt.filter(Item.item_type.in_(allowed_types))
        else:
            if not is_item_joined:
                stmt = stmt.join(Item, Item.id == StockBalance.item_id)
            stmt = stmt.filter(False)

    result = await db.execute(stmt.limit(limit).offset(offset))
    stock_balances = result.scalars().unique().all()

    # Gather serial numbers for each (item_id, warehouse_id, bin_id, batch_id) tuple
    sn_map: dict = {}
    item_wh_pairs = list({
        (sb.item_id, sb.warehouse_id, sb.bin_id, sb.batch_id)
        for sb in stock_balances
    })
    if item_wh_pairs:
        sn_stmt = select(SerialNumber).where(
            SerialNumber.status == "available"
        )
        # Build an OR across all (item_id, warehouse_id) combos
        conditions = [
            (SerialNumber.item_id == iid) & (SerialNumber.warehouse_id == wid)
            for iid, wid, _bid, _baid in item_wh_pairs
        ]
        if conditions:
            sn_stmt = sn_stmt.where(or_(*conditions))
        sn_result = await db.execute(sn_stmt)
        for sn in sn_result.scalars().all():
            key = (sn.item_id, sn.warehouse_id)
            sn_map.setdefault(key, []).append(sn.serial_number)

    return [
        {
            "item_code": stock.item.item_code if stock.item else None,
            "item_name": stock.item.name if stock.item else None,
            "item_type": stock.item.item_type if stock.item else None,
            "warehouse_name": stock.warehouse.name if stock.warehouse else None,
            "warehouse_code": stock.warehouse.code if stock.warehouse else None,
            "batch_number": stock.batch.batch_number if stock.batch else None,
            "available_qty": float(stock.available_qty or 0),
            "serial_numbers": sn_map.get((stock.item_id, stock.warehouse_id), []),
        }
        for stock in stock_balances
    ]

@router.get("/indent/acknowledgements")
async def get_indent_acknowledgements(
    indent_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_api_key_scope("indent:acknowledgement:read")),
):
    """Get all indent acknowledgements. Requires 'indent:acknowledgement:read' scope."""
    from app.models.indent import IndentAcknowledgement, IndentAcknowledgementItem, IndentItem
    from sqlalchemy.orm import selectinload
    
    stmt = (
        select(IndentAcknowledgement)
        .options(
            selectinload(IndentAcknowledgement.acknowledger),
            selectinload(IndentAcknowledgement.items).selectinload(IndentAcknowledgementItem.item),
            selectinload(IndentAcknowledgement.items).selectinload(IndentAcknowledgementItem.indent_item).selectinload(IndentItem.uom),
        )
    )
    
    if indent_id is not None:
        stmt = stmt.where(IndentAcknowledgement.indent_id == indent_id)
        
    result = await db.execute(stmt.limit(limit).offset(offset))
    acks = result.scalars().all()
    
    return [
        {
            "id": ack.id,
            "indent_id": ack.indent_id,
            "warehouse_id": ack.warehouse_id,
            "acknowledged_by": ack.acknowledged_by,
            "empcode": ack.employee_code or (ack.acknowledger.employee_code if ack.acknowledger else None),
            "employee_code": ack.employee_code or (ack.acknowledger.employee_code if ack.acknowledger else None),
            "acknowledged_at": ack.acknowledged_at.isoformat() if ack.acknowledged_at else None,
            "received_qty": float(ack.received_qty) if ack.received_qty is not None else 0.0,
            "status": ack.status,
            "remarks": ack.remarks,
            "items": [
                {
                    "id": ai.id,
                    "item_id": ai.item_id,
                    "indent_item_id": ai.indent_item_id,
                    "item_code": ai.item.item_code if ai.item else None,
                    "item_name": ai.item.name if ai.item else None,
                    "uom": (
                        ai.indent_item.uom.name
                        if ai.indent_item and ai.indent_item.uom
                        else None
                    ),
                    "approved_qty": float(ai.indent_item.approved_qty) if ai.indent_item and ai.indent_item.approved_qty is not None else None,
                    "requested_qty": float(ai.indent_item.requested_qty) if ai.indent_item and ai.indent_item.requested_qty is not None else None,
                    "received_qty": float(ai.received_qty) if ai.received_qty is not None else 0.0,
                    "remarks": ai.remarks,
                }
                for ai in (ack.items or [])
            ]
        }
        for ack in acks
    ]


@router.get("/masters/warehouses")
async def get_warehouses(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_api_key_scope("masters:warehouses:read")),
):
    """Get all warehouses. Requires 'masters:warehouses:read' scope."""
    from app.models.warehouse import Warehouse
    result = await db.execute(select(Warehouse).where(Warehouse.is_active == True).limit(limit).offset(offset))
    rows = result.scalars().all()
    return [
        {"id": w.id, "code": w.code, "name": w.name, "type": w.type, "is_active": w.is_active}
        for w in rows
    ]


@router.get("/masters/packaging")
async def get_packaging(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_api_key_scope("masters:packaging:read")),
):
    """Get all packaging types. Requires 'masters:packaging:read' scope."""
    from app.models.master import PackagingType
    result = await db.execute(select(PackagingType).limit(limit).offset(offset))
    rows = result.scalars().all()
    return [
        {"id": r.id, "name": r.name, "code": getattr(r, 'code', None), "is_active": getattr(r, 'is_active', True)}
        for r in rows
    ]


@router.get("/masters/categories")
async def get_categories(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_api_key_scope("masters:categories:read")),
):
    """Get all item categories. Requires 'masters:categories:read' scope."""
    from app.models.master import ItemCategory
    result = await db.execute(select(ItemCategory).limit(limit).offset(offset))
    rows = result.scalars().all()
    return [
        {"id": r.id, "name": r.name, "code": getattr(r, 'code', None), "is_active": getattr(r, 'is_active', True)}
        for r in rows
    ]


@router.get("/masters/uom")
async def get_uom(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_api_key_scope("masters:uom:read")),
):
    """Get all units of measure. Requires 'masters:uom:read' scope."""
    from app.models.master import UnitOfMeasure
    result = await db.execute(select(UnitOfMeasure).limit(limit).offset(offset))
    rows = result.scalars().all()
    return [
        {"id": r.id, "name": r.name, "symbol": getattr(r, 'symbol', None), "is_active": getattr(r, 'is_active', True)}
        for r in rows
    ]


@router.get("/masters/brands")
async def get_brands(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_api_key_scope("masters:brands:read")),
):
    """Get all brands. Requires 'masters:brands:read' scope."""
    from app.models.master import Brand
    result = await db.execute(select(Brand).limit(limit).offset(offset))
    rows = result.scalars().all()
    return [
        {"id": r.id, "name": r.name, "code": getattr(r, 'code', None), "is_active": getattr(r, 'is_active', True)}
        for r in rows
    ]


@router.get("/masters/features")
async def get_features(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_api_key_scope("masters:features:read")),
):
    """Get all features. Requires 'masters:features:read' scope."""
    from app.models.master import Feature
    result = await db.execute(select(Feature).limit(limit).offset(offset))
    rows = result.scalars().all()
    return [
        {"id": r.id, "name": r.name, "is_active": getattr(r, 'is_active', True)}
        for r in rows
    ]


@router.get("/masters/item-types")
async def get_item_types(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_api_key_scope("masters:item-types:read")),
):
    """Get all item types. Requires 'masters:item-types:read' scope."""
    from app.models.master import ItemType
    result = await db.execute(select(ItemType).limit(limit).offset(offset))
    rows = result.scalars().all()
    return [
        {"id": r.id, "name": r.name, "is_active": getattr(r, 'is_active', True)}
        for r in rows
    ]


@router.get("/masters/attributes")
async def get_attributes(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_api_key_scope("masters:attributes:read")),
):
    """Get all item attributes. Requires 'masters:attributes:read' scope."""
    from app.models.master import ItemAttribute
    result = await db.execute(select(ItemAttribute).limit(limit).offset(offset))
    rows = result.scalars().all()
    return [
        {"id": r.id, "name": r.name, "is_active": getattr(r, 'is_active', True)}
        for r in rows
    ]


@router.get("/masters/users")
async def get_users_external(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_api_key_scope("masters:users:read")),
):
    """Get all users. Requires 'masters:users:read' scope."""
    from app.models.user import User as _User
    result = await db.execute(
        select(_User.id, _User.username, _User.email, _User.is_active, _User.employee_id)
        .limit(limit).offset(offset)
    )
    rows = result.all()
    return [
        {"id": r.id, "username": r.username, "email": r.email, "is_active": r.is_active, "employee_id": r.employee_id}
        for r in rows
    ]


@router.get("/inventory/stock-ledger")
async def get_stock_ledger(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_api_key_scope("inventory:stock-ledger:read")),
):
    """Get stock ledger entries. Requires 'inventory:stock-ledger:read' scope."""
    from app.models.stock import StockLedger
    result = await db.execute(select(StockLedger).order_by(StockLedger.id.desc()).limit(limit).offset(offset))
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "item_id": r.item_id,
            "warehouse_id": r.warehouse_id,
            "transaction_type": r.transaction_type,
            "qty_in": float(r.qty_in or 0),
            "qty_out": float(r.qty_out or 0),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]

@router.get("/inventory/vehicle-stock-balance")
async def get_vehicle_stock_balance(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_api_key_scope("inventory:vehicle-stock-balance:read")),
):
    """Get vehicle stock balance. Filters by linked_vehicle_codes if present on the API key."""
    from app.models.stock import VehicleStockBalance
    from sqlalchemy.orm import selectinload
    stmt = select(VehicleStockBalance).options(
        selectinload(VehicleStockBalance.item),
        selectinload(VehicleStockBalance.batch)
    )
    
    linked_vehicles = getattr(user, "used_api_key", None) and user.used_api_key.linked_vehicle_codes
    if linked_vehicles:
        if isinstance(linked_vehicles, str):
            try:
                import json as _json
                linked_vehicles = _json.loads(linked_vehicles)
            except Exception:
                linked_vehicles = []
        if linked_vehicles:
            stmt = stmt.filter(VehicleStockBalance.vehicle_code.in_(linked_vehicles))
            
    result = await db.execute(stmt.limit(limit).offset(offset))
    balances = result.scalars().all()
    
    grouped = {}
    for b in balances:
        if b.vehicle_code not in grouped:
            grouped[b.vehicle_code] = {
                "vehicle_code": b.vehicle_code,
                "vehicle_number": b.vehicle_number,
                "items": []
            }
        grouped[b.vehicle_code]["items"].append({
            "id": b.id,
            "item_name": b.item.name if b.item else None,
            "batch_name": b.batch.batch_number if b.batch else None,
            "qty": float(b.qty or 0),
            "serial_numbers": b.serial_numbers,
            "last_updated": b.last_updated.isoformat() if b.last_updated else None,
        })
        
    return list(grouped.values())


# ─────────────────────────────────────────────────────────────────────────────
# Template Indents
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/indent/template-indents")
async def get_template_indents(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_api_key_scope("indent:template-indents:read")),
):
    """Get template-based indents with full human-readable data.
    Requires 'indent:template-indents:read' scope.
    """
    from app.models.indent import Indent, IndentItem

    stmt = (
        select(Indent)
        .options(
            selectinload(Indent.raiser).selectinload(User.employee),
            selectinload(Indent.project),
            selectinload(Indent.items).selectinload(IndentItem.item),
            selectinload(Indent.items).selectinload(IndentItem.uom),
        )
        .where(Indent.template_id.is_not(None))
        .order_by(Indent.id.desc())
    )

    result = await db.execute(stmt.limit(limit).offset(offset))
    indents = result.scalars().unique().all()

    return [
        {
            "id": indent.id,
            "indent_number": indent.indent_number,
            "indent_date": indent.indent_date.isoformat() if indent.indent_date else None,
            "status": indent.status,
            "indent_type": indent.indent_type,
            "template_name": indent.template_name,
            "template_type": indent.template_type,
            "vehicle_code": indent.vehicle_code,
            "vehicle_number": indent.vehicle_number,
            "project_name": indent.project.name if indent.project else None,
            "raised_by_name": (
                (indent.raiser.employee.name if indent.raiser and indent.raiser.employee else None)
                or (f"{indent.raiser.first_name} {indent.raiser.last_name or ''}".strip() if indent.raiser else None)
                or (indent.raiser.username if indent.raiser else None)
            ),
            "raised_by_employee_code": indent.raiser.employee_code if indent.raiser else None,
            "remarks": indent.remarks,
            "created_at": indent.created_at.isoformat() if indent.created_at else None,
            "items": [
                {
                    "item_code": ii.item.item_code if ii.item else None,
                    "item_name": ii.item.name if ii.item else None,
                    "item_type": ii.item.item_type if ii.item else None,
                    "requested_qty": float(ii.requested_qty) if ii.requested_qty is not None else 0.0,
                    "approved_qty": float(ii.approved_qty) if ii.approved_qty is not None else None,
                    "issued_qty": float(ii.issued_qty) if ii.issued_qty is not None else 0.0,
                    "uom": ii.uom.name if ii.uom else None,
                    "fulfillment_status": ii.fulfillment_status,
                }
                for ii in (indent.items or [])
            ],
        }
        for indent in indents
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Vehicle Issues
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/warehouse/vehicle-issues")
async def get_vehicle_issues(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_api_key_scope("warehouse:vehicle-issues:read")),
):
    """Get vehicle issues with full human-readable data.
    Requires 'warehouse:vehicle-issues:read' scope.
    """
    from app.models.issue import VehicleIssue, VehicleIssueItem

    stmt = (
        select(VehicleIssue)
        .options(
            selectinload(VehicleIssue.warehouse),
            selectinload(VehicleIssue.project),
            selectinload(VehicleIssue.issued_to_user).selectinload(User.employee),
            selectinload(VehicleIssue.issued_by_user).selectinload(User.employee),
            selectinload(VehicleIssue.items).selectinload(VehicleIssueItem.item),
            selectinload(VehicleIssue.items).selectinload(VehicleIssueItem.uom),
            selectinload(VehicleIssue.items).selectinload(VehicleIssueItem.batch),
        )
        .order_by(VehicleIssue.id.desc())
    )

    # Filter by linked_vehicle_codes if present on the API key
    linked_vehicles = getattr(user, "used_api_key", None) and user.used_api_key.linked_vehicle_codes
    if linked_vehicles:
        if isinstance(linked_vehicles, str):
            try:
                import json as _json
                linked_vehicles = _json.loads(linked_vehicles)
            except Exception:
                linked_vehicles = []
        if linked_vehicles:
            stmt = stmt.where(VehicleIssue.vehicle_code.in_(linked_vehicles))

    result = await db.execute(stmt.limit(limit).offset(offset))
    issues = result.scalars().unique().all()

    def _user_name(u):
        """Employee name → first+last → username fallback."""
        if not u:
            return None
        if u.employee and u.employee.name:
            return u.employee.name
        full = f"{u.first_name} {u.last_name or ''}".strip()
        return full or u.username

    def _user_emp_code(u):
        if not u:
            return None
        return u.employee_code or (u.employee.employee_code if u.employee else None)

    return [
        {
            "id": vi.id,
            "issue_number": vi.issue_number,
            "issue_date": vi.issue_date.isoformat() if vi.issue_date else None,
            "status": vi.status,
            "vehicle_code": vi.vehicle_code,
            "vehicle_number": vi.vehicle_number,
            "template_name": vi.template_name,
            "template_type": vi.template_type,
            "remarks": vi.remarks,
            "warehouse_name": vi.warehouse.name if vi.warehouse else None,
            "warehouse_code": vi.warehouse.code if vi.warehouse else None,
            "project_name": vi.project.name if vi.project else None,
            "issued_to_name": _user_name(vi.issued_to_user),
            "issued_to_employee_code": _user_emp_code(vi.issued_to_user),
            "issued_by_name": _user_name(vi.issued_by_user),
            "issued_by_employee_code": _user_emp_code(vi.issued_by_user),
            "created_at": vi.created_at.isoformat() if vi.created_at else None,
            "items": [
                {
                    "item_code": item.item.item_code if item.item else None,
                    "item_name": item.item.name if item.item else None,
                    "item_type": item.item.item_type if item.item else None,
                    "qty": float(item.qty) if item.qty is not None else 0.0,
                    "uom": item.uom.name if item.uom else None,
                    "batch_number": item.batch.batch_number if item.batch else (item.batch_number_text or None),
                    "serial_numbers": item.serial_numbers or [],
                }
                for item in (vi.items or [])
            ],
        }
        for vi in issues
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Material Acknowledgements
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/warehouse/material-acknowledgements")
async def get_material_acknowledgements(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_api_key_scope("warehouse:material-acknowledgements:read")),
):
    """Get material acknowledgements with full human-readable data.
    Requires 'warehouse:material-acknowledgements:read' scope.
    """
    from app.models.issue import MaterialAcknowledgement, MaterialAcknowledgementItem, VehicleIssue

    stmt = (
        select(MaterialAcknowledgement)
        .options(
            selectinload(MaterialAcknowledgement.acknowledger),
            selectinload(MaterialAcknowledgement.vehicle_issue).selectinload(VehicleIssue.warehouse),
            selectinload(MaterialAcknowledgement.items).selectinload(MaterialAcknowledgementItem.item),
        )
        .order_by(MaterialAcknowledgement.id.desc())
    )

    # Filter by linked_vehicle_codes via the linked vehicle issue if present
    linked_vehicles = getattr(user, "used_api_key", None) and user.used_api_key.linked_vehicle_codes
    if linked_vehicles:
        if isinstance(linked_vehicles, str):
            try:
                import json as _json
                linked_vehicles = _json.loads(linked_vehicles)
            except Exception:
                linked_vehicles = []
        if linked_vehicles:
            stmt = stmt.join(
                VehicleIssue, VehicleIssue.id == MaterialAcknowledgement.vehicle_issue_id
            ).where(VehicleIssue.vehicle_code.in_(linked_vehicles))

    result = await db.execute(stmt.limit(limit).offset(offset))
    acks = result.scalars().unique().all()

    return [
        {
            "id": ack.id,
            "acknowledgement_number": ack.acknowledgement_number,
            "acknowledged_at": ack.acknowledged_at.isoformat() if ack.acknowledged_at else None,
            "status": ack.status,
            "remarks": ack.remarks,
            "employee_code": ack.employee_code,
            "acknowledged_by_name": ack.acknowledger.username if ack.acknowledger else None,
            "vehicle_issue_number": ack.vehicle_issue.issue_number if ack.vehicle_issue else None,
            "vehicle_code": ack.vehicle_issue.vehicle_code if ack.vehicle_issue else None,
            "vehicle_number": ack.vehicle_issue.vehicle_number if ack.vehicle_issue else None,
            "warehouse_name": (
                ack.vehicle_issue.warehouse.name
                if ack.vehicle_issue and ack.vehicle_issue.warehouse else None
            ),
            "created_at": ack.created_at.isoformat() if ack.created_at else None,
            "items": [
                {
                    "item_code": ai.item.item_code if ai.item else None,
                    "item_name": ai.item.name if ai.item else None,
                    "item_type": ai.item.item_type if ai.item else None,
                    "received_qty": float(ai.received_qty) if ai.received_qty is not None else 0.0,
                    "serial_numbers": ai.serial_numbers or [],
                    "remarks": ai.remarks,
                }
                for ai in (ack.items or [])
            ],
        }
        for ack in acks
    ]


@router.get("/inventory/vehicle-stock-ledger")
async def get_vehicle_stock_ledger(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_api_key_scope("inventory:vehicle-stock-ledger:read")),
):
    """Get vehicle stock ledger. Filters by linked_vehicle_codes if present on the API key."""
    from app.models.stock import VehicleStockLedger
    from sqlalchemy.orm import selectinload
    stmt = select(VehicleStockLedger).options(
        selectinload(VehicleStockLedger.item),
        selectinload(VehicleStockLedger.batch)
    ).order_by(VehicleStockLedger.id.desc())
    
    linked_vehicles = getattr(user, "used_api_key", None) and user.used_api_key.linked_vehicle_codes
    if linked_vehicles:
        if isinstance(linked_vehicles, str):
            try:
                import json as _json
                linked_vehicles = _json.loads(linked_vehicles)
            except Exception:
                linked_vehicles = []
        if linked_vehicles:
            stmt = stmt.filter(VehicleStockLedger.vehicle_code.in_(linked_vehicles))
            
    result = await db.execute(stmt.limit(limit).offset(offset))
    ledger = result.scalars().all()
    
    grouped = {}
    for l in ledger:
        if l.vehicle_code not in grouped:
            grouped[l.vehicle_code] = {
                "vehicle_code": l.vehicle_code,
                "vehicle_number": l.vehicle_number,
                "transactions": []
            }
        grouped[l.vehicle_code]["transactions"].append({
            "id": l.id,
            "item_name": l.item.name if l.item else None,
            "batch_name": l.batch.batch_number if l.batch else None,
            "transaction_type": l.transaction_type,
            "qty_in": float(l.qty_in or 0),
            "qty_out": float(l.qty_out or 0),
            "posting_date": l.posting_date.isoformat() if l.posting_date else None,
        })
        
    return list(grouped.values())
