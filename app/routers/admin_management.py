from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_superadmin
from app.models import Admin
from app.schemas import AdminRoleUpdateIn, AdminStatusUpdateIn

router = APIRouter(prefix="/api/admin/admins", tags=["admin-management"])


def _serialize(admin: Admin) -> dict:
    return {
        "admin_id": admin.admin_id,
        "admin_uuid": admin.admin_uuid,
        "username": admin.admin_username,
        "email": admin.admin_email,
        "status": admin.status,
        "role": admin.role,
    }


@router.get("")
async def list_admins(
    requesting_admin_id: int = Depends(require_superadmin), db: AsyncSession = Depends(get_db)
):
    """Every admin account, for a superadmin's management view (not just pending ones)."""
    rows = (await db.execute(select(Admin).order_by(Admin.admin_username.asc()))).scalars().all()
    return {"success": True, "admins": [_serialize(a) for a in rows]}


@router.get("/pending")
async def list_pending_admins(
    requesting_admin_id: int = Depends(require_superadmin), db: AsyncSession = Depends(get_db)
):
    rows = (
        await db.execute(
            select(Admin).where(Admin.status == "Waiting Approval").order_by(Admin.admin_username.asc())
        )
    ).scalars().all()
    return {"success": True, "admins": [_serialize(a) for a in rows]}


@router.put("/{target_admin_id}/status")
async def update_admin_status(
    target_admin_id: int,
    payload: AdminStatusUpdateIn,
    requesting_admin_id: int = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    if target_admin_id == requesting_admin_id:
        raise HTTPException(status_code=400, detail="You can't change your own status.")

    admin = await db.get(Admin, target_admin_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found.")

    admin.status = payload.status
    await db.commit()

    return {"success": True, "admin": _serialize(admin)}


@router.put("/{target_admin_id}/role")
async def update_admin_role(
    target_admin_id: int,
    payload: AdminRoleUpdateIn,
    requesting_admin_id: int = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    if target_admin_id == requesting_admin_id:
        raise HTTPException(status_code=400, detail="You can't change your own role.")

    admin = await db.get(Admin, target_admin_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found.")

    admin.role = payload.role
    await db.commit()

    return {"success": True, "admin": _serialize(admin)}