from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import require_admin
from app.models import ActiveStatus, Route, Terminal, Waypoint
from app.schemas import RouteIn

router = APIRouter(prefix="/api/routes", tags=["routes"])


def _serialize_list_item(r: Route) -> dict:
    return {
        "route_id": r.route_id,
        "route_code": r.route_code,
        "vehicle_type": r.vehicle_type,
        "origin_terminal_id": r.origin_terminal_id,
        "destination_terminal_id": r.destination_terminal_id,
        "origin_name": r.origin.terminal_name,
        "destination_name": r.destination.terminal_name,
        "status": r.status,
        "base_fare": float(r.base_fare) if r.base_fare is not None else None,
        "description": r.description,
    }


def _serialize_detail(r: Route) -> dict:
    data = _serialize_list_item(r)
    data["waypoints"] = [
        {"sequence_no": wp.sequence_no, "latitude": wp.latitude, "longitude": wp.longitude}
        for wp in r.waypoints
    ]
    return data


def _fare(value: float | None) -> Decimal | None:
    # asyncpg is strict about NUMERIC parameters - hand it a Decimal, not a float.
    return None if value is None else Decimal(str(value))


async def _require_terminals(db: AsyncSession, origin_id: int, destination_id: int) -> None:
    found = set(
        (
            await db.scalars(
                select(Terminal.terminal_id).where(Terminal.terminal_id.in_([origin_id, destination_id]))
            )
        ).all()
    )
    if origin_id not in found:
        raise HTTPException(status_code=400, detail="The origin terminal does not exist.")
    if destination_id not in found:
        raise HTTPException(status_code=400, detail="The destination terminal does not exist.")


async def _get_route_or_404(db: AsyncSession, route_id: int) -> Route:
    route = await db.scalar(
        select(Route)
        .options(selectinload(Route.origin), selectinload(Route.destination), selectinload(Route.waypoints))
        .where(Route.route_id == route_id)
    )
    if not route:
        raise HTTPException(status_code=404, detail="Route not found.")
    return route


@router.get("")
async def list_routes(admin_id: int = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(Route)
            .options(selectinload(Route.origin), selectinload(Route.destination))
            .order_by(Route.route_code.asc())
        )
    ).scalars().all()
    return [_serialize_list_item(r) for r in rows]


@router.get("/{route_id}")
async def get_route(route_id: int, admin_id: int = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    route = await _get_route_or_404(db, route_id)
    return _serialize_detail(route)


@router.post("", status_code=201)
async def create_route(
    payload: RouteIn, admin_id: int = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    await _require_terminals(db, payload.origin_terminal_id, payload.destination_terminal_id)

    route = Route(
        created_by_admin_id=admin_id,
        origin_terminal_id=payload.origin_terminal_id,
        destination_terminal_id=payload.destination_terminal_id,
        route_code=payload.route_code,
        vehicle_type=payload.vehicle_type,
        status=ActiveStatus(payload.status),
        base_fare=_fare(payload.base_fare),
        description=payload.description,
    )
    route.waypoints = [
        Waypoint(sequence_no=wp.sequence_no, latitude=wp.latitude, longitude=wp.longitude)
        for wp in payload.waypoints
    ]
    db.add(route)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Could not save the route. Check the terminals and values you entered.")
    await db.refresh(route)

    return {"success": True, "route_id": route.route_id}


@router.put("/{route_id}")
async def update_route(
    route_id: int,
    payload: RouteIn,
    admin_id: int = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    route = await db.scalar(
        select(Route).options(selectinload(Route.waypoints)).where(Route.route_id == route_id)
    )
    if not route:
        raise HTTPException(status_code=404, detail="Route not found.")

    await _require_terminals(db, payload.origin_terminal_id, payload.destination_terminal_id)

    route.origin_terminal_id = payload.origin_terminal_id
    route.destination_terminal_id = payload.destination_terminal_id
    route.route_code = payload.route_code
    route.vehicle_type = payload.vehicle_type
    route.status = ActiveStatus(payload.status)
    route.base_fare = _fare(payload.base_fare)
    route.description = payload.description

    route.waypoints.clear()
    route.waypoints = [
        Waypoint(sequence_no=wp.sequence_no, latitude=wp.latitude, longitude=wp.longitude)
        for wp in payload.waypoints
    ]

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Could not save the route. Check the terminals and values you entered.")
    return {"success": True, "route_id": route_id}


@router.delete("/{route_id}")
async def delete_route(route_id: int, admin_id: int = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    route = await db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found.")

    await db.delete(route)  # cascades to waypoints via relationship(cascade="all, delete-orphan")
    await db.commit()

    return {
        "success": True,
        "message": "Route and its waypoints were successfully deleted.",
        "deleted_route_id": route_id,
    }