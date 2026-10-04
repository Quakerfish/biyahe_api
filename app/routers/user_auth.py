import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.schemas import UserLoginIn, UserSignupIn
from app.security import hash_password, verify_password

router = APIRouter(prefix="/api", tags=["user-auth"])


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(payload: UserSignupIn, db: AsyncSession = Depends(get_db)):
    if payload.password != payload.confirmPassword:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    existing = await db.scalar(
        select(User).where(or_(User.username == payload.username, User.email == payload.email))
    )
    if existing:
        raise HTTPException(status_code=409, detail="Username or email already exists.")

    user = User(
        username=payload.username,
        email=payload.email,
        password=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()

    return {"success": True, "message": "Account created successfully."}


@router.post("/login")
async def login(payload: UserLoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    # Matches login.php: lookup by username OR email in one field.
    user = await db.scalar(
        select(User).where(or_(User.username == payload.username, User.email == payload.username))
    )

    if not user or not verify_password(payload.password, user.password):
        await asyncio.sleep(0.3)
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    request.session["user_id"] = user.user_id
    request.session["username"] = user.username
    request.session["logged_in"] = True

    return {
        "success": True,
        "message": "Login successful.",
        "username": user.username,
        "email": user.email,
    }
