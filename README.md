# Biyahe API: FastAPI backend

FastAPI port of the original 16 PHP endpoint files, extended since with admin approval/roles, route ratings, terminal photos and Vercel Blob uploads. It uses a single Postgres (Supabase) database and **cookie-based sessions**, and is consumed by the admin website and the Android app.

Production base URL: `https://biyahe-api.vercel.app`

This README is the ground truth for how the API works **right now**. If an older doc, file name or chat history disagrees with it, this wins. Read [section 1](#1-known-gaps-and-things-that-changed-direction) first.

---

## Contents

1. [Known gaps and things that changed direction](#1-known-gaps-and-things-that-changed-direction)
2. [Project layout](#2-project-layout)
3. [Install and configure](#3-install-and-configure)
4. [Run locally](#4-run-locally)
5. [Deploy to Vercel](#5-deploy-to-vercel)
6. [Authentication model](#6-authentication-model)
7. [Endpoint reference](#7-endpoint-reference)
8. [Old PHP → new endpoint map](#8-old-php--new-endpoint-map)
9. [Database schema](#9-database-schema)
10. [What changed from the PHP version](#10-what-changed-from-the-php-version)
11. [Things an agent or developer should NOT assume](#11-things-an-agent-or-developer-should-not-assume)

---

## 1. Known gaps and things that changed direction

- **No OTP / 2FA on login yet.** A `login_otps` table and a `LoginOtp` model exist, but **no endpoint uses them**. `POST /api/login` authenticates and logs the user in in one step as soon as the password is correct.
- **The "Community" feature (posts, tags, helpful-votes) was built, then removed.** It was replaced by **Route Ratings** (`route_ratings` table, `/api/routes/{id}/ratings`). There is no `community_posts` table, `community_post_helpful` table, `CommunityPost` model or `community_tag` enum anymore.
- **Terminals support exactly one photo**, not a gallery. `image_url` is a single column.
- **`routes.vehicle_type`** is a plain `varchar(20)` validated in the app (Pydantic `Literal["Traditional", "Modern"]`), not a Postgres enum. By contrast `routes.status`, `terminals.status`, `admins.status` and `admins.role` *are* real Postgres enums.
- **Sessions, not tokens.** Auth is a signed session cookie (`biyahe_session`), set on login and sent back on every request (`credentials: 'include'` in `fetch`). There is no bearer token or `Authorization` header anywhere.
- **Every response is JSON, including errors.** A caught error returns `{"success": false, "message": "..."}` with a non-2xx status. Uncaught exceptions are normalized to the same shape by a global exception handler, so clients never see a raw traceback or plain-text 500.
- **`users.suspended_until` / `suspension_reason` exist but are not enforced** by any endpoint yet.

---

## 2. Project layout

```
app/
  main.py          FastAPI app: CORS, session middleware, error shapes, router wiring
  config.py        Settings loaded from .env (pydantic-settings)
  database.py      Async SQLAlchemy engine/session (asyncpg driver)
  models.py        ORM models: Admin, User, LoginOtp, Terminal, Landmark, Route,
                   Waypoint, SavedRoute, RouteRating
  schemas.py       Pydantic request/response models (replaces manual PHP validation)
  security.py      bcrypt hashing (compatible with existing PHP password_hash() values)
  dependencies.py  require_admin / require_superadmin / require_user / require_user_or_admin
  routers/
    admin_auth.py      admin signup, login, profile
    admin_management   list/approve/block admins, change roles (superadmin only)
    user_auth.py       commuter signup, login
    profile.py         profile get/update, avatar upload, logout
    dashboard.py       admin dashboard aggregates
    analytics.py       admin analytics aggregates
    terminals.py       terminals CRUD + photo upload
    routes.py          routes CRUD
    route_ratings      per-route ratings (upsert)
    saved_routes.py    commuter saved routes
    user_routes.py     commuter-facing route/terminal browsing
api/
  index.py        Vercel entrypoint: re-exports app/main.py's `app`
requirements.txt
.env.example
.python-version   pins the Vercel Python runtime version
vercel.json
ANDROID_INTEGRATION.md   which endpoints the Android app hits, and what changed
```

> File names for the newer routers (`admin_management`, `route_ratings`) are indicative. Match them to what is actually in your repo.

> **The Android app also calls several of these endpoints.** Read `ANDROID_INTEGRATION.md` before deploying. A few endpoints changed method or payload shape in ways a simple URL swap won't cover (notably `save_routes.php`'s POST/DELETE, and logout moving to its own URL).

---

## 3. Install and configure

```bash
python3 -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows
pip install -r requirements.txt

cp .env.example .env
```

Edit `.env`:

| Variable | Purpose |
|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS` | Postgres (Supabase) connection. Use the **pooled** connection string in production. |
| `SESSION_SECRET_KEY` | Cookie signing key. Generate with `openssl rand -hex 32`. |
| `SESSION_SAME_SITE` | `none` in production (admin site and Android app are on different origins than the API). |
| `SESSION_HTTPS_ONLY` | `true` in production. |
| `CORS_ORIGINS` | Comma-separated list of allowed origins. Any new frontend origin must be added here before it can authenticate. |
| `BLOB_READ_WRITE_TOKEN` | Vercel Blob token. Injected automatically in production; locally, get it with `vercel env pull`. |

---

## 4. Run locally

```bash
uvicorn app.main:app --reload --port 8000
```

Interactive docs are at `http://localhost:8000/docs`, handy for checking each endpoint's exact request and response shape.

---

## 5. Deploy to Vercel

Deploy this as its **own, separate Vercel project**, not combined with the admin website's project. Vercel's Python runtime is stateless serverless functions with no persistent disk, so the API, the admin site and the Android app each talk to the API over its own URL.

1. **Use Postgres connection pooling.** Serverless functions can spin up many concurrent instances, each opening DB connections. On Supabase/Neon/RDS, use the **pooled** connection string (often a different port, e.g. `6543` instead of `5432` for Supabase/PgBouncer) for `DB_HOST`/`DB_PORT`, otherwise you can exhaust your connection limit under load.
2. **Create a Blob store.** Vercel dashboard → your project → **Storage** → **Create Database** → **Blob**, and link it to the project. Vercel injects `BLOB_READ_WRITE_TOKEN` automatically.
3. **Push to a Git repo**, then import it at [vercel.com/new](https://vercel.com/new). Vercel auto-detects FastAPI from `requirements.txt` and `api/index.py`, so there is no build command or output directory to configure.
4. **Set environment variables** under Settings → Environment Variables (see the table in [section 3](#3-install-and-configure)).
5. **Deploy.** The API is live at `https://<project>.vercel.app` (or a custom domain, e.g. `api.biyahe.app`). Point the admin website's fetch calls and the Android app's base URL at it.

---

## 6. Authentication model

Two entirely separate session concepts exist side by side:

- **Admin session**: `request.session["admin_id"]`, set by `POST /api/admin/login`. Required by every endpoint under `/api/admin`, `/api/terminals`, `/api/routes` (except ratings), `/api/dashboard`, `/api/analytics`.
- **User (commuter) session**: `request.session["user_id"]`, set by `POST /api/login`. Required by `/api/profile`, `/api/saved-routes`, `/api/routes/{id}/ratings`.
- **Either**: `/api/commuter-routes` accepts a valid admin **or** user session (`require_user_or_admin`).

An admin's `status` is checked **on every request**, not just at login. A superadmin blocking another admin takes effect immediately, even mid-session.

CORS is locked to `CORS_ORIGINS` with `allow_credentials=True`. Preflight (`OPTIONS`) is handled globally by `CORSMiddleware`.

---

## 7. Endpoint reference

Every success response includes `"success": true`. Every error is `{"success": false, "message": "<reason>"}` with an HTTP status of 400/401/403/404/409/500. Only the *successful* shape is shown below.

### Admin auth: `/api/admin`

| Method | Path | Auth | Body | Notes |
|---|---|---|---|---|
| POST | `/api/admin/signup` | none | `{username, email, password, confirm_password}` | New admins start as `status="Waiting Approval"`, `role="admin"` and cannot log in until a superadmin approves them. |
| POST | `/api/admin/login` | none | `{username, password}` | 403 if status is `"Waiting Approval"` or `"Blocked"`. Success returns `{message, admin: {admin_id, admin_uuid, username, email, status, role}}`. |
| GET | `/api/admin/profile` | admin | none | `{admin: {admin_id, admin_uuid, username, email, status, role}}` |
| PUT | `/api/admin/profile` | admin | `{username, email}` | Username/email only. No admin password-change endpoint exists yet. |

### Admin management: `/api/admin/admins` (superadmin only)

| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/api/admin/admins` | none | Every admin account: `{admins: [{admin_id, admin_uuid, username, email, status, role}, ...]}` |
| GET | `/api/admin/admins/pending` | none | Same shape, filtered to `status="Waiting Approval"`. |
| PUT | `/api/admin/admins/{admin_id}/status` | `{status: "Waiting Approval" \| "Approved" \| "Blocked"}` | A superadmin cannot change their **own** status (400), to avoid self-lockout. |
| PUT | `/api/admin/admins/{admin_id}/role` | `{role: "admin" \| "superadmin"}` | Same self-modification guard. |

### User auth: `/api` (no auth)

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/api/signup` | `{username, email, password, confirmPassword}` | The field is `confirmPassword` (camelCase) here but `confirm_password` for admin signup. Inherited from the PHP endpoints and kept for Android compatibility. |
| POST | `/api/login` | `{username, password}` | `username` accepts a username **or** an email. Logs in directly with **no OTP step**. Returns `{message, username, email}`. |

### Profile: `/api` (user auth)

| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/api/profile` | none | `{user_id, username, email, profile_image, date_created}`. `profile_image` is `null` unless it's a real `http(s)://` URL; legacy pre-migration filenames are deliberately suppressed. |
| PUT | `/api/profile` (also accepts `POST` for backward compatibility) | `{username, email, current_password?, new_password?}` | Send both password fields together to change the password, or omit both to update only username/email. |
| POST | `/api/profile/image` | multipart, field `profile_image` | Uploads to Vercel Blob (public) and stores the CDN URL in `users.profile_image`. Accepts `image/jpeg`, `image/png`, `image/webp`. |
| POST | `/api/logout` | none | Clears the session. |

### Dashboard and analytics (admin, read-only)

| Method | Path | Returns |
|---|---|---|
| GET | `/api/dashboard` | Stats (user/admin/route/terminal counts, active/inactive route split), top 6 terminal hubs by route count, GeoJSON FeatureCollections for terminals and landmarks (map overlay). |
| GET | `/api/analytics` | Stats, user distribution (admins vs commuters), vehicle-type breakdown (Traditional/Modern), 7-day signup and saved-route trend lines. |

Both are aggregate views with no filters or pagination.

### Terminals: `/api/terminals` (admin)

| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/api/terminals` | none | List ordered by name: `{terminal_id, terminal_name, latitude, longitude, status, description, image_url}`. |
| GET | `/api/terminals/{id}` | none | Same fields **plus** `routes: [{route_id, route_code, vehicle_type, origin_name, destination_name, status}, ...]` for every route whose origin *or* destination is this terminal. This is a query-time join, not a stored column. |
| POST | `/api/terminals` | `{terminal_name, latitude, longitude, status?, description?}` | `status` defaults to `"Active"`. Returns the created terminal (no `image_url` yet; upload separately). |
| PUT | `/api/terminals/{id}` | same as POST | Full replace of those fields. |
| POST | `/api/terminals/{id}/image` | multipart, field `image` | Same Blob upload pattern as avatars. Returns `{image_url}`. |
| DELETE | `/api/terminals/{id}` | none | 409 if any route still references it as origin/destination. |

### Routes: `/api/routes` (admin)

| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/api/routes` | none | `{route_id, route_code, vehicle_type, origin_terminal_id, destination_terminal_id, origin_name, destination_name, status, base_fare, description}` per item. |
| GET | `/api/routes/{id}` | none | Same fields plus `waypoints: [{sequence_no, latitude, longitude}, ...]`. |
| POST | `/api/routes` | `{route_code, vehicle_type, origin_terminal_id, destination_terminal_id, status?, base_fare?, description?, waypoints: [...]}` | `waypoints` must be non-empty; origin and destination must differ; `status` defaults to `"Active"`. `created_by_admin_id` is set from the session automatically. |
| PUT | `/api/routes/{id}` | same as POST | **Replaces waypoints wholesale** (delete all, re-insert). Always send the complete list, not a diff. |
| DELETE | `/api/routes/{id}` | none | Cascades to waypoints. |

### Route ratings: `/api/routes/{route_id}/ratings` (user)

| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/api/routes/{route_id}/ratings` | none | `{route_id, rating_count, average_route_accuracy, average_fare_accuracy, my_rating}`. Averages are `null` if nobody has rated. `my_rating` is `null` or `{route_accuracy_rating, fare_accuracy_rating, comment, date_created, date_updated}`. |
| POST | `/api/routes/{route_id}/ratings` | `{route_accuracy_rating: 1-5, fare_accuracy_rating: 1-5, comment?}` | **Upsert**: one rating per user per route. Re-rating overwrites the row and bumps `date_updated`. |

### Saved routes: `/api/saved-routes` (user)

| Method | Query | Notes |
|---|---|---|
| GET | none | The user's saved routes with full route info (`status`, `base_fare`, etc.) plus `date_saved`. |
| POST | `?route_id=123` | `route_id` is a **query param**, not a JSON body. Idempotent. |
| DELETE | `?route_id=123` | Same: query param, idempotent. |

### Commuter routes: `/api/commuter-routes` (user **or** admin)

One endpoint, three modes selected by query params:

| Query | Returns |
|---|---|
| `?type=terminals` | `{terminals: [{terminal_id, terminal_name, latitude, longitude, status, description, image_url}, ...]}` |
| `?id=123` | One **active** route's full detail incl. `waypoints`, `base_fare`, `description`, and nested `origin`/`destination` objects. 404 if the route isn't `status="Active"`. |
| *(neither)* | `{routes: [...]}`: every **active** route, summary fields only (no waypoints). |

---

## 8. Old PHP → new endpoint map

| PHP file | Method(s) | New endpoint |
|---|---|---|
| admin_signup.php | POST | `POST /api/admin/signup` |
| admin_login.php | POST | `POST /api/admin/login` |
| admin_profile.php | GET, POST | `GET/PUT /api/admin/profile` |
| signup.php | POST | `POST /api/signup` |
| login.php | POST | `POST /api/login` |
| get_profile.php | GET | `GET /api/profile` |
| get_profile.php?action=logout | POST | `POST /api/logout` |
| update_profile.php | POST | `PUT /api/profile` (`POST` still accepted) |
| upload_profile_image.php | POST | `POST /api/profile/image` (multipart, field `profile_image`) |
| dashboard.php | GET | `GET /api/dashboard` |
| analytics.php | GET | `GET /api/analytics` |
| terminals.php | GET, POST, PUT, DELETE | `/api/terminals`, `/api/terminals/{id}` |
| routes.php | GET, POST, PUT, DELETE | `/api/routes`, `/api/routes/{id}` |
| save_routes.php | GET, POST, DELETE | `/api/saved-routes` (POST/DELETE take `route_id` as a query param) |
| user_routes.php | GET | `GET /api/commuter-routes` (same `?type=terminals` / `?id=` params) |

**New since the port (no PHP equivalent):** admin management (`/api/admin/admins/...`), route ratings (`/api/routes/{id}/ratings`), terminal photo upload (`/api/terminals/{id}/image`).

Several update calls moved from "`POST` does everything" to `PUT`. Update the frontend's fetch calls for `admin_profile.php` and the route/terminal updates accordingly. `PUT /api/profile` still accepts `POST` for Android backward compatibility.

---

## 9. Database schema

Current state after migrations 001 → 004, written as equivalent fresh-create DDL (not a migration script). The ORM models in `models.py` map onto this existing database; **never let the ORM create tables**. For future migrations, use Alembic:

```bash
pip install alembic
alembic init migrations
# point migrations/env.py's target_metadata at app.database.Base.metadata
```

```sql
-- Enum types
CREATE TYPE public.active_status AS ENUM ('Active', 'Inactive');
CREATE TYPE public.admin_approval_status AS ENUM ('Waiting Approval', 'Approved', 'Blocked');
CREATE TYPE public.admin_role AS ENUM ('admin', 'superadmin');

-- admins
CREATE TABLE public.admins (
    admin_id       integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admin_uuid     uuid UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    admin_username character varying(50) UNIQUE NOT NULL,
    admin_password character varying(255) NOT NULL,
    admin_email    character varying(255) UNIQUE NOT NULL,
    status         public.admin_approval_status NOT NULL DEFAULT 'Waiting Approval',
    role           public.admin_role NOT NULL DEFAULT 'admin'
);

-- users
CREATE TABLE public.users (
    user_id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username           character varying(50) UNIQUE NOT NULL,
    email              character varying(255) UNIQUE NOT NULL,
    password           character varying(255) NOT NULL,
    profile_image      character varying(255),
    date_created       timestamp with time zone DEFAULT now(),
    suspended_until    timestamp with time zone,  -- NULL = not suspended; not yet enforced
    suspension_reason  text
);

-- login_otps: table exists, but NO endpoint uses it yet (see section 1)
CREATE TABLE public.login_otps (
    user_id       integer PRIMARY KEY REFERENCES public.users(user_id) ON DELETE CASCADE,
    otp_code      character varying(6) NOT NULL,
    expires_at    timestamp with time zone NOT NULL,
    attempt_count integer NOT NULL DEFAULT 0,
    date_created  timestamp with time zone DEFAULT now()
);

-- terminals
CREATE TABLE public.terminals (
    terminal_id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    terminal_name character varying(150) NOT NULL,
    latitude      double precision,
    longitude     double precision,
    status        public.active_status NOT NULL DEFAULT 'Active',
    description   text,
    image_url     text  -- single photo (Vercel Blob URL), not a gallery
);

-- landmarks
CREATE TABLE public.landmarks (
    landmark_id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    landmark_name character varying(150) NOT NULL,
    latitude      double precision,
    longitude     double precision
);

-- routes
CREATE TABLE public.routes (
    route_id                integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_by_admin_id     integer NOT NULL REFERENCES public.admins(admin_id),
    origin_terminal_id      integer NOT NULL REFERENCES public.terminals(terminal_id),
    destination_terminal_id integer NOT NULL REFERENCES public.terminals(terminal_id),
    route_code              character varying(50) NOT NULL,
    vehicle_type            character varying(20) NOT NULL, -- 'Traditional' | 'Modern', app-validated, NOT a DB enum
    status                  public.active_status NOT NULL DEFAULT 'Active',
    base_fare               numeric(6,2),
    description             text
);

-- waypoints
CREATE TABLE public.waypoints (
    waypoint_id  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    route_id     integer NOT NULL REFERENCES public.routes(route_id) ON DELETE CASCADE,
    sequence_no  integer NOT NULL,
    latitude     double precision NOT NULL,
    longitude    double precision NOT NULL
);

-- saved_routes
CREATE TABLE public.saved_routes (
    saved_by_user_id integer NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    route_id         integer NOT NULL REFERENCES public.routes(route_id) ON DELETE CASCADE,
    date_created     timestamp with time zone DEFAULT now(),
    PRIMARY KEY (saved_by_user_id, route_id)
);

-- route_ratings
CREATE TABLE public.route_ratings (
    route_id              integer NOT NULL REFERENCES public.routes(route_id) ON DELETE CASCADE,
    rated_by_user_id      integer NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    route_accuracy_rating smallint NOT NULL CHECK (route_accuracy_rating BETWEEN 1 AND 5),
    fare_accuracy_rating  smallint NOT NULL CHECK (fare_accuracy_rating BETWEEN 1 AND 5),
    comment               text,
    date_created          timestamp with time zone DEFAULT now(),
    date_updated          timestamp with time zone DEFAULT now(),
    PRIMARY KEY (route_id, rated_by_user_id)
);
```

**Tables that no longer exist:** `community_posts`, `community_post_helpful` and the `community_tag` enum (dropped in migration 004); `users.role` and the `user_role` enum (dropped in migration 003). If they appear in older docs or an agent's context, they're stale. Don't recreate them.

**Naming convention:** the schema deliberately avoids bare `user_id`/`admin_id` in child tables in favor of naming what the person did (`saved_by_user_id`, `created_by_admin_id`, `rated_by_user_id`).

---

## 10. What changed from the PHP version

- **Sessions**: PHP's `session_start()` + `$_SESSION[...]` is replaced by Starlette's `SessionMiddleware`, which stores the key/value data in a signed cookie (`biyahe_session`) instead of a server-side file. Clients already send/receive cookies with `credentials: 'include'`; only the cookie's contents changed.
- **Passwords**: PHP's `password_hash()` produced `$2y$` bcrypt hashes. Passlib reads `$2y$` the same as `$2b$`, so **existing passwords keep working** with no re-hashing. New signups get `$2b$` hashes, which PHP's `password_verify()` also accepts, so running both stacks briefly is safe.
- **Validation**: hand-rolled `empty()`/`strlen()` checks became Pydantic validators (`schemas.py`). Error responses keep the `{"success": false, "message": "..."}` shape and roughly the same messages, via the custom exception handlers in `main.py`.
- **`htmlspecialchars()` sanitization**: the PHP code HTML-escaped strings before storing/returning them. This port does **not** re-implement that. The better fix is escaping on render (the default in React/Vue/modern templating) plus CSP, rather than mutating stored data. If you need byte-for-byte HTML-escaped storage like before, add it back in `schemas.py`.
- **CORS/OPTIONS**: handled globally by `CORSMiddleware` instead of per-file `header(...)` + `if (OPTIONS) exit` blocks.
- **Avatar and terminal photo uploads go to Vercel Blob, not local disk.** Vercel's Python functions have no persistent filesystem, so `move_uploaded_file()` to `uploads/avatars/` became a Blob upload. `users.profile_image` now stores a full CDN URL rather than a filename. See `ANDROID_INTEGRATION.md` if anything client-side parses that URL's shape.

---

## 11. Things an agent or developer should NOT assume

- Don't assume `/api/login` involves OTP/2FA. It doesn't yet.
- Don't build against `community_posts` or any community endpoint. It's gone; use Route Ratings.
- Don't assume `terminals.image_url` is a list. It's one URL.
- Don't assume `vehicle_type` is a Postgres enum. It's a plain varchar validated in the API layer only.
- Don't assume admin approval is a one-time login check. `status` is re-verified on every admin-authenticated request.
- Don't assume any bearer-token auth. Everything is cookie sessions.
- Don't assume a bare `user_id` column on child tables: `saved_routes` uses `saved_by_user_id`, `route_ratings` uses `rated_by_user_id`.
- Don't assume `users.suspended_until` blocks anything. It isn't enforced yet.
