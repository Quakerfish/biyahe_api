from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import require_user_or_admin
from app.models import Route, Terminal

router = APIRouter(prefix="/api/commuter-routes", tags=["commuter-routes"])


@router.get("")
async def commuter_routes(
    type: str | None = Query(default=None),
    id: int | None = Query(default=None),
    _session=Depends(require_user_or_admin),
    db: AsyncSession = Depends(get_db),
):
    # Option A: terminals list (?type=terminals)
    if type == "terminals":
        rows = (await db.execute(select(Terminal).order_by(Terminal.terminal_name.asc()))).scalars().all()
        return {
            "success": True,
            "terminals": [
                {
                    "terminal_id": t.terminal_id,
                    "terminal_name": t.terminal_name,
                    "latitude": t.latitude,
                    "longitude": t.longitude,
                    "status": t.status,
                    "description": t.description,
                    "image_url": t.image_url,
                }
                for t in rows
            ],
        }

    # Option B: single active route with waypoints (?id=123)
    if id:
        route = await db.scalar(
            select(Route)
            .options(
                selectinload(Route.origin), selectinload(Route.destination), selectinload(Route.waypoints)
            )
            .where(Route.route_id == id, Route.status == "Active")
        )
        if not route:
            raise HTTPException(status_code=404, detail="Active route not found.")

        return {
            "success": True,
            "route_id": route.route_id,
            "route_code": route.route_code,
            "vehicle_type": route.vehicle_type,
            "base_fare": float(route.base_fare) if route.base_fare is not None else None,
            "description": route.description,
            "origin": {
                "terminal_id": route.origin.terminal_id,
                "terminal_name": route.origin.terminal_name,
                "latitude": route.origin.latitude,
                "longitude": route.origin.longitude,
            },
            "destination": {
                "terminal_id": route.destination.terminal_id,
                "terminal_name": route.destination.terminal_name,
                "latitude": route.destination.latitude,
                "longitude": route.destination.longitude,
            },
            "waypoints": [
                {"sequence_no": wp.sequence_no, "latitude": wp.latitude, "longitude": wp.longitude}
                for wp in route.waypoints
            ],
        }

    # Option C: all active routes
    rows = (
        await db.execute(
            select(Route)
            .options(selectinload(Route.origin), selectinload(Route.destination))
            .where(Route.status == "Active")
            .order_by(Route.route_code.asc())
        )
    ).scalars().all()

    return {
        "success": True,
        "routes": [
            {
                "route_id": r.route_id,
                "route_code": r.route_code,
                "vehicle_type": r.vehicle_type,
                "origin_terminal_id": r.origin_terminal_id,
                "destination_terminal_id": r.destination_terminal_id,
                "origin_name": r.origin.terminal_name,
                "destination_name": r.destination.terminal_name,
                "base_fare": float(r.base_fare) if r.base_fare is not None else None,
            }
            for r in rows
        ],
    }