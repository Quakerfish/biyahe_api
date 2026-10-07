from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------- admin auth
class AdminSignupIn(BaseModel):
    username: str
    email: EmailStr
    password: str
    confirm_password: str = Field(
        validation_alias=AliasChoices("confirm_password", "confirmPassword")
    )

    @field_validator("username")
    @classmethod
    def username_length(cls, v: str) -> str:
        v = v.strip()
        if not (3 <= len(v) <= 50):
            raise ValueError("Username must be between 3 and 50 characters.")
        return v

    @field_validator("password")
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return v


class AdminLoginIn(BaseModel):
    username: str
    password: str


class AdminOut(BaseModel):
    admin_id: int
    admin_uuid: str
    username: str
    email: EmailStr
    status: str
    role: str


class AdminApprovalOut(BaseModel):
    admin_id: int
    admin_uuid: str
    username: str
    email: EmailStr
    status: str
    role: str


class AdminStatusUpdateIn(BaseModel):
    status: Literal["Waiting Approval", "Approved", "Blocked"]


class AdminRoleUpdateIn(BaseModel):
    role: Literal["admin", "superadmin"]


class AdminProfileUpdateIn(BaseModel):
    username: str
    email: EmailStr


# ----------------------------------------------------------------- user auth
class UserSignupIn(BaseModel):
    username: str
    email: EmailStr
    password: str
    confirmPassword: str

    @field_validator("username")
    @classmethod
    def username_length(cls, v: str) -> str:
        v = v.strip()
        if not (3 <= len(v) <= 50):
            raise ValueError("Username must be between 3 and 50 characters.")
        return v

    @field_validator("password")
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return v


class UserLoginIn(BaseModel):
    username: str  # accepts username OR email, same as login.php
    password: str


class UserProfileOut(BaseModel):
    user_id: int
    username: str
    email: str
    profile_image: str | None
    date_created: datetime | None


class UserProfileUpdateIn(BaseModel):
    username: str
    email: EmailStr
    current_password: str | None = None
    new_password: str | None = None


# ------------------------------------------------------------------ terminal
class TerminalIn(BaseModel):
    terminal_name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    status: Literal["Active", "Inactive"] = "Active"
    description: str | None = None

    @field_validator("terminal_name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("terminal_name is required.")
        return v


class TerminalOut(BaseModel):
    terminal_id: int
    terminal_name: str
    latitude: float | None
    longitude: float | None
    status: str
    description: str | None
    image_url: str | None


class TerminalRouteSummaryOut(BaseModel):
    """One route passing through a terminal - used in the terminal detail response."""

    route_id: int
    route_code: str
    vehicle_type: str
    origin_name: str
    destination_name: str
    status: str


class TerminalDetailOut(TerminalOut):
    routes: list[TerminalRouteSummaryOut]


# ---------------------------------------------------------------------- route
class WaypointIn(BaseModel):
    sequence_no: int
    latitude: float
    longitude: float


class WaypointOut(BaseModel):
    sequence_no: int
    latitude: float
    longitude: float


class RouteIn(BaseModel):
    route_code: str
    vehicle_type: Literal["Traditional", "Modern"]
    origin_terminal_id: int
    destination_terminal_id: int
    status: Literal["Active", "Inactive"] = "Active"
    base_fare: float | None = Field(default=None, ge=0)
    description: str | None = None
    waypoints: list[WaypointIn]

    @field_validator("route_code")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("route_code is required.")
        return v

    @field_validator("waypoints")
    @classmethod
    def non_empty(cls, v: list[WaypointIn]) -> list[WaypointIn]:
        if not v:
            raise ValueError("waypoints must be a non-empty array.")
        return v

    @field_validator("destination_terminal_id")
    @classmethod
    def differs_from_origin(cls, v: int, info):
        origin = info.data.get("origin_terminal_id")
        if origin is not None and origin == v:
            raise ValueError("Origin and destination terminals must differ.")
        return v


class RouteListItemOut(BaseModel):
    route_id: int
    route_code: str
    vehicle_type: str
    origin_terminal_id: int
    destination_terminal_id: int
    origin_name: str
    destination_name: str
    status: str
    base_fare: float | None
    description: str | None


class RouteDetailOut(RouteListItemOut):
    waypoints: list[WaypointOut]


class SavedRouteOut(RouteListItemOut):
    date_saved: datetime | None


# ------------------------------------------------------------------ ratings
class RouteRatingIn(BaseModel):
    route_accuracy_rating: int = Field(ge=1, le=5)
    fare_accuracy_rating: int = Field(ge=1, le=5)
    comment: str | None = None

    @field_validator("comment")
    @classmethod
    def comment_length(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) > 500:
            raise ValueError("Comments must be 500 characters or fewer.")
        return v or None


class RouteRatingOut(BaseModel):
    route_accuracy_rating: int
    fare_accuracy_rating: int
    comment: str | None
    date_created: datetime
    date_updated: datetime


class RouteRatingSummaryOut(BaseModel):
    """Aggregate ratings for a route, plus the current user's own rating if they've rated it."""

    route_id: int
    rating_count: int
    average_route_accuracy: float | None
    average_fare_accuracy: float | None
    my_rating: RouteRatingOut | None