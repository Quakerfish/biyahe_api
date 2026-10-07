Biyahe API — FastAPI BackendA high-performance FastAPI backend providing API endpoints for both the Biyahe Admin Web Application and the Biyahe Android App. Connected to a Postgres (Supabase) database, it uses signed cookie-based sessions for authentication and handles direct file uploads via Vercel Blob Storage.Base URL (Production): [https://biyahe-api.vercel.app](https://biyahe-api.vercel.app)📌 Critical Updates & Architectural DecisionsBefore working on or deploying this codebase, note the following architectural details:Auth Model (Sessions, Not Tokens):Uses Starlette signed session cookies (biyahe_session). Sent via Cookie headers (credentials: 'include' in fetch).No Bearer Tokens / Authorization Headers are used anywhere in this API.No OTP / 2FA: POST /api/login authenticates and logs users in directly. The login_otps table exists in the DB, but no endpoints currently enforce OTPs.Admin authorization status (status) is re-checked on every request. Blocking an admin takes effect immediately.Feature Removal:The Community feature (community_posts, tags, helpful votes) was completely removed and replaced by Route Ratings (route_ratings table, /api/routes/{id}/ratings).Storage & Media:Avatars and terminal photos are uploaded directly to Vercel Blob Storage, which returns absolute CDN URLs stored in the DB.Terminals support one photo (image_url column), not an array/gallery.Data Validation & Enums:routes.vehicle_type is a plain varchar(20) validated at the application layer (Literal["Traditional", "Modern"]), not a Postgres DB enum.routes.status, terminals.status, admins.status, and admins.role are real Postgres enums.Unified Exception Handling:Every API response is JSON. Success responses always contain "success": true.Errors always return {"success": false, "message": "<reason>"} with an appropriate non-2xx status code.Project LayoutPlaintextapp/
├── main.py              # FastAPI app: CORS, session middleware, error shapes, router wiring
├── config.py            # Settings loaded from .env (pydantic-settings)
├── database.py          # Async SQLAlchemy engine/session (asyncpg driver)
├── models.py            # ORM models: Admin, User, Terminal, Landmark, Route, Waypoint, SavedRoute, RouteRating
├── schemas.py           # Pydantic request/response models
├── security.py          # bcrypt password hashing (compatible with PHP's password_hash())
├── dependencies.py      # require_admin / require_user / require_user_or_admin middleware logic
└── routers/
    ├── admin_auth.py    # Admin auth & admin management endpoints (/api/admin)
    ├── user_auth.py     # Commuter signup & login (/api)
    ├── profile.py       # Commuter profile management, avatar uploads, and logout
    ├── dashboard.py     # Admin dashboard aggregates & GeoJSON map layers
    ├── analytics.py     # Admin analytics & trend metrics
    ├── terminals.py     # Terminal CRUD & image upload
    ├── routes.py        # Route CRUD & waypoints
    ├── route_ratings.py # Commuter route rating endpoints
    ├── saved_routes.py  # Saved commuter routes
    └── user_routes.py   # Public route/terminal query endpoints for commuters
api/
└── index.py             # Vercel entrypoint re-exporting app/main.py's `app`
requirements.txt
.env.example
.python-version          # Python runtime version pin for Vercel
vercel.json
ANDROID_INTEGRATION.md   # Android app endpoints & payload specifications
1. Local Setup & ConfigurationPrerequisitesPython 3.10+Access to a PostgreSQL database (e.g., Supabase, Neon, or local instance)Bash# 1. Environment creation & dependency installation
python3 -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure environment variables
cp .env.example .env
Environment Variables (.env)VariableDescriptionDB_HOSTPostgres host addressDB_PORTPostgres port (5432 or pooled 6543)DB_NAMEDatabase nameDB_USERDatabase usernameDB_PASSDatabase passwordSESSION_SECRET_KEYHex secret generated via openssl rand -hex 32SESSION_SAME_SITECookie SameSite attribute (none for cross-site)SESSION_HTTPS_ONLYSet to true in productionCORS_ORIGINSComma-separated list of allowed frontend originsBLOB_READ_WRITE_TOKENToken for Vercel Blob Storage (pulled automatically in Vercel)2. Running LocallyBashuvicorn app.main:app --reload --port 8000
Interactive Swagger Docs: http://localhost:8000/docsReDoc Documentation: http://localhost:8000/redoc3. Vercel DeploymentDeploy this API as its own, standalone Vercel project separate from any web frontend.Database Connection Pooling: Since serverless functions scale dynamically, configure your DB_HOST and DB_PORT to point to a pooled Postgres connection (e.g., Supabase PgBouncer port 6543) to prevent connection pool exhaustion.Vercel Blob Store:Go to your Vercel Project → Storage tab → Create Database → Blob.Link it to this project. Vercel automatically injects BLOB_READ_WRITE_TOKEN.Environment Variables: Configure DB_*, SESSION_SECRET_KEY, SESSION_SAME_SITE=none, SESSION_HTTPS_ONLY=true, and CORS_ORIGINS under Project Settings → Environment Variables.Deploy: Import the GitHub repository into Vercel. Vercel automatically detects requirements.txt and api/index.py.4. API Endpoint ReferenceAdmin Auth & Profile — /api/adminMethodPathAuthRequest BodyDescriptionPOST/api/admin/signupNone{username, email, password, confirm_password}New admins are created with status="Waiting Approval" and role="admin".POST/api/admin/loginNone{username, password}Fails if account status is Waiting Approval or Blocked. Sets session cookie on success.GET/api/admin/profileAdminNoneRetrieves current logged-in admin details.PUT/api/admin/profileAdmin{username, email}Updates admin username and/or email.Admin Management — /api/admin/admins (Superadmin Only)MethodPathAuthRequest BodyDescriptionGET/api/admin/adminsSuperadminNoneReturns a list of all admin accounts.GET/api/admin/admins/pendingSuperadminNoneReturns admin accounts where status="Waiting Approval".PUT/api/admin/admins/{admin_id}/statusSuperadmin{status}Values: "Waiting Approval", "Approved", "Blocked". Self-modification blocked.PUT/api/admin/admins/{admin_id}/roleSuperadmin{role}Values: "admin", "superadmin". Self-modification blocked.User Auth — /apiMethodPathAuthRequest BodyDescriptionPOST/api/signupNone{username, email, password, confirmPassword}Registers a new commuter account.POST/api/loginNone{username, password}Accepts either username or email in username field. Direct login without OTP.POST/api/logoutUserNoneInvalidates user session and clears cookie.Profile & Settings — /apiMethodPathAuthRequest BodyDescriptionGET/api/profileUserNoneReturns user profile details (profile_image contains absolute CDN URL).PUT/api/profileUser{username, email, current_password?, new_password?}Updates profile info. Pass password fields only if changing password. (Accepts POST for legacy client support).POST/api/profile/imageUsermultipart/form-data (profile_image)Uploads image to Vercel Blob and stores CDN URL in database.Dashboard & Analytics — /api (Admin Only)MethodPathAuthRequest BodyDescriptionGET/api/dashboardAdminNoneSummary counts, top hubs, and GeoJSON FeatureCollection overlays for terminals/landmarks.GET/api/analyticsAdminNoneAggregate usage metrics, vehicle breakdowns, and 7-day user/route trend lines.Terminals — /api/terminals (Admin Only)MethodPathAuthRequest BodyDescriptionGET/api/terminalsAdminNoneList of all terminals.GET/api/terminals/{id}AdminNoneTerminal details including associated routes where origin/destination match.POST/api/terminalsAdmin{terminal_name, latitude, longitude, status?, description?}Creates a new terminal (status defaults to "Active").PUT/api/terminals/{id}AdminSame as POSTReplaces terminal details.POST/api/terminals/{id}/imageAdminmultipart/form-data (image)Uploads terminal header photo to Vercel Blob Store.DELETE/api/terminals/{id}AdminNoneDeletes terminal. Returns 409 Conflict if referenced by an existing route.Routes — /api/routes (Admin Only)MethodPathAuthRequest BodyDescriptionGET/api/routesAdminNoneList of all routes.GET/api/routes/{id}AdminNoneFull route details including list of waypoints.POST/api/routesAdmin{route_code, vehicle_type, origin_terminal_id, destination_terminal_id, status?, base_fare?, description?, waypoints: [...]}Creates a route and inserts associated waypoints. created_by_admin_id inferred from session.PUT/api/routes/{id}AdminSame as POSTUpdates route details and replaces waypoints wholesale.DELETE/api/routes/{id}AdminNoneDeletes route (cascades to waypoints and ratings).Route Ratings — /api/routes/{route_id}/ratings (User Only)MethodPathAuthRequest BodyDescriptionGET/api/routes/{route_id}/ratingsUserNoneReturns aggregated accuracy averages and user's own rating for this route.POST/api/routes/{route_id}/ratingsUser{route_accuracy_rating: 1-5, fare_accuracy_rating: 1-5, comment?}Upserts rating (one rating per user per route). Re-rating updates existing entry.Saved Routes — /api/saved-routes (User Only)MethodPathAuthQuery ParametersDescriptionGET/api/saved-routesUserNoneReturns list of user's saved routes with full route metadata.POST/api/saved-routesUser?route_id=123Saves route to user profile (idempotent).DELETE/api/saved-routesUser?route_id=123Removes saved route from user profile (idempotent).Commuter Routes & Exploration — /api/commuter-routesQuery ParametersAuthDescription?type=terminalsUser or AdminReturns list of active terminals with coordinates and images.?id=123User or AdminReturns detailed information for a single active route including waypoints.(None)User or AdminReturns summary list of all active routes.5. Database Schema StructureSQL-- Custom Enum Types
CREATE TYPE public.active_status AS ENUM ('Active', 'Inactive');
CREATE TYPE public.admin_approval_status AS ENUM ('Waiting Approval', 'Approved', 'Blocked');
CREATE TYPE public.admin_role AS ENUM ('admin', 'superadmin');

-- Admins Table
CREATE TABLE public.admins (
    admin_id       integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admin_uuid     uuid UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    admin_username character varying(50) UNIQUE NOT NULL,
    admin_password character varying(255) NOT NULL,
    admin_email    character varying(255) UNIQUE NOT NULL,
    status         public.admin_approval_status NOT NULL DEFAULT 'Waiting Approval',
    role           public.admin_role NOT NULL DEFAULT 'admin'
);

-- Users Table
CREATE TABLE public.users (
    user_id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username           character varying(50) UNIQUE NOT NULL,
    email              character varying(255) UNIQUE NOT NULL,
    password           character varying(255) NOT NULL,
    profile_image      character varying(255),
    date_created       timestamp with time zone DEFAULT now(),
    suspended_until    timestamp with time zone,
    suspension_reason  text
);

-- Login OTPs Table (Reserved for future multi-factor support)
CREATE TABLE public.login_otps (
    user_id       integer PRIMARY KEY REFERENCES public.users(user_id) ON DELETE CASCADE,
    otp_code      character varying(6) NOT NULL,
    expires_at    timestamp with time zone NOT NULL,
    attempt_count integer NOT NULL DEFAULT 0,
    date_created  timestamp with time zone DEFAULT now()
);

-- Terminals Table
CREATE TABLE public.terminals (
    terminal_id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    terminal_name character varying(150) NOT NULL,
    latitude      double precision,
    longitude     double precision,
    status        public.active_status NOT NULL DEFAULT 'Active',
    description   text,
    image_url     text
);

-- Landmarks Table
CREATE TABLE public.landmarks (
    landmark_id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    landmark_name character varying(150) NOT NULL,
    latitude      double precision,
    longitude     double precision
);

-- Routes Table
CREATE TABLE public.routes (
    route_id                integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_by_admin_id     integer NOT NULL REFERENCES public.admins(admin_id),
    origin_terminal_id      integer NOT NULL REFERENCES public.terminals(terminal_id),
    destination_terminal_id integer NOT NULL REFERENCES public.terminals(terminal_id),
    route_code              character varying(50) NOT NULL,
    vehicle_type            character varying(20) NOT NULL, -- 'Traditional' | 'Modern'
    status                  public.active_status NOT NULL DEFAULT 'Active',
    base_fare               numeric(6,2),
    description             text
);

-- Waypoints Table
CREATE TABLE public.waypoints (
    waypoint_id  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    route_id     integer NOT NULL REFERENCES public.routes(route_id) ON DELETE CASCADE,
    sequence_no  integer NOT NULL,
    latitude     double precision NOT NULL,
    longitude    double precision NOT NULL
);

-- Saved Routes Table
CREATE TABLE public.saved_routes (
    saved_by_user_id integer NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    route_id         integer NOT NULL REFERENCES public.routes(route_id) ON DELETE CASCADE,
    date_created     timestamp with time zone DEFAULT now(),
    PRIMARY KEY (saved_by_user_id, route_id)
);

-- Route Ratings Table
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
6. Security & Migration CompatibilityPassword Hash Compatibility: Password hashes generated by PHP's password_hash() (prefixed $2y$) are seamlessly parsed by Passlib's bcrypt handler alongside standard $2b$ hashes. Users do not need to reset passwords upon stack migration.Foreign Key Naming Policy: Relational foreign keys explicitly name the actor or action where applicable (saved_by_user_id, created_by_admin_id, rated_by_user_id) rather than using ambiguous user_id columns.Deprecated Tables: community_posts, community_post_helpful, community_tag, and user_role have been completely removed from the schema.
