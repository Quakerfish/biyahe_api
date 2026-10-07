import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Admin(Base):
    __tablename__ = "admins"

    admin_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Uuid(as_uuid=False): your actual Supabase column is a native Postgres
    # `uuid` type (not varchar), which asyncpg decodes as a Python UUID
    # object - and UUID isn't JSON-serializable, which breaks session cookie
    # encoding. as_uuid=False tells SQLAlchemy to hand it to app code as a
    # plain str instead.
    admin_uuid: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), unique=True, default=lambda: str(uuid.uuid4())
    )
    admin_username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    admin_password: Mapped[str] = mapped_column(String(255))
    admin_email: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    # "Waiting Approval" | "Approved" | "Blocked" - gates login entirely,
    # checked fresh on every admin-authenticated request (not just at
    # login), so blocking an admin takes effect immediately even if they're
    # already mid-session.
    status: Mapped[str] = mapped_column(String(20), default="Waiting Approval")
    # "admin" | "superadmin" - superadmin can approve/block other admins.
    role: Mapped[str] = mapped_column(String(20), default="admin")

    routes_created: Mapped[list["Route"]] = relationship(back_populates="creator")


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password: Mapped[str] = mapped_column(String(255))
    profile_image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # NULL = not suspended. A future timestamp blocks login until then.
    suspended_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspension_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    saved_routes: Mapped[list["SavedRoute"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class LoginOtp(Base):
    __tablename__ = "login_otps"

    # One pending OTP per user at a time - user_id IS the primary key, so a
    # new send just overwrites (upsert) the old row rather than piling up.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    otp_code: Mapped[str] = mapped_column(String(6))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    date_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Terminal(Base):
    __tablename__ = "terminals"

    terminal_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    terminal_name: Mapped[str] = mapped_column(String(150))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    # "Active" | "Inactive" - same active_status enum type Route.status uses.
    status: Mapped[str] = mapped_column(String(20), default="Active")
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    # Single photo (a Vercel Blob URL), same pattern as User.profile_image.
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)  # actual DB column is `text`, unbounded


class Landmark(Base):
    __tablename__ = "landmarks"

    landmark_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    landmark_name: Mapped[str] = mapped_column(String(150))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)


class Route(Base):
    __tablename__ = "routes"

    route_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_by_admin_id: Mapped[int] = mapped_column(ForeignKey("admins.admin_id"))
    origin_terminal_id: Mapped[int] = mapped_column(ForeignKey("terminals.terminal_id"))
    destination_terminal_id: Mapped[int] = mapped_column(ForeignKey("terminals.terminal_id"))
    route_code: Mapped[str] = mapped_column(String(50))
    vehicle_type: Mapped[str] = mapped_column(String(20))  # "Traditional" | "Modern"
    # "Active" | "Inactive" - replaces the old is_active boolean (migration 003).
    status: Mapped[str] = mapped_column(String(20), default="Active")
    base_fare: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    creator: Mapped["Admin"] = relationship(back_populates="routes_created")
    origin: Mapped["Terminal"] = relationship(foreign_keys=[origin_terminal_id])
    destination: Mapped["Terminal"] = relationship(foreign_keys=[destination_terminal_id])
    waypoints: Mapped[list["Waypoint"]] = relationship(
        back_populates="route", cascade="all, delete-orphan", order_by="Waypoint.sequence_no"
    )


class Waypoint(Base):
    __tablename__ = "waypoints"

    waypoint_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.route_id", ondelete="CASCADE"))
    sequence_no: Mapped[int] = mapped_column(Integer)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)

    route: Mapped["Route"] = relationship(back_populates="waypoints")


class SavedRoute(Base):
    __tablename__ = "saved_routes"

    saved_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.route_id", ondelete="CASCADE"), primary_key=True)
    date_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="saved_routes")
    route: Mapped["Route"] = relationship()


class RouteRating(Base):
    __tablename__ = "route_ratings"

    # One rating per user per route (composite PK) - re-rating is an upsert
    # that overwrites the existing row (and bumps date_updated) rather than
    # creating a second rating, so the aggregate always reflects each
    # rider's most current assessment.
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.route_id", ondelete="CASCADE"), primary_key=True)
    rated_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    route_accuracy_rating: Mapped[int] = mapped_column(Integer)  # 1-5, CHECK constraint enforced in the DB
    fare_accuracy_rating: Mapped[int] = mapped_column(Integer)  # 1-5, CHECK constraint enforced in the DB
    comment: Mapped[str | None] = mapped_column(String, nullable=True)
    date_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    date_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship()
    route: Mapped["Route"] = relationship()