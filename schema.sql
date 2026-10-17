-- =========================================================================
-- Biyahe Database Schema (PostgreSQL / Supabase)
-- =========================================================================

-- 1. Create Custom ENUM Types
CREATE TYPE public.admin_approval_status AS ENUM ('Waiting Approval', 'Approved', 'Blocked');
CREATE TYPE public.admin_role AS ENUM ('admin', 'superadmin');
CREATE TYPE public.active_status AS ENUM ('Active', 'Inactive');
CREATE TYPE public.vehicle_type_enum AS ENUM ('Traditional', 'Modern');

-- 2. Users Table
CREATE TABLE public.users (
  user_id serial not null,
  user_uuid uuid null default gen_random_uuid (),
  username character varying(150) null,
  email character varying(150) null,
  date_created timestamp with time zone null default now(),
  password character varying(100) null,
  profile_image character varying(255) null default null::character varying,
  suspended_until timestamp with time zone null,
  suspension_reason text null,
  constraint users_pkey primary key (user_id)
) TABLESPACE pg_default;

-- 3. Admins Table
CREATE TABLE public.admins (
  admin_id serial not null,
  admin_uuid uuid null default gen_random_uuid (),
  admin_username character varying(150) not null,
  admin_password character varying(255) not null,
  admin_email character varying(100) not null,
  date_created timestamp with time zone null default now(),
  status public.admin_approval_status not null default 'Waiting Approval'::admin_approval_status,
  role public.admin_role not null default 'admin'::admin_role,
  pending_password character varying(255) null,
  password_reset_requested_at timestamp with time zone null,
  constraint admins_pkey primary key (admin_id),
  constraint admins_admin_email_key unique (admin_email),
  constraint admins_admin_username_key unique (admin_username)
) TABLESPACE pg_default;

-- 4. Login OTPs Table
CREATE TABLE public.login_otps (
  user_id integer not null,
  otp_code character varying(64) not null,
  expires_at timestamp with time zone not null,
  attempt_count integer not null default 0,
  date_created timestamp with time zone null default now(),
  constraint login_otps_pkey primary key (user_id),
  constraint login_otps_user_id_fkey foreign KEY (user_id) references users (user_id) on delete CASCADE
) TABLESPACE pg_default;

-- 5. Terminals Table
CREATE TABLE public.terminals (
  terminal_id serial not null,
  terminal_name character varying(255) not null,
  latitude numeric(10, 8) null,
  longitude numeric(11, 8) null,
  status public.active_status not null default 'Active'::active_status,
  description text null,
  image_url text null,
  constraint terminals_pkey primary key (terminal_id)
) TABLESPACE pg_default;

-- 6. Routes Table
CREATE TABLE public.routes (
  route_id serial not null,
  created_by_admin_id integer not null,
  origin_terminal_id integer not null,
  destination_terminal_id integer not null,
  route_code character varying(50) not null,
  vehicle_type public.vehicle_type_enum not null,
  status public.active_status not null default 'Active'::active_status,
  base_fare numeric(6, 2) null,
  description text null,
  constraint routes_pkey primary key (route_id),
  constraint fk_route_created_by foreign KEY (created_by_admin_id) references admins (admin_id) on delete RESTRICT,
  constraint fk_route_destination foreign KEY (destination_terminal_id) references terminals (terminal_id) on delete RESTRICT,
  constraint fk_route_origin foreign KEY (origin_terminal_id) references terminals (terminal_id) on delete RESTRICT
) TABLESPACE pg_default;

-- 7. Waypoints Table (with Street Name)
CREATE TABLE public.waypoints (
  waypoint_id serial not null,
  route_id integer not null,
  sequence_no integer not null,
  latitude numeric(10, 8) null,
  longitude numeric(11, 8) null,
  street_name character varying(255) null,
  constraint waypoints_pkey primary key (waypoint_id),
  constraint fk_waypoint_route foreign KEY (route_id) references routes (route_id) on delete CASCADE
) TABLESPACE pg_default;

-- 8. Saved Routes Table
CREATE TABLE public.saved_routes (
  saved_by_user_id integer not null,
  route_id integer not null,
  date_created timestamp without time zone not null default CURRENT_TIMESTAMP,
  constraint saved_routes_pkey primary key (saved_by_user_id, route_id),
  constraint fk_saved_route_route foreign KEY (route_id) references routes (route_id) on delete CASCADE,
  constraint fk_saved_route_user foreign KEY (saved_by_user_id) references users (user_id) on delete CASCADE
) TABLESPACE pg_default;

-- 9. Route Ratings Table
CREATE TABLE public.route_ratings (
  route_id integer not null,
  rated_by_user_id integer not null,
  route_accuracy_rating smallint not null,
  fare_accuracy_rating smallint not null,
  comment text null,
  date_created timestamp with time zone null default now(),
  date_updated timestamp with time zone null default now(),
  constraint route_ratings_pkey primary key (route_id, rated_by_user_id),
  constraint route_ratings_rated_by_user_id_fkey foreign KEY (rated_by_user_id) references users (user_id) on delete CASCADE,
  constraint route_ratings_route_id_fkey foreign KEY (route_id) references routes (route_id) on delete CASCADE,
  constraint route_ratings_fare_accuracy_rating_check check (
    (
      (fare_accuracy_rating >= 1)
      and (fare_accuracy_rating <= 5)
    )
  ),
  constraint route_ratings_route_accuracy_rating_check check (
    (
      (route_accuracy_rating >= 1)
      and (route_accuracy_rating <= 5)
    )
  )
) TABLESPACE pg_default;
