import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.blob import upload_blob
from app.database import get_db
from app.dependencies import require_admin
from app.models import Route, Terminal
from app.schemas import TerminalIn

router = APIRouter(prefix="/api/terminals", tags=["terminals"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _serialize(t: Terminal) -> dict:
    return {
        "terminal_id": t.terminal_id,
        "terminal_name": t.terminal_name,
        "latitude": t.latitude,
        "longitude": t.longitude,
        "status": t.status,
        "description": t.description,
        "image_url": t.image_url,
    }


@router.get("")
async def list_terminals(admin_id: int = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Terminal).order_by(Terminal.terminal_name.asc()))).scalars().all()
    return [_serialize(t) for t in rows]


@router.get("/{terminal_id}")
async def get_terminal(
    terminal_id: int, admin_id: int = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    terminal = await db.get(Terminal, terminal_id)
    if not terminal:
        raise HTTPException(status_code=404, detail="Terminal not found.")

    # "Routes going through it" - a join at query time, not a stored
    # column, since it's derived from routes.origin_terminal_id /
    # destination_terminal_id rather than being its own fact to store.
    routes = (
        await db.execute(
            select(Route)
            .options(selectinload(Route.origin), selectinload(Route.destination))
            .where(
                or_(Route.origin_terminal_id == terminal_id, Route.destination_terminal_id == terminal_id)
            )
            .order_by(Route.route_code.asc())
        )
    ).scalars().all()

    data = _serialize(terminal)
    data["routes"] = [
        {
            "route_id": r.route_id,
            "route_code": r.route_code,
            "vehicle_type": r.vehicle_type,
            "origin_name": r.origin.terminal_name,
            "destination_name": r.destination.terminal_name,
            "status": r.status,
        }
        for r in routes
    ]
    return data


@router.post("", status_code=201)
async def create_terminal(
    payload: TerminalIn, admin_id: int = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    terminal = Terminal(
        terminal_name=payload.terminal_name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        status=payload.status,
        description=payload.description,
    )
    db.add(terminal)
    await db.commit()
    await db.refresh(terminal)
    return _serialize(terminal)


@router.put("/{terminal_id}")
async def update_terminal(
    terminal_id: int,
    payload: TerminalIn,
    admin_id: int = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    terminal = await db.get(Terminal, terminal_id)
    if not terminal:
        raise HTTPException(status_code=404, detail="Terminal not found.")

    terminal.terminal_name = payload.terminal_name
    terminal.latitude = payload.latitude
    terminal.longitude = payload.longitude
    terminal.status = payload.status
    terminal.description = payload.description
    await db.commit()

    return {"success": True, **_serialize(terminal)}


@router.post("/{terminal_id}/image")
async def upload_terminal_image(
    terminal_id: int,
    image: UploadFile,
    admin_id: int = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    terminal = await db.get(Terminal, terminal_id)
    if not terminal:
        raise HTTPException(status_code=404, detail="Terminal not found.")

    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, and WEBP formats are allowed.")

    ext = (image.filename or "").rsplit(".", 1)[-1].lower() or "jpg"
    pathname = f"terminals/terminal_{terminal_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}.{ext}"

    file_bytes = await image.read()
    blob_url = await upload_blob(pathname, file_bytes, image.content_type or "application/octet-stream")

    terminal.image_url = blob_url
    await db.commit()

    return {"success": True, "image_url": blob_url}


@router.delete("/{terminal_id}")
async def delete_terminal(
    terminal_id: int, admin_id: int = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    terminal = await db.get(Terminal, terminal_id)
    if not terminal:
        raise HTTPException(status_code=404, detail="Terminal not found.")

    try:
        await db.delete(terminal)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Postgres FK violation - terminal still referenced by a route.
        raise HTTPException(
            status_code=409,
            detail="This terminal is used as an origin or destination on one or more routes. "
            "Update or delete those routes first.",
        )

    return {"success": True, "message": "Terminal deleted.", "deleted_terminal_id": terminal_id}