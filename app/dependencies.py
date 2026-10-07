from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Admin


async def require_admin(request: Request, db: AsyncSession = Depends(get_db)) -> int:
    """
    Equivalent of every PHP endpoint's `empty($_SESSION['admin_id'])` guard,
    plus a live status check: an admin's status (Waiting Approval / Approved
    / Blocked) is re-checked against the DB on every request, not just at
    login, so blocking an admin takes effect immediately even if they're
    already mid-session - not just the next time they'd otherwise log in.
    """
    admin_id = request.session.get("admin_id")
    if not admin_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")

    admin = await db.get(Admin, admin_id)
    if not admin or admin.status != "Approved":
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your admin access is no longer active. Please log in again.",
        )
    return admin_id


async def require_superadmin(admin_id: int = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> int:
    """Same as require_admin, plus role == 'superadmin'. Used for approving/blocking other admins."""
    admin = await db.get(Admin, admin_id)
    if not admin or admin.role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superadmin access required.")
    return admin_id


def require_user(request: Request) -> int:
    """Equivalent of `empty($_SESSION['user_id'])` guard (user_routes.php style)."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized. Please log in.")
    return user_id


def require_pending_login(request: Request) -> int:
    """
    Between password-check and OTP-verify: username/password were already
    confirmed correct (that's what sets this), but the session is NOT yet
    authenticated - require_user still rejects it, since only a verified
    OTP promotes this to a real session (sets 'user_id'). Used by the OTP
    verify/resend endpoints.
    """
    pending_user_id = request.session.get("pending_user_id")
    if not pending_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No login in progress. Please log in again.",
        )
    return pending_user_id


async def require_user_or_admin(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """
    user_routes.php allows EITHER a logged-in commuter OR a logged-in admin.
    Returns whichever is present so callers can branch if needed. The admin
    branch gets the same live status check require_admin does.
    """
    user_id = request.session.get("user_id")
    admin_id = request.session.get("admin_id")

    if admin_id:
        admin = await db.get(Admin, admin_id)
        if not admin or admin.status != "Approved":
            admin_id = None  # fall through to "neither" below if no user_id either

    if not user_id and not admin_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User session required. Please log in.",
        )
    return {"user_id": user_id, "admin_id": admin_id}