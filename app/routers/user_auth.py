import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import require_pending_login
from app.models import LoginOtp, PasswordResetOtp, User
from app.otp_service import (
    EmailSendError,
    codes_match,
    expiry_time,
    generate_code,
    hash_code,
    is_expired,
    mask_email,
    now_utc,
    seconds_since,
    send_code_email,
)
from app.schemas import (
    ForgotPasswordIn,
    OtpVerifyIn,
    ResetPasswordIn,
    UserLoginIn,
    UserSignupIn,
)
from app.security import hash_password, verify_password

router = APIRouter(prefix="/api", tags=["user-auth"])

LOGIN = "login"
RESET = "reset"

BAD_CODE = "Invalid or expired code."


async def _issue_code(db: AsyncSession, model, user: User, purpose: str) -> None:
    """Create/replace the single pending code row for this user and email it.
    The row is only kept if the email actually went out."""
    code = generate_code()
    row = await db.get(model, user.user_id)
    if row is None:
        row = model(user_id=user.user_id)
        db.add(row)
    row.otp_code = hash_code(user.user_id, purpose, code)
    row.expires_at = expiry_time()
    row.attempt_count = 0
    row.date_created = now_utc()
    await db.flush()

    try:
        await send_code_email(user.email, code, purpose)
    except EmailSendError:
        await db.rollback()
        raise HTTPException(status_code=502, detail="Couldn't send the email. Please try again shortly.")
    await db.commit()


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


# --------------------------------------------------------------- login + OTP
@router.post("/login")
async def login(payload: UserLoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    """Step 1 of 2: check the password, email a code. Does NOT log the user in."""
    user = await db.scalar(
        select(User).where(or_(User.username == payload.username, User.email == payload.username))
    )

    if not user or not verify_password(payload.password, user.password):
        await asyncio.sleep(0.3)
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    # Start from a clean session: password is right, but nothing is authenticated yet.
    request.session.clear()

    await _issue_code(db, LoginOtp, user, LOGIN)
    request.session["pending_user_id"] = user.user_id

    return {
        "success": True,
        "otp_required": True,
        "message": "We sent a 6-digit code to your email.",
        "email": mask_email(user.email),
        "resend_cooldown_seconds": settings.OTP_RESEND_COOLDOWN_SECONDS,
    }


@router.post("/login/verify-otp")
async def verify_login_otp(
    payload: OtpVerifyIn,
    request: Request,
    user_id: int = Depends(require_pending_login),
    db: AsyncSession = Depends(get_db),
):
    """Step 2 of 2: the right code promotes the pending session to a real one."""
    otp = await db.get(LoginOtp, user_id)
    if otp is None:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Code expired. Please log in again.")

    if is_expired(otp.expires_at):
        await db.delete(otp)
        await db.commit()
        request.session.clear()
        raise HTTPException(status_code=401, detail="Code expired. Please log in again.")

    if otp.attempt_count >= settings.OTP_MAX_ATTEMPTS:
        await db.delete(otp)
        await db.commit()
        request.session.clear()
        raise HTTPException(status_code=429, detail="Too many wrong codes. Please log in again.")

    if not codes_match(otp.otp_code, user_id, LOGIN, payload.code):
        otp.attempt_count += 1
        remaining = settings.OTP_MAX_ATTEMPTS - otp.attempt_count
        if remaining <= 0:
            await db.delete(otp)
            await db.commit()
            request.session.clear()
            raise HTTPException(status_code=429, detail="Too many wrong codes. Please log in again.")
        await db.commit()
        await asyncio.sleep(0.3)
        raise HTTPException(
            status_code=401,
            detail=f"Invalid code. {remaining} attempt{'s' if remaining != 1 else ''} left.",
        )

    user = await db.get(User, user_id)
    await db.delete(otp)  # single use
    await db.commit()
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Account not found. Please log in again.")

    request.session.clear()
    request.session["user_id"] = user.user_id
    request.session["username"] = user.username
    request.session["logged_in"] = True

    return {"success": True, "message": "Verification successful.", "username": user.username}


@router.post("/login/resend-otp")
async def resend_login_otp(
    user_id: int = Depends(require_pending_login),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="No login in progress. Please log in again.")

    existing = await db.get(LoginOtp, user_id)
    if existing is not None:
        wait = settings.OTP_RESEND_COOLDOWN_SECONDS - seconds_since(existing.date_created)
        if wait > 0:
            raise HTTPException(status_code=429, detail=f"Please wait {int(wait) + 1}s before requesting a new code.")

    await _issue_code(db, LoginOtp, user, LOGIN)
    return {
        "success": True,
        "message": "A new code was sent.",
        "resend_cooldown_seconds": settings.OTP_RESEND_COOLDOWN_SECONDS,
    }


# ---------------------------------------------------------- forgot password
@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordIn, db: AsyncSession = Depends(get_db)):
    """
    Emails a reset code. The reply is identical whether or not the email belongs to
    an account, so this can't be used to find out who has one.
    """
    generic = {
        "success": True,
        "message": "If that email has an account, a reset code is on its way.",
        "resend_cooldown_seconds": settings.OTP_RESEND_COOLDOWN_SECONDS,
    }
    user = await db.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    if user is None:
        await asyncio.sleep(0.6)
        return generic

    existing = await db.get(PasswordResetOtp, user.user_id)
    if existing is not None and seconds_since(existing.date_created) < settings.OTP_RESEND_COOLDOWN_SECONDS:
        return generic  # throttled; stay silent so timing doesn't reveal the account

    try:
        await _issue_code(db, PasswordResetOtp, user, RESET)
    except HTTPException:
        # Email service trouble: same generic reply (details are in the server log).
        pass
    return generic


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordIn, db: AsyncSession = Depends(get_db)):
    if payload.newPassword != payload.confirmPassword:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    user = await db.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    otp = await db.get(PasswordResetOtp, user.user_id) if user else None

    if user is None or otp is None:
        await asyncio.sleep(0.6)
        raise HTTPException(status_code=400, detail=BAD_CODE)

    if is_expired(otp.expires_at) or otp.attempt_count >= settings.OTP_MAX_ATTEMPTS:
        await db.delete(otp)
        await db.commit()
        raise HTTPException(status_code=400, detail=BAD_CODE + " Request a new one.")

    if not codes_match(otp.otp_code, user.user_id, RESET, payload.code):
        otp.attempt_count += 1
        if otp.attempt_count >= settings.OTP_MAX_ATTEMPTS:
            await db.delete(otp)
        await db.commit()
        await asyncio.sleep(0.3)
        raise HTTPException(status_code=400, detail=BAD_CODE)

    user.password = hash_password(payload.newPassword)
    await db.execute(delete(PasswordResetOtp).where(PasswordResetOtp.user_id == user.user_id))
    await db.execute(delete(LoginOtp).where(LoginOtp.user_id == user.user_id))  # kill any in-flight login code
    await db.commit()

    return {"success": True, "message": "Password updated. You can log in now."}