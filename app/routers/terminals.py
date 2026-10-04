from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models import Terminal
from app.schemas import TerminalIn

router = APIRouter(prefix="/api/terminals", tags=["terminals"])


@router.get("")
async def list_terminals(admin_id: int = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Terminal).order_by(Terminal.terminal_name.asc()))).scalars().all()
    return [
        {
            "terminal_id": t.terminal_id,
            "terminal_name": t.terminal_name,
            "latitude": t.latitude,
            "longitude": t.longitude,
        }
        for t in rows
    ]


@router.post("", status_code=201)
async def create_terminal(
    payload: TerminalIn, admin_id: int = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    terminal = Terminal(
        terminal_name=payload.terminal_name, latitude=payload.latitude, longitude=payload.longitude
    )
    db.add(terminal)
    await db.commit()
    await db.refresh(terminal)
    return {
        "terminal_id": terminal.terminal_id,
        "terminal_name": terminal.terminal_name,
        "latitude": terminal.latitude,
        "longitude": terminal.longitude,
    }


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
    await db.commit()

    return {
        "success": True,
        "terminal_id": terminal.terminal_id,
        "terminal_name": terminal.terminal_name,
        "latitude": terminal.latitude,
        "longitude": terminal.longitude,
    }


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
