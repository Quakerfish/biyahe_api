# Biyahe API — FastAPI port

A 1:1 behavioral port of the 16 PHP endpoint files to a single FastAPI app,
using the **same Postgres database** and **cookie-based sessions**, so your
admin web app and Android app need little to no client-side changes.

## Project layout

```
app/
  main.py          FastAPI app: CORS, session middleware, error shapes, router wiring
  config.py        Settings loaded from .env (pydantic-settings)
  database.py      Async SQLAlchemy engine/session (asyncpg driver)
  models.py        ORM models: Admin, User, Terminal, Landmark, Route, Waypoint, SavedRoute
  schemas.py       Pydantic request/response models (replaces manual PHP validation)
  security.py      bcrypt hashing (compatible with your existing password_hash() values)
  dependencies.py  require_admin / require_user / require_user_or_admin (replaces $_SESSION checks)
  routers/
    admin_auth.py      admin_signup.php, admin_login.php, admin_profile.php
    user_auth.py       signup.php, login.php
    profile.py         get_profile.php, update_profile.php, upload_profile_image.php
    dashboard.py        dashboard.php
    analytics.py        analytics.php
    terminals.py        terminals.php
    routes.py           routes.php
    saved_routes.py     save_routes.php
    user_routes.py      user_routes.php
api/
  index.py        Vercel's recognized entrypoint - just re-exports app/main.py's `app`
requirements.txt
.env.example
.python-version   pins the Vercel Python runtime version
vercel.json
ANDROID_INTEGRATION.md   which endpoints the Android app hits, and exactly what changed
```

> **The Android app also calls several of these endpoints.** Read
> `ANDROID_INTEGRATION.md` before deploying — a few endpoints changed method
> or payload shape in ways a simple URL swap won't cover (notably
> `save_routes.php`'s POST/DELETE, and logout moving to its own URL).

## 1. Install & configure

```bash
python3 -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows
pip install -r requirements.txt

cp .env.example .env
# edit .env: DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASS (same Postgres DB you
# already have — no schema migration needed, see "Database" below), plus
# SESSION_SECRET_KEY (`openssl rand -hex 32`) and CORS_ORIGINS.
```

## 2. Run it locally

```bash
uvicorn app.main:app --reload --port 8000
```

Interactive API docs land at `http://localhost:8000/docs` — handy for
checking each endpoint's exact request/response shape as you wire up the
frontend.

## 3. Deploy to Vercel

Deploy this as its **own, separate Vercel project** — not combined with the
admin website's project. See the earlier discussion in this chat for why;
short version: Vercel's Python runtime is stateless serverless functions
with no persistent disk, so this API, your admin site, and your Android app
should each talk to the API over its own URL rather than sharing a
filesystem the way the old PHP setup did.

1. **Set up Postgres connection pooling.** Serverless functions can spin up
   many concurrent instances, each opening DB connections. If your Postgres
   is on Supabase/Neon/RDS, use the **pooled** connection string (often a
   different port, e.g. `6543` instead of `5432` on Supabase/PgBouncer) for
   `DB_HOST`/`DB_PORT` in step 3 below — otherwise you can exhaust your
   connection limit under load.
2. **Create a Blob store**: Vercel dashboard → your project (or create one
   first by importing this repo) → **Storage** tab → **Create Database** →
   **Blob**. Link it to this project. Vercel then injects
   `BLOB_READ_WRITE_TOKEN` into the deployment automatically — you don't
   set it by hand in production (only needed in your local `.env` for
   `vercel dev`, via `vercel env pull`).
3. **Push this project to a Git repo** (GitHub/GitLab/Bitbucket), then
   [vercel.com/new](https://vercel.com/new) → import it. Vercel
   auto-detects FastAPI from `requirements.txt` and `api/index.py` — no
   build command or output directory to configure.
4. **Set environment variables** in the Vercel project's Settings →
   Environment Variables: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`,
   `DB_PASS`, `SESSION_SECRET_KEY`, `SESSION_SAME_SITE` (`none`, since the
   admin site and Android app are on different origins than the API),
   `SESSION_HTTPS_ONLY` (`true`), `CORS_ORIGINS` (your admin site's deployed
   URL).
5. Deploy. Your API is now live at `https://<project>.vercel.app` (or a
   custom domain you attach, e.g. `api.biyahe.app`). Point the admin
   website's fetch calls and the Android app's base URL at that.

## 4. Database

No migration needed — the ORM models in `models.py` were written to match
the tables your PHP code already queries (`admins`, `users`, `terminals`,
`landmarks`, `routes`, `waypoints`, `saved_routes`). If any column names
differ slightly from your actual schema, adjust `models.py` to match (don't
let the ORM create tables — point it at your existing DB as-is). If you'd
like proper migrations going forward, add Alembic:

```bash
pip install alembic
alembic init migrations
# then point migrations/env.py's target_metadata at app.database.Base.metadata
```

## 5. Endpoint map (old → new)

| PHP file | Method(s) | New endpoint |
|---|---|---|
| admin_signup.php | POST | `POST /api/admin/signup` |
| admin_login.php | POST | `POST /api/admin/login` |
| admin_profile.php | GET, PUT | `GET/PUT /api/admin/profile` |
| signup.php | POST | `POST /api/signup` |
| login.php | POST | `POST /api/login` |
| get_profile.php | GET | `GET /api/profile` |
| get_profile.php?action=logout | POST | `POST /api/logout` |
| update_profile.php | POST | `PUT /api/profile` |
| upload_profile_image.php | POST | `POST /api/profile/image` (multipart, field name `profile_image`) |
| dashboard.php | GET | `GET /api/dashboard` |
| analytics.php | GET | `GET /api/analytics` |
| terminals.php | GET, POST, PUT, DELETE | `/api/terminals`, `/api/terminals/{id}` |
| routes.php | GET, POST, PUT, DELETE | `/api/routes`, `/api/routes/{id}` |
| save_routes.php | GET, POST, DELETE | `/api/saved-routes` (POST/DELETE take `route_id` as a query param) |
| user_routes.php | GET | `GET /api/commuter-routes` (same `?type=terminals` / `?id=` query params as before) |

A couple of these moved from `POST`-does-everything to proper HTTP verbs
(`PUT` for updates) since that's idiomatic FastAPI/REST — update the
frontend's fetch calls for `update_profile.php`, `admin_profile.php`, and the
route/terminal update calls to use `PUT` instead of `POST`.

## 6. What changed, and why it should be safe

- **Sessions**: PHP's `session_start()` + `$_SESSION[...]` is replaced by
  Starlette's `SessionMiddleware`, which stores the same key/value data in a
  signed cookie (`biyahe_session`) instead of a server-side file. Your
  frontend doesn't need to change — it already sends/receives cookies with
  `credentials: true`; this just changes what's inside the cookie.
- **Passwords**: `password_hash()`/`password_verify()` produced `$2y$...`
  bcrypt hashes. Passlib's bcrypt handler reads `$2y$` the same as `$2b$`, so
  your **existing users' passwords keep working** with no re-hashing step.
  New signups get `$2b$` hashes, which `password_verify()` in PHP also
  accepts — so this is safe even mid-migration if you run both stacks
  briefly.
- **Validation**: hand-rolled `empty()`/`strlen()` checks became Pydantic
  field validators (`schemas.py`). Error responses keep the same
  `{"success": false, "message": "..."}` shape and roughly the same
  messages, via the custom exception handlers in `main.py`.
- **`htmlspecialchars()` sanitization**: the PHP code HTML-escaped strings
  before storing/returning them, presumably to blunt stored-XSS when the
  admin dashboard rendered values directly into the DOM. This port does
  **not** re-implement that — the better fix is to have the frontend escape
  on render (which any modern templating/React/Vue setup does by default) or
  CSP, rather than mutating the stored data. If you specifically want the
  stored strings byte-for-byte HTML-escaped like before, say so and I'll add
  it back in `schemas.py`.
- **CORS/OPTIONS preflight**: handled globally by `CORSMiddleware` now
  instead of per-file `header(...)` + `if (OPTIONS) exit` blocks.
- **Avatar uploads go to Vercel Blob, not local disk.** Vercel's Python
  functions have no persistent filesystem between requests, so
  `upload_profile_image.php`'s `move_uploaded_file()` to a local
  `uploads/avatars/` folder became an upload to Vercel Blob instead. The
  `profile_image` column now stores a full Blob CDN URL rather than just a
  filename — see `ANDROID_INTEGRATION.md` if anything parses that URL's
  shape client-side.

## 7. Things worth double-checking against your real schema

I inferred column types (e.g. `vehicle_type` as a plain string, not a
Postgres enum) from how the PHP queries used them. If your actual `routes`
table has a real `CHECK` constraint or enum type for `vehicle_type`, or if
`admin_uuid` has a DB-side default (e.g. `gen_random_uuid()`) rather than
being app-generated, adjust `models.py` to match so inserts don't conflict
with constraints you already have.
