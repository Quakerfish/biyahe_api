import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models import Admin
from app.schemas import AdminOut, AdminProfileUpdateIn, AdminLoginIn, AdminSignupIn
from app.security import hash_password, verify_password

router = APIRouter(prefix="/api/admin", tags=["admin-auth"])


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def admin_signup(payload: AdminSignupIn, db: AsyncSession = Depends(get_db)):
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    existing = await db.scalar(
        select(Admin).where(
            or_(Admin.admin_username == payload.username, Admin.admin_email == payload.email)
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Username or email already exists.")

    # status/role default to "Waiting Approval"/"admin" (see models.py) - a
    # superadmin has to approve the account before it can log in.
    admin = Admin(
        admin_username=payload.username,
        admin_email=payload.email,
        admin_password=hash_password(payload.password),
    )
    db.add(admin)
    await db.commit()

    return {
        "success": True,
        "message": "Admin account created. A superadmin needs to approve it before you can log in.",
    }


@router.post("/login")
async def admin_login(payload: AdminLoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    admin = await db.scalar(select(Admin).where(Admin.admin_username == payload.username))

    if not admin or not verify_password(payload.password, admin.admin_password):
        await asyncio.sleep(0.3)  # mirrors the PHP usleep() brute-force mitigation
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    # Enforce the approval workflow - correct credentials alone aren't
    # enough once status matters.
    if admin.status == "Waiting Approval":
        raise HTTPException(
            status_code=403, detail="Your account is still waiting for a superadmin to approve it."
        )
    if admin.status == "Blocked":
        raise HTTPException(status_code=403, detail="Your account has been blocked.")

    # Session fixation protection: rotate the session.
    request.session.clear()
    request.session["admin_id"] = admin.admin_id
    request.session["admin_uuid"] = str(admin.admin_uuid)
    request.session["admin_username"] = admin.admin_username

    return {
        "success": True,
        "message": "Login successful.",
        "admin": {
            "admin_id": admin.admin_id,
            "admin_uuid": admin.admin_uuid,
            "username": admin.admin_username,
            "email": admin.admin_email,
            "status": admin.status,
            "role": admin.role,
        },
    }


@router.get("/profile")
async def get_admin_profile(
    admin_id: int = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    admin = await db.get(Admin, admin_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found.")

    return {
        "success": True,
        "admin": {
            "admin_id": admin.admin_id,
            "admin_uuid": admin.admin_uuid,
            "username": admin.admin_username,
            "email": admin.admin_email,
            "status": admin.status,
            "role": admin.role,
        },
    }


@router.put("/profile")
async def update_admin_profile(
    payload: AdminProfileUpdateIn,
    request: Request,
    admin_id: int = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    collision = await db.scalar(
        select(Admin).where(
            or_(Admin.admin_username == payload.username, Admin.admin_email == payload.email),
            Admin.admin_id != admin_id,
        )
    )
    if collision:
        raise HTTPException(status_code=409, detail="That username or email is already in use.")

    admin = await db.get(Admin, admin_id)
    admin.admin_username = payload.username
    admin.admin_email = payload.email
    await db.commit()

    request.session["admin_username"] = payload.username  # keep session in sync

    return {
        "success": True,
        "message": "Profile updated successfully.",
        "admin": {"admin_id": admin_id, "username": payload.username, "email": payload.email},
    }