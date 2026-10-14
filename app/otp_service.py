"""
OTP helpers + EmailJS sender, used by the login 2FA step and forgot-password.

Why this lives on the server: the EmailJS private key (an access token) used to
be compiled into the Android app, and the 6-digit code was generated *and checked*
on the phone, so anyone could read the code out of the APK/memory and skip the
email entirely. Now the phone never sees the code: the server creates it, emails
it, stores only a keyed hash, and checks what the user types.
"""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings

logger = logging.getLogger("biyahe_api")

EMAILJS_API_URL = "https://api.emailjs.com/api/v1.0/email/send"


class EmailSendError(Exception):
    pass


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def generate_code() -> str:
    """Cryptographically secure 6-digit code (random.randint is not)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(user_id: int, purpose: str, code: str) -> str:
    """
    Keyed hash, bound to the user and the purpose, so a leaked table row can't be
    brute-forced offline without SESSION_SECRET_KEY and a login code can't be
    replayed as a reset code.
    """
    msg = f"{purpose}:{user_id}:{code}".encode()
    return hmac.new(settings.SESSION_SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def codes_match(stored_hash: str, user_id: int, purpose: str, entered: str) -> bool:
    return hmac.compare_digest(stored_hash, hash_code(user_id, purpose, entered))


def expiry_time() -> datetime:
    return now_utc() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)


def seconds_since(moment: datetime | None) -> float:
    if moment is None:
        return 10**9
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (now_utc() - moment).total_seconds()


def is_expired(expires_at: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return now_utc() >= expires_at


def mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    if len(name) <= 2:
        return f"{name[:1]}***@{domain}"
    return f"{name[0]}{'*' * min(len(name) - 2, 6)}{name[-1]}@{domain}"


async def send_code_email(to_email: str, code: str, purpose: str) -> None:
    """purpose: 'login' or 'reset'. Raises EmailSendError on any failure."""
    template_id = settings.EMAILJS_TEMPLATE_ID
    if purpose == "reset" and settings.EMAILJS_RESET_TEMPLATE_ID:
        template_id = settings.EMAILJS_RESET_TEMPLATE_ID

    if not (settings.EMAILJS_SERVICE_ID and template_id and settings.EMAILJS_PUBLIC_KEY):
        logger.error("EmailJS is not configured (missing env vars).")
        raise EmailSendError("Email service is not configured.")

    payload = {
        "service_id": settings.EMAILJS_SERVICE_ID,
        "template_id": template_id,
        "user_id": settings.EMAILJS_PUBLIC_KEY,
        "accessToken": settings.EMAILJS_PRIVATE_KEY,
        "template_params": {
            # Several aliases so the template's "To Email" box works whichever variable
            # name it uses ({{to_email}} is what the shipped templates expect).
            "to_email": to_email,
            "email": to_email,
            "user_email": to_email,
            "to": to_email,
            "reply_to": to_email,
            "passcode": code,
            "expiry_minutes": str(settings.OTP_EXPIRY_MINUTES),
            "purpose": "password reset" if purpose == "reset" else "login verification",
        },
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(EMAILJS_API_URL, json=payload)
    except httpx.HTTPError as exc:
        logger.error("EmailJS request failed: %s", exc)
        raise EmailSendError("Could not reach the email service.") from exc

    if resp.status_code != 200:
        # Log EmailJS's reason (e.g. non-browser API calls disabled) but never the code.
        logger.error("EmailJS rejected the send: %s %s", resp.status_code, resp.text[:200])
        raise EmailSendError("The email service rejected the request.")