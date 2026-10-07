from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import require_user
from app.models import Route, SavedRoute
from app.schemas import SavedRouteOut

router = APIRouter(prefix="/api/saved-routes", tags=["saved-routes"])


@router.get("")
async def list_saved_routes(user_id: int = Depends(require_user), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(SavedRoute)
            .options(
                selectinload(SavedRoute.route).selectinload(Route.origin),
                selectinload(SavedRoute.route).selectinload(Route.destination),
            )
            .where(SavedRoute.saved_by_user_id == user_id)
            .order_by(SavedRoute.date_created.desc())
        )
    ).scalars().all()

    return [
        {
            "route_id": sr.route.route_id,
            "route_code": sr.route.route_code,
            "vehicle_type": sr.route.vehicle_type,
            "origin_terminal_id": sr.route.origin_terminal_id,
            "destination_terminal_id": sr.route.destination_terminal_id,
            "origin_name": sr.route.origin.terminal_name,
            "destination_name": sr.route.destination.terminal_name,
            "status": sr.route.status,
            "base_fare": float(sr.route.base_fare) if sr.route.base_fare is not None else None,
            "date_saved": sr.date_created,
        }
        for sr in rows
    ]


@router.post("", status_code=201)
async def save_route(
    route_id: int, user_id: int = Depends(require_user), db: AsyncSession = Depends(get_db)
):
    route = await db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=400, detail="route_id must be a valid integer.")

    stmt = (
        pg_insert(SavedRoute)
        .values(saved_by_user_id=user_id, route_id=route_id)
        .on_conflict_do_nothing(index_elements=["saved_by_user_id", "route_id"])
        .returning(SavedRoute.route_id, SavedRoute.date_created)
    )
    result = (await db.execute(stmt)).first()
    await db.commit()

    return {
        "success": True,
        "route_id": result.route_id if result else route_id,
        "date_saved": result.date_created if result else None,
    }


@router.delete("")
async def unsave_route(
    route_id: int, user_id: int = Depends(require_user), db: AsyncSession = Depends(get_db)
):
    saved = await db.get(SavedRoute, {"saved_by_user_id": user_id, "route_id": route_id})
    if saved:
        await db.delete(saved)
        await db.commit()

    return {"success": True, "message": "Route removed from saved routes.", "route_id": route_id}