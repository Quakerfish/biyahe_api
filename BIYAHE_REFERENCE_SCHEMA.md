# Biyahe API & Database Reference

Ground-truth reference for the FastAPI backend and Postgres (Supabase) schema,
as they actually exist right now — not as originally planned. Written for use
as context for coding agents building the admin website.

Base URL (production): `https://biyahe-api.vercel.app`

---

## 0. Important: known gaps and things that changed direction

Read this section first — these are the places where what the code *actually
does* differs from what an earlier plan or an old file name might suggest.

- **No OTP / 2FA on login yet.** A `login_otps` table and a `LoginOtp` model
  exist in the schema and codebase, but **no endpoint uses them**.
  `POST /api/login` currently authenticates and logs the user in directly in
  one step, the moment the password is correct. Do not assume an OTP step
  exists anywhere in the commuter login flow.
- **The "Community" feature (posts, tags, helpful-votes) was built, then
  removed.** It has been fully replaced by **Route Ratings**
  (`route_ratings` table, `/api/routes/{id}/ratings`). There is no
  `community_posts` table, `community_post_helpful` table, `CommunityPost`
  model, or `community_tag` enum anymore — if you see any of these
  mentioned elsewhere (old docs, old chat history), they're stale.
- **Terminals support exactly one photo**, not a gallery — `image_url` is a
  single column, not a related table.
- **`routes.vehicle_type`** is a plain `varchar(20)` validated at the
  application layer (Pydantic `Literal["Traditional", "Modern"]`), not a
  Postgres enum type — unlike `routes.status`, `terminals.status`,
  `admins.status`, and `admins.role`, which *are* real Postgres enums.
- **Sessions, not tokens.** Auth is a signed session cookie
  (`biyahe_session`), set via `Set-Cookie` on login and sent back via
  `Cookie` on every subsequent request (`credentials: 'include'` in
  `fetch`). There is no bearer token / `Authorization` header anywhere in
  this API.
- **Every response is JSON**, including errors. A caught error returns
  `{"success": false, "message": "..."}` with a non-2xx status code; an
  *uncaught* exception is also normalized to that same shape (via a global
  FastAPI exception handler) rather than leaking a raw Python traceback or
  plain-text 500.

---

## 1. Authentication model

Two entirely separate session concepts exist side by side:

- **Admin session** — `request.session["admin_id"]`, set by
  `POST /api/admin/login`. Required by every endpoint under `/api/admin`,
  `/api/terminals`, `/api/routes`, `/api/dashboard`, `/api/analytics`.
- **User (commuter) session** — `request.session["user_id"]`, set by
  `POST /api/login`. Required by `/api/profile`, `/api/saved-routes`,
  `/api/routes/{id}/ratings`.
- **Either** — `/api/commuter-routes` accepts *either* a valid admin or user
  session (`require_user_or_admin`).

An admin's `status` (see §3) is checked **on every request**, not just at
login — a superadmin blocking another admin takes effect immediately, even
mid-session, rather than waiting for their session to expire.

CORS is locked to the `CORS_ORIGINS` environment variable (comma-separated
list of allowed origins) with `allow_credentials=True`. Any new frontend
origin (e.g. a new admin site deployment) must be added there before it can
authenticate.

---

## 2. Endpoint reference

Every success response includes `"success": true`. Every error response is
`{"success": false, "message": "<human-readable reason>"}` with an
appropriate HTTP status code (400/401/403/404/409/500). That's omitted below
for brevity — only the *successful* response shape is shown.

### Admin Auth — `/api/admin` (no auth required for signup/login)

| Method | Path | Auth | Body | Notes |
|---|---|---|---|---|
| POST | `/api/admin/signup` | none | `{username, email, password, confirm_password}` | New admins start as `status="Waiting Approval"`, `role="admin"`. Cannot log in until a superadmin approves them. |
| POST | `/api/admin/login` | none | `{username, password}` | Rejects with 403 if `status` is `"Waiting Approval"` or `"Blocked"`. On success, sets the admin session and returns `{message, admin: {admin_id, admin_uuid, username, email, status, role}}`. |
| GET | `/api/admin/profile` | admin | — | Returns `{admin: {admin_id, admin_uuid, username, email, status, role}}`. |
| PUT | `/api/admin/profile` | admin | `{username, email}` | Username/email only — no password change endpoint exists for admins yet. |

### Admin Management — `/api/admin/admins` (superadmin only)

| Method | Path | Auth | Body | Notes |
|---|---|---|---|---|
| GET | `/api/admin/admins` | superadmin | — | Every admin account. `{admins: [{admin_id, admin_uuid, username, email, status, role}, ...]}` |
| GET | `/api/admin/admins/pending` | superadmin | — | Same shape, filtered to `status="Waiting Approval"`. |
| PUT | `/api/admin/admins/{admin_id}/status` | superadmin | `{status: "Waiting Approval"\|"Approved"\|"Blocked"}` | A superadmin cannot change their **own** status (400 if attempted) — avoids accidental self-lockout. |
| PUT | `/api/admin/admins/{admin_id}/role` | superadmin | `{role: "admin"\|"superadmin"}` | Same self-modification guard as above. |

### User Auth — `/api` (no auth required)

| Method | Path | Auth | Body | Notes |
|---|---|---|---|---|
| POST | `/api/signup` | none | `{username, email, password, confirmPassword}` | Note the body field is `confirmPassword` (camelCase) here, but `confirm_password` (snake_case) for admin signup — inherited from the original PHP endpoints, kept as-is for the Android app's compatibility. |
| POST | `/api/login` | none | `{username, password}` | `username` field accepts either a username or an email. **Logs the user in directly — no OTP step** (see §0). Returns `{message, username, email}`. |

### Profile — `/api` (user auth required)

| Method | Path | Auth | Body | Notes |
|---|---|---|---|---|
| GET | `/api/profile` | user | — | `{user_id, username, email, profile_image, date_created}`. `profile_image` is `null` unless it's a real `http(s)://` URL — legacy pre-migration filenames are deliberately suppressed, not returned broken. |
| PUT | `/api/profile` (also accepts `POST`, for backward compatibility) | user | `{username, email, current_password?, new_password?}` | Password change is optional — include both `current_password` and `new_password` together to change it, or omit both to just update username/email. |
| POST | `/api/profile/image` | user | multipart, field name `profile_image` | Uploads to Vercel Blob (public), stores the resulting CDN URL in `users.profile_image`. Accepts `image/jpeg`, `image/png`, `image/webp`. |
| POST | `/api/logout` | user | — | Clears the session. |

### Dashboard & Analytics — admin only, read-only

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/dashboard` | admin | Stats (user/admin/route/terminal counts, active/inactive route split), top 6 terminal hubs by route count, GeoJSON FeatureCollections for terminals + landmarks (map overlay data). |
| GET | `/api/analytics` | admin | Stats, user distribution (admins vs commuters), vehicle-type breakdown (Traditional/Modern counts), 7-day signup and saved-route trend lines. |

Both are **read-only aggregate views** — no filters, no pagination, nothing
to post.

### Terminals — `/api/terminals` (admin only)

| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/api/terminals` | — | List, ordered by name. Each item: `{terminal_id, terminal_name, latitude, longitude, status, description, image_url}`. |
| GET | `/api/terminals/{id}` | — | Same fields, **plus** `routes: [{route_id, route_code, vehicle_type, origin_name, destination_name, status}, ...]` — every route whose origin *or* destination is this terminal. This is a query-time join, not a stored column. |
| POST | `/api/terminals` | `{terminal_name, latitude, longitude, status?, description?}` | `status` defaults to `"Active"` if omitted. Returns the created terminal (no `image_url` yet — upload separately). |
| PUT | `/api/terminals/{id}` | same as POST | Full replace of those fields. |
| POST | `/api/terminals/{id}/image` | multipart, field name `image` | Same Blob upload pattern as avatars. Returns `{image_url}`. |
| DELETE | `/api/terminals/{id}` | — | 409 if the terminal is still referenced as an origin/destination by any route. |

### Routes — `/api/routes` (admin only)

| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/api/routes` | — | List. Each item: `{route_id, route_code, vehicle_type, origin_terminal_id, destination_terminal_id, origin_name, destination_name, status, base_fare, description}`. |
| GET | `/api/routes/{id}` | — | Same fields, plus `waypoints: [{sequence_no, latitude, longitude}, ...]`. |
| POST | `/api/routes` | `{route_code, vehicle_type, origin_terminal_id, destination_terminal_id, status?, base_fare?, description?, waypoints: [...]}` | `waypoints` must be non-empty. `origin_terminal_id` and `destination_terminal_id` must differ. `status` defaults to `"Active"`. Sets `created_by_admin_id` to the logged-in admin automatically. |
| PUT | `/api/routes/{id}` | same as POST | **Replaces waypoints wholesale** (deletes all, re-inserts) — always send the complete waypoint list, not a diff. |
| DELETE | `/api/routes/{id}` | — | Cascades to waypoints automatically. |

### Route Ratings — `/api/routes/{route_id}/ratings` (user only)

| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/api/routes/{route_id}/ratings` | — | `{route_id, rating_count, average_route_accuracy, average_fare_accuracy, my_rating}`. Averages are `null` if nobody's rated yet. `my_rating` is `null` if the current user hasn't rated this route, else `{route_accuracy_rating, fare_accuracy_rating, comment, date_created, date_updated}`. |
| POST | `/api/routes/{route_id}/ratings` | `{route_accuracy_rating: 1-5, fare_accuracy_rating: 1-5, comment?}` | **Upsert** — one rating per user per route. Re-rating overwrites the existing row (and bumps `date_updated`) rather than creating a second one. |

### Saved Routes — `/api/saved-routes` (user only)

| Method | Path | Query | Notes |
|---|---|---|---|
| GET | `/api/saved-routes` | — | List of the user's saved routes, each with full route info (`status`, `base_fare`, etc.) plus `date_saved`. |
| POST | `/api/saved-routes` | `?route_id=123` | `route_id` is a **query param**, not a JSON body. Idempotent (no error if already saved). |
| DELETE | `/api/saved-routes` | `?route_id=123` | Same — query param, idempotent. |

### Commuter Routes — `/api/commuter-routes` (user **or** admin)

Single endpoint, three modes selected by query params:

| Query | Returns |
|---|---|
| `?type=terminals` | `{terminals: [{terminal_id, terminal_name, latitude, longitude, status, description, image_url}, ...]}` |
| `?id=123` | One **active** route's full detail incl. `waypoints`, `base_fare`, `description`, nested `origin`/`destination` objects. 404 if that route isn't `status="Active"`. |
| *(neither)* | `{routes: [...]}` — every **active** route, summary fields only (no waypoints). |

---

## 3. Database schema (current state)

Reflects migrations 001 → 004 applied on top of the original schema. Written
as the equivalent fresh-create DDL — not a migration script — for reference.

```sql
-- ============================================================
-- Enum types
-- ============================================================
CREATE TYPE public.active_status AS ENUM ('Active', 'Inactive');
CREATE TYPE public.admin_approval_status AS ENUM ('Waiting Approval', 'Approved', 'Blocked');
CREATE TYPE public.admin_role AS ENUM ('admin', 'superadmin');

-- ============================================================
-- admins
-- ============================================================
CREATE TABLE public.admins (
    admin_id       integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admin_uuid     uuid UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    admin_username character varying(50) UNIQUE NOT NULL,
    admin_password character varying(255) NOT NULL,
    admin_email    character varying(255) UNIQUE NOT NULL,
    status         public.admin_approval_status NOT NULL DEFAULT 'Waiting Approval',
    role           public.admin_role NOT NULL DEFAULT 'admin'
);

-- ============================================================
-- users
-- ============================================================
CREATE TABLE public.users (
    user_id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username           character varying(50) UNIQUE NOT NULL,
    email              character varying(255) UNIQUE NOT NULL,
    password           character varying(255) NOT NULL,
    profile_image      character varying(255),
    date_created       timestamp with time zone DEFAULT now(),
    suspended_until    timestamp with time zone,  -- NULL = not suspended; not yet enforced by any endpoint
    suspension_reason  text
);

-- ============================================================
-- login_otps - table exists, but NO endpoint uses it yet (see §0)
-- ============================================================
CREATE TABLE public.login_otps (
    user_id       integer PRIMARY KEY REFERENCES public.users(user_id) ON DELETE CASCADE,
    otp_code      character varying(6) NOT NULL,
    expires_at    timestamp with time zone NOT NULL,
    attempt_count integer NOT NULL DEFAULT 0,
    date_created  timestamp with time zone DEFAULT now()
);

-- ============================================================
-- terminals
-- ============================================================
CREATE TABLE public.terminals (
    terminal_id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    terminal_name character varying(150) NOT NULL,
    latitude      double precision,
    longitude     double precision,
    status        public.active_status NOT NULL DEFAULT 'Active',
    description   text,
    image_url     text  -- single photo (Vercel Blob URL), not a gallery
);

-- ============================================================
-- landmarks (unchanged since the original schema)
-- ============================================================
CREATE TABLE public.landmarks (
    landmark_id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    landmark_name character varying(150) NOT NULL,
    latitude      double precision,
    longitude     double precision
);

-- ============================================================
-- routes
-- ============================================================
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

-- ============================================================
-- waypoints (unchanged since the original schema)
-- ============================================================
CREATE TABLE public.waypoints (
    waypoint_id  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    route_id     integer NOT NULL REFERENCES public.routes(route_id) ON DELETE CASCADE,
    sequence_no  integer NOT NULL,
    latitude     double precision NOT NULL,
    longitude    double precision NOT NULL
);

-- ============================================================
-- saved_routes
-- ============================================================
CREATE TABLE public.saved_routes (
    saved_by_user_id integer NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    route_id         integer NOT NULL REFERENCES public.routes(route_id) ON DELETE CASCADE,
    date_created     timestamp with time zone DEFAULT now(),
    PRIMARY KEY (saved_by_user_id, route_id)
);

-- ============================================================
-- route_ratings
-- ============================================================
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

### Tables that no longer exist

`community_posts`, `community_post_helpful`, and the `community_tag` enum
were dropped in migration 004. `users.role` and the `user_role` enum (an
earlier, unused per-user role concept) were dropped in migration 003. If any
of these appear in older documentation or an agent's training/context,
they're stale — don't recreate them.

---

## 4. Things an agent should NOT assume

- Don't assume `/api/login` involves OTP/2FA — it doesn't yet.
- Don't build against a `community_posts` table or endpoint — it's gone;
  use Route Ratings instead.
- Don't assume `terminals.image_url` is a list/array — it's one URL.
- Don't assume `vehicle_type` is a Postgres enum (it isn't — it's a plain
  varchar validated in the API layer only).
- Don't assume admin approval is a one-time login check — `status` is
  re-verified on every single admin-authenticated request.
- `saved_routes`' user-id column is `saved_by_user_id`, not `user_id`.
  `community_posts` (when it existed) used `posted_by_user_id` for the same
  reason — this project deliberately avoids bare `user_id`/`admin_id`
  column names in favor of naming *what the person did* (`saved_by`,
  `created_by`, `rated_by`), for schema readability.