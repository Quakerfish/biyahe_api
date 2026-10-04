from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.routers import (
    admin_auth,
    analytics,
    dashboard,
    profile,
    routes,
    saved_routes,
    terminals,
    user_auth,
    user_routes,
)

app = FastAPI(title="Biyahe API", version="1.0.0")

# ---------------------------------------------------------------- middleware
# SessionMiddleware signs a cookie (itsdangerous) holding the session data,
# which is this app's equivalent of PHP's server-side $_SESSION. The cookie
# name "biyahe_session" replaces PHPSESSID; same_site/https_only mirror the
# CORS + "Access-Control-Allow-Credentials: true" setup every PHP file had,
# which your Android app and admin web app already rely on.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
    session_cookie="biyahe_session",
    same_site=settings.SESSION_SAME_SITE,
    https_only=settings.SESSION_HTTPS_ONLY,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------- PHP-shaped errors
# Every PHP file returned {"success": false, "message": "..."} on error, with
# an HTTP status code. Keep that exact JSON shape here so existing frontend
# code (admin web app + Android app) that reads `.message` doesn't need to
# change just because of this migration.
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"success": False, "message": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Collapse Pydantic's structured error list into one readable message,
    # same flavor as the PHP endpoints' single validation message.
    first_error = exc.errors()[0] if exc.errors() else {"msg": "Invalid request."}
    return JSONResponse(status_code=400, content={"success": False, "message": first_error["msg"]})


# ------------------------------------------------------------------ routers
app.include_router(admin_auth.router)
app.include_router(user_auth.router)
app.include_router(profile.router)
app.include_router(dashboard.router)
app.include_router(analytics.router)
app.include_router(terminals.router)
app.include_router(routes.router)
app.include_router(saved_routes.router)
app.include_router(user_routes.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
