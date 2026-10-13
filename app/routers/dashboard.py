from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models import Admin, Landmark, Route, Terminal, User, Waypoint

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
async def dashboard(admin_id: int = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    total_users = await db.scalar(select(func.count()).select_from(User))
    total_admins = await db.scalar(select(func.count()).select_from(Admin))
    total_terminals = await db.scalar(select(func.count()).select_from(Terminal))
    total_landmarks = await db.scalar(select(func.count()).select_from(Landmark))
    total_waypoints = await db.scalar(select(func.count()).select_from(Waypoint))

    active_routes = await db.scalar(select(func.count()).where(Route.status == "Active"))
    inactive_routes = await db.scalar(select(func.count()).where(Route.status == "Inactive"))
    total_routes = active_routes + inactive_routes

    # Top terminal hubs by how many routes touch them (origin or destination).
    hub_rows = (
        await db.execute(
            select(
                Terminal.terminal_id,
                Terminal.terminal_name,
                func.count(Route.route_id).label("route_count"),
            )
            .outerjoin(
                Route,
                (Route.origin_terminal_id == Terminal.terminal_id)
                | (Route.destination_terminal_id == Terminal.terminal_id),
            )
            .group_by(Terminal.terminal_id, Terminal.terminal_name)
            .order_by(func.count(Route.route_id).desc(), Terminal.terminal_name.asc())
            .limit(6)
        )
    ).all()
    hubs = [
        {"terminal_id": r.terminal_id, "name": r.terminal_name, "route_count": r.route_count}
        for r in hub_rows
    ]

    terminals = (await db.execute(select(Terminal))).scalars().all()
    terminal_features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [t.longitude, t.latitude]},
            "properties": {"id": t.terminal_id, "name": t.terminal_name},
        }
        for t in terminals
        if t.latitude is not None and t.longitude is not None
    ]

    # Active route paths as LineStrings, so the dashboard map can draw every
    # corridor from this single response (no per-route request).
    active = (
        await db.execute(
            select(Route)
            .options(selectinload(Route.waypoints))
            .where(Route.status == "Active")
            .order_by(Route.route_code.asc())
        )
    ).scalars().all()
    route_features = []
    for r in active:
        pts = sorted(r.waypoints, key=lambda w: w.sequence_no)
        coords = [[w.longitude, w.latitude] for w in pts if w.latitude is not None and w.longitude is not None]
        if len(coords) < 2:
            continue
        route_features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {"route_id": r.route_id, "route_code": r.route_code, "waypoints": len(coords)},
            }
        )

    return {
        "success": True,
        "stats": {
            "total_users": total_users,
            "total_admins": total_admins,
            "total_people": total_users + total_admins,
            "total_routes": total_routes,
            "active_routes": active_routes,
            "inactive_routes": inactive_routes,
            "total_terminals": total_terminals,
            "total_landmarks": total_landmarks,
            "total_waypoints": total_waypoints,
        },
        "hubs": hubs,
        "map": {
            "terminals": {"type": "FeatureCollection", "features": terminal_features},
            "routes": {"type": "FeatureCollection", "features": route_features},
        },
    }