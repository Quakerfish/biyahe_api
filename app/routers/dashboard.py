from fastapi import APIRouter, Depends
from sqlalchemy import func, select
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

    landmarks = (await db.execute(select(Landmark))).scalars().all()
    landmark_features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lm.longitude, lm.latitude]},
            "properties": {"id": lm.landmark_id, "name": lm.landmark_name},
        }
        for lm in landmarks
        if lm.latitude is not None and lm.longitude is not None
    ]

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
            "landmarks": {"type": "FeatureCollection", "features": landmark_features},
        },
    }