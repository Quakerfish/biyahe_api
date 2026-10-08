import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ==========================================
# PostgreSQL Enum Mappings (Option A)
# ==========================================
class ActiveStatus(str, enum.Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"


class AdminApprovalStatus(str, enum.Enum):
    WAITING_APPROVAL = "Waiting Approval"
    APPROVED = "Approved"
    BLOCKED = "Blocked"


class AdminRole(str, enum.Enum):
    ADMIN = "admin"
    SUPERADMIN = "superadmin"

# ==========================================
# ORM Models 
# ==========================================
class Admin(Base):
    __tablename__ = "admins"

    admin_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_uuid: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), unique=True, default=lambda: str(uuid.uuid4())
    )
    admin_username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    admin_password: Mapped[str] = mapped_column(String(255))
    admin_email: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    status: Mapped[AdminApprovalStatus] = mapped_column(
        SQLEnum(
            AdminApprovalStatus,
            name="admin_approval_status",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=AdminApprovalStatus.WAITING_APPROVAL,
    )
    role: Mapped[AdminRole] = mapped_column(
        SQLEnum(
            AdminRole,
            name="admin_role",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=AdminRole.ADMIN,
    )

    routes_created: Mapped[list["Route"]] = relationship(back_populates="creator")


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password: Mapped[str] = mapped_column(String(255))
    profile_image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    suspended_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspension_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    saved_routes: Mapped[list["SavedRoute"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class LoginOtp(Base):
    __tablename__ = "login_otps"

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
    status: Mapped[ActiveStatus] = mapped_column(
        SQLEnum(
            ActiveStatus,
            name="active_status",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=ActiveStatus.ACTIVE,
    )
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)


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
    vehicle_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[ActiveStatus] = mapped_column(
        SQLEnum(
            ActiveStatus,
            name="active_status",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=ActiveStatus.ACTIVE,
    )
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

    route_id: Mapped[int] = mapped_column(ForeignKey("routes.route_id", ondelete="CASCADE"), primary_key=True)
    rated_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    route_accuracy_rating: Mapped[int] = mapped_column(Integer)
    fare_accuracy_rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(String, nullable=True)
    date_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    date_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship()
    route: Mapped["Route"] = relationship()