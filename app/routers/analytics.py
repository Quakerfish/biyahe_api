from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models import Admin, Landmark, Route, SavedRoute, Terminal, User, Waypoint

router = APIRouter(prefix="/api", tags=["analytics"])

SIGNUP_TREND_SQL = text(
    """
    SELECT to_char(d.day, 'Dy') AS label,
           to_char(d.day, 'YYYY-MM-DD') AS iso,
           COUNT(u.user_id) AS cnt
    FROM generate_series((CURRENT_DATE - INTERVAL '6 days')::date, CURRENT_DATE::date, INTERVAL '1 day') AS d(day)
    LEFT JOIN users u ON DATE(u.date_created) = d.day
    GROUP BY d.day
    ORDER BY d.day
    """
)

SAVED_TREND_SQL = text(
    """
    SELECT to_char(d.day, 'Dy') AS label,
           to_char(d.day, 'YYYY-MM-DD') AS iso,
           COUNT(sr.route_id) AS cnt
    FROM generate_series((CURRENT_DATE - INTERVAL '6 days')::date, CURRENT_DATE::date, INTERVAL '1 day') AS d(day)
    LEFT JOIN saved_routes sr ON DATE(sr.date_created) = d.day
    GROUP BY d.day
    ORDER BY d.day
    """
)


@router.get("/analytics")
async def analytics(admin_id: int = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    total_users = await db.scalar(select(func.count()).select_from(User))
    total_admins = await db.scalar(select(func.count()).select_from(Admin))
    total_terminals = await db.scalar(select(func.count()).select_from(Terminal))
    total_landmarks = await db.scalar(select(func.count()).select_from(Landmark))
    total_saved = await db.scalar(select(func.count()).select_from(SavedRoute))
    total_waypoints = await db.scalar(select(func.count()).select_from(Waypoint))

    active_routes = await db.scalar(select(func.count()).where(Route.status == "Active"))
    inactive_routes = await db.scalar(select(func.count()).where(Route.status == "Inactive"))
    total_routes = active_routes + inactive_routes
    active_route_pct = round((active_routes / total_routes) * 100, 1) if total_routes > 0 else 0.0

    vehicle_rows = (
        await db.execute(select(Route.vehicle_type, func.count().label("cnt")).group_by(Route.vehicle_type))
    ).all()
    vehicle_breakdown = {"Modern": 0, "Traditional": 0}
    for row in vehicle_rows:
        vehicle_breakdown[row.vehicle_type] = row.cnt

    signup_rows = (await db.execute(SIGNUP_TREND_SQL)).mappings().all()
    saved_rows = (await db.execute(SAVED_TREND_SQL)).mappings().all()

    return {
        "success": True,
        "stats": {
            "total_users": total_users,
            "total_admins": total_admins,
            "total_people": total_users + total_admins,
            "total_routes": total_routes,
            "active_routes": active_routes,
            "inactive_routes": inactive_routes,
            "active_route_pct": active_route_pct,
            "total_terminals": total_terminals,
            "total_landmarks": total_landmarks,
            "total_saved_routes": total_saved,
            "total_waypoints": total_waypoints,
        },
        "user_distribution": {"admins": total_admins, "commuters": total_users},
        "vehicle_breakdown": vehicle_breakdown,
        "trend": {
            "labels": [r["label"] for r in signup_rows],
            "signups": [r["cnt"] for r in signup_rows],
            "saved_routes": [r["cnt"] for r in saved_rows],
        },
    }