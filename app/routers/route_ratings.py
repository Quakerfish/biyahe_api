from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_user
from app.models import Route, RouteRating
from app.schemas import RouteRatingIn

router = APIRouter(prefix="/api/routes/{route_id}/ratings", tags=["route-ratings"])


@router.get("")
async def get_route_ratings(
    route_id: int, user_id: int = Depends(require_user), db: AsyncSession = Depends(get_db)
):
    route = await db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found.")

    agg = (
        await db.execute(
            select(
                func.count(RouteRating.rated_by_user_id),
                func.avg(RouteRating.route_accuracy_rating),
                func.avg(RouteRating.fare_accuracy_rating),
            ).where(RouteRating.route_id == route_id)
        )
    ).first()
    rating_count, avg_route_accuracy, avg_fare_accuracy = agg

    my_rating = await db.get(RouteRating, {"route_id": route_id, "rated_by_user_id": user_id})

    return {
        "success": True,
        "route_id": route_id,
        "rating_count": rating_count or 0,
        "average_route_accuracy": round(float(avg_route_accuracy), 2) if avg_route_accuracy is not None else None,
        "average_fare_accuracy": round(float(avg_fare_accuracy), 2) if avg_fare_accuracy is not None else None,
        "my_rating": (
            {
                "route_accuracy_rating": my_rating.route_accuracy_rating,
                "fare_accuracy_rating": my_rating.fare_accuracy_rating,
                "comment": my_rating.comment,
                "date_created": my_rating.date_created,
                "date_updated": my_rating.date_updated,
            }
            if my_rating
            else None
        ),
    }


@router.post("", status_code=201)
async def rate_route(
    route_id: int,
    payload: RouteRatingIn,
    user_id: int = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    route = await db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found.")

    now = datetime.now(timezone.utc)

    # Upsert: one rating per user per route - re-rating overwrites the
    # existing row (and bumps date_updated) rather than creating a second
    # one, so the aggregate always reflects each rider's most current
    # assessment, not every rating they've ever left.
    stmt = (
        pg_insert(RouteRating)
        .values(
            route_id=route_id,
            rated_by_user_id=user_id,
            route_accuracy_rating=payload.route_accuracy_rating,
            fare_accuracy_rating=payload.fare_accuracy_rating,
            comment=payload.comment,
            date_updated=now,
        )
        .on_conflict_do_update(
            index_elements=["route_id", "rated_by_user_id"],
            set_={
                "route_accuracy_rating": payload.route_accuracy_rating,
                "fare_accuracy_rating": payload.fare_accuracy_rating,
                "comment": payload.comment,
                "date_updated": now,
            },
        )
    )
    await db.execute(stmt)
    await db.commit()

    return {"success": True, "message": "Rating saved."}