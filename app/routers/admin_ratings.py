from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.database import get_db
from app.dependencies import require_admin
from app.models import Route, RouteRating, Terminal, User

# Read-only moderation view for admins AND superadmins (require_admin lets
# both through). Commuters submit ratings via /api/routes/{id}/ratings.
router = APIRouter(prefix="/api/admin/ratings", tags=["admin-ratings"])

MAX_ROWS = 2000


@router.get("")
async def list_all_ratings(
    admin_id: int = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    origin = aliased(Terminal)
    destination = aliased(Terminal)

    rows = (
        await db.execute(
            select(RouteRating, User.username, Route.route_code, Route.vehicle_type, origin.terminal_name, destination.terminal_name)
            .join(User, User.user_id == RouteRating.rated_by_user_id)
            .join(Route, Route.route_id == RouteRating.route_id)
            .join(origin, origin.terminal_id == Route.origin_terminal_id)
            .join(destination, destination.terminal_id == Route.destination_terminal_id)
            .order_by(RouteRating.date_updated.desc())
            .limit(MAX_ROWS)
        )
    ).all()

    ratings = [
        {
            "route_id": r.route_id,
            "user_id": r.rated_by_user_id,
            "username": username,
            "route_code": route_code,
            "vehicle_type": vehicle_type,
            "origin_name": origin_name,
            "destination_name": destination_name,
            "route_accuracy_rating": r.route_accuracy_rating,
            "fare_accuracy_rating": r.fare_accuracy_rating,
            "comment": r.comment,
            "date_created": r.date_created.isoformat() if r.date_created else None,
            "date_updated": r.date_updated.isoformat() if r.date_updated else None,
        }
        for r, username, route_code, vehicle_type, origin_name, destination_name in rows
    ]

    total = len(ratings)

    def avg(key):
        return round(sum(x[key] for x in ratings) / total, 2) if total else None

    return {
        "success": True,
        "summary": {
            "total": total,
            "average_route_accuracy": avg("route_accuracy_rating"),
            "average_fare_accuracy": avg("fare_accuracy_rating"),
            "with_comments": sum(1 for x in ratings if x["comment"]),
        },
        "ratings": ratings,
    }