-- ============================================================================
-- Biyahe database schema (Supabase / PostgreSQL)
-- Fresh-install script: creates every table the API uses.
-- Run it in the Supabase SQL editor on an empty database.
-- (The numbered migration files record how the schema changed over time;
--  this file is the final result of all of them.)
-- ============================================================================

-- ---------------------------------------------------------------- enum types
CREATE TYPE public.active_status         AS ENUM ('Active', 'Inactive');
CREATE TYPE public.admin_approval_status AS ENUM ('Waiting Approval', 'Approved', 'Blocked');
CREATE TYPE public.admin_role            AS ENUM ('admin', 'superadmin');

-- -------------------------------------------------------------------- admins
CREATE TABLE public.admins (
    admin_id                    integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admin_uuid                  uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    admin_username              varchar(50)  NOT NULL UNIQUE,
    admin_password              varchar(255) NOT NULL,           -- bcrypt hash, never plain text
    admin_email                 varchar(255) NOT NULL UNIQUE,
    status                      public.admin_approval_status NOT NULL DEFAULT 'Waiting Approval',
    role                        public.admin_role            NOT NULL DEFAULT 'admin',
    pending_password            varchar(255),                    -- bcrypt hash waiting for superadmin approval
    password_reset_requested_at timestamptz
);

-- --------------------------------------------------------------------- users
CREATE TABLE public.users (
    user_id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username          varchar(50)  NOT NULL UNIQUE,
    email             varchar(255) NOT NULL UNIQUE,
    password          varchar(255) NOT NULL,                     -- bcrypt hash, never plain text
    profile_image     varchar(255),                              -- Vercel Blob URL
    date_created      timestamptz DEFAULT now(),
    suspended_until   timestamptz,                               -- NULL = not suspended
    suspension_reason text
);

-- -------------------------------------------- one-time passwords (one row per user)
CREATE TABLE public.login_otps (
    user_id       integer PRIMARY KEY REFERENCES public.users(user_id) ON DELETE CASCADE,
    otp_code      varchar(64) NOT NULL,                          -- keyed hash of the 6-digit code
    expires_at    timestamptz NOT NULL,
    attempt_count integer     NOT NULL DEFAULT 0,
    date_created  timestamptz DEFAULT now()
);

CREATE TABLE public.password_reset_otps (
    user_id       integer PRIMARY KEY REFERENCES public.users(user_id) ON DELETE CASCADE,
    otp_code      varchar(64) NOT NULL,
    expires_at    timestamptz NOT NULL,
    attempt_count integer     NOT NULL DEFAULT 0,
    date_created  timestamptz DEFAULT now()
);

-- ----------------------------------------------------------------- terminals
CREATE TABLE public.terminals (
    terminal_id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    terminal_name varchar(150) NOT NULL,
    latitude      double precision,
    longitude     double precision,
    status        public.active_status NOT NULL DEFAULT 'Active',
    description   text,
    image_url     text                                           -- one photo (Vercel Blob URL)
);

-- -------------------------------------------------------------------- routes
CREATE TABLE public.routes (
    route_id                integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_by_admin_id     integer NOT NULL REFERENCES public.admins(admin_id),
    origin_terminal_id      integer NOT NULL REFERENCES public.terminals(terminal_id),
    destination_terminal_id integer NOT NULL REFERENCES public.terminals(terminal_id),
    route_code              varchar(50) NOT NULL,
    vehicle_type            varchar(20) NOT NULL,                -- 'Traditional' or 'Modern' (checked by the API)
    status                  public.active_status NOT NULL DEFAULT 'Active',
    base_fare               numeric(6,2),
    description             text
);

-- ----------------------------------------------------------------- waypoints
CREATE TABLE public.waypoints (
    waypoint_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    route_id    integer NOT NULL REFERENCES public.routes(route_id) ON DELETE CASCADE,
    sequence_no integer NOT NULL,
    latitude    double precision NOT NULL,
    longitude   double precision NOT NULL
);

-- -------------------------------------------------------------- saved_routes
CREATE TABLE public.saved_routes (
    saved_by_user_id integer NOT NULL REFERENCES public.users(user_id)   ON DELETE CASCADE,
    route_id         integer NOT NULL REFERENCES public.routes(route_id) ON DELETE CASCADE,
    date_created     timestamptz DEFAULT now(),
    PRIMARY KEY (saved_by_user_id, route_id)
);

-- ------------------------------------------------------------- route_ratings
CREATE TABLE public.route_ratings (
    route_id              integer  NOT NULL REFERENCES public.routes(route_id) ON DELETE CASCADE,
    rated_by_user_id      integer  NOT NULL REFERENCES public.users(user_id)   ON DELETE CASCADE,
    route_accuracy_rating smallint NOT NULL CHECK (route_accuracy_rating BETWEEN 1 AND 5),
    fare_accuracy_rating  smallint NOT NULL CHECK (fare_accuracy_rating  BETWEEN 1 AND 5),
    comment               text,
    date_created          timestamptz DEFAULT now(),
    date_updated          timestamptz DEFAULT now(),
    PRIMARY KEY (route_id, rated_by_user_id)
);