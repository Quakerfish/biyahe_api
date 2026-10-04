import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Uuid, func
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

    routes_created: Mapped[list["Route"]] = relationship(back_populates="creator")


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password: Mapped[str] = mapped_column(String(255))
    profile_image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    saved_routes: Mapped[list["SavedRoute"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Terminal(Base):
    __tablename__ = "terminals"

    terminal_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    terminal_name: Mapped[str] = mapped_column(String(150))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)


class Landmark(Base):
    __tablename__ = "landmarks"

    landmark_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    landmark_name: Mapped[str] = mapped_column(String(150))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)


class Route(Base):
    __tablename__ = "routes"

    route_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("admins.admin_id"))
    origin_terminal_id: Mapped[int] = mapped_column(ForeignKey("terminals.terminal_id"))
    destination_terminal_id: Mapped[int] = mapped_column(ForeignKey("terminals.terminal_id"))
    route_code: Mapped[str] = mapped_column(String(50))
    vehicle_type: Mapped[str] = mapped_column(String(20))  # "Traditional" | "Modern"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

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

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.route_id", ondelete="CASCADE"), primary_key=True)
    date_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="saved_routes")
    route: Mapped["Route"] = relationship()
