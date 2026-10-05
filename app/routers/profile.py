import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from vercel.blob import AsyncBlobClient

from app.database import get_db
from app.dependencies import require_user
from app.models import User
from app.schemas import UserProfileUpdateIn
from app.security import hash_password, verify_password

router = APIRouter(prefix="/api", tags=["user-profile"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

# NOTE ON STORAGE: Vercel's Python functions have no persistent local disk
# (each invocation is a fresh, stateless container), so this no longer writes
# to uploads/avatars/ like upload_profile_image.php did. Instead it uploads
# to Vercel Blob and stores the returned CDN URL directly in
# users.profile_image - that column now holds a full URL, not just a
# filename, so _avatar_url()'s old "rebuild the URL from a filename" step is
# gone; the DB value is already the URL to hand back to clients.
#
# Needs BLOB_READ_WRITE_TOKEN set in the environment (Vercel sets this
# automatically once you create a Blob store and link it to the project;
# for local dev, pull it with `vercel env pull`).


def _safe_avatar_url(profile_image: str | None) -> str | None:
    """
    Some users still have a profile_image value left over from before the
    Vercel Blob migration - the old PHP upload_profile_image.php stored a
    bare filename like "avatar_22_1790818407.jpg", not a URL. That old file
    lived on the old PHP server's local disk, which no longer exists, so
    there's no way to actually recover it. Returning the bare filename
    as-is makes Android's Glide try to load it as a local file path and
    crash (FileNotFoundException) - so treat anything that isn't a real URL
    as "no avatar" instead of returning something unusable.
    """
    if profile_image and profile_image.startswith(("http://", "https://")):
        return profile_image
    return None


# -------------------------------------------------------------- get_profile.php
@router.get("/profile")
async def get_profile(user_id: int = Depends(require_user), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    return {
        "success": True,
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "profile_image": _safe_avatar_url(user.profile_image),
        "date_created": user.date_created,
    }


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"success": True, "message": "Logged out successfully."}


# ------------------------------------------------------------- update_profile.php
# Registered on both PUT (the idiomatic method going forward) and POST (what
# update_profile.php used, so the existing Android app's call keeps working
# unchanged until/unless you update it to PUT). Same handler either way.
@router.put("/profile")
@router.post("/profile")
async def update_profile(
    payload: UserProfileUpdateIn,
    request: Request,
    user_id: int = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    collision = await db.scalar(
        select(User).where(
            or_(User.username == payload.username, User.email == payload.email),
            User.user_id != user_id,
        )
    )
    if collision:
        raise HTTPException(status_code=409, detail="Username or email is already in use.")

    if payload.new_password:
        if not payload.current_password or not verify_password(payload.current_password, user.password):
            raise HTTPException(status_code=401, detail="Current password is incorrect.")
        user.password = hash_password(payload.new_password)

    user.username = payload.username
    user.email = payload.email
    await db.commit()

    request.session["username"] = payload.username

    return {"success": True, "message": "Profile updated successfully!"}


# --------------------------------------------------------- upload_profile_image.php
@router.post("/profile/image")
async def upload_profile_image(
    profile_image: UploadFile,
    user_id: int = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if profile_image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, and WEBP formats are allowed.")

    ext = (profile_image.filename or "").rsplit(".", 1)[-1].lower() or "jpg"
    pathname = f"avatars/avatar_{user_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}.{ext}"

    file_bytes = await profile_image.read()

    async with AsyncBlobClient() as blob:  # reads BLOB_READ_WRITE_TOKEN from env
        uploaded = await blob.put(
            pathname,
            file_bytes,
            access="public",
            content_type=profile_image.content_type,
        )

    user = await db.get(User, user_id)
    user.profile_image = uploaded.url
    await db.commit()

    return {
        "success": True,
        "message": "Profile picture updated successfully.",
        "profile_image": uploaded.url,
    }