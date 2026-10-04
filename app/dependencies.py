from fastapi import HTTPException, Request, status


def require_admin(request: Request) -> int:
    """Equivalent of every PHP endpoint's `empty($_SESSION['admin_id'])` guard."""
    admin_id = request.session.get("admin_id")
    if not admin_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    return admin_id


def require_user(request: Request) -> int:
    """Equivalent of `empty($_SESSION['user_id'])` guard (user_routes.php style)."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized. Please log in.")
    return user_id


def require_user_or_admin(request: Request) -> dict:
    """
    user_routes.php allows EITHER a logged-in commuter OR a logged-in admin.
    Returns whichever is present so callers can branch if needed.
    """
    user_id = request.session.get("user_id")
    admin_id = request.session.get("admin_id")
    if not user_id and not admin_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User session required. Please log in.",
        )
    return {"user_id": user_id, "admin_id": admin_id}
