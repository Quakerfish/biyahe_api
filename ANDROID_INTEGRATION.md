# Android app compatibility notes

The **Biyahe Android app** (commuter-facing, Kotlin + MapLibre) talks to this
API alongside the admin web app. Based on which PHP files require a
*commuter* session (`$_SESSION['user_id']`) rather than an *admin* session
(`$_SESSION['admin_id']`), the endpoints below are the ones most likely in
use by the Android app. **Please confirm/correct this list against the
app's actual networking code** — treat it as my best inference from the PHP
files, not a guarantee.

| Likely used by Android | Old PHP | New FastAPI | Status |
|---|---|---|---|
| ✅ | `POST login.php` | `POST /api/login` | URL changed |
| ✅ | `POST signup.php` | `POST /api/signup` | URL changed |
| ✅ | `GET get_profile.php` | `GET /api/profile` | URL changed |
| ✅ | `POST get_profile.php?action=logout` | `POST /api/logout` | **URL changed — was a query param on get_profile.php, now its own route** |
| ✅ | `POST update_profile.php` | `PUT /api/profile` (POST still works too, see below) | URL + verb changed, **but POST alias kept** |
| ✅ | `POST upload_profile_image.php` (multipart, field `profile_image`) | `POST /api/profile/image` (same field name) | URL changed; response `profile_image` is now a Vercel Blob CDN URL instead of `.../Biyahe-Admin/uploads/avatars/...` |
| ✅ | `GET/POST/DELETE save_routes.php` | `GET/POST/DELETE /api/saved-routes` | URL changed; POST/DELETE now take `route_id` as a **query param**, not JSON body (see below) |
| ✅ | `GET user_routes.php` (`?type=terminals`, `?id=`, or no params) | `GET /api/commuter-routes` (same query params) | Only the URL path changed — query-param behavior is identical |
| ❓ unclear | `routes.php` | `GET/POST/PUT/DELETE /api/routes` | **Admin-only** (`require_admin`) in this port. If the Android app genuinely calls this today, it must be sending an *admin* session cookie — worth double-checking, since that seems unlikely for a commuter app. Flag this to me if so and I'll adjust who's allowed to call it. |

Every URL changed (new base path, `/api/...` instead of bare `.php` files),
so **the Android app's base URL / endpoint constants need updating no matter
what** — that part isn't optional. The items below are the handful of
spots where the *method or payload shape* also changed, which is where a
simple "find and replace the URL" in the Android code won't be enough:

1. **Logout moved to its own URL.** Old: `POST get_profile.php?action=logout`.
   New: `POST /api/logout`. Update the Android logout call's path, not just
   its host.

2. **`update_profile.php` → `/api/profile`.** I registered this route to
   accept **both `PUT` and `POST`**, specifically so the existing Android
   call (which presumably sends `POST`) keeps working as-is after you just
   swap the URL — no verb change required on the Android side unless you
   want to modernize it to `PUT` later.

3. **`save_routes.php`'s POST/DELETE took `route_id` in the JSON body; the
   new `/api/saved-routes` takes it as a query param** (`?route_id=123`)
   for both POST and DELETE, to match FastAPI's idiomatic style for
   body-less mutations. This one **does** need an Android-side change
   beyond the URL — moving `route_id` from the request body to the query
   string.

4. **Avatar URLs changed shape.** `profile_image` used to look like
   `http://host/Biyahe-Admin/uploads/avatars/avatar_12_169...jpg`. It's now
   a Vercel Blob CDN URL (`https://*.public.blob.vercel-storage.com/...`).
   If the Android app does any string-matching/parsing on that URL (rather
   than just loading it as an image), that logic needs updating.

## What to do with this

Before you deploy: either send me the Android app's networking/API-client
code (Retrofit interfaces, OkHttp calls, whatever it uses) so I can confirm
this table is accurate and update the Android side to match, or go through
it yourself against the table above. Either way, I'd treat this as a
blocking step before cutting the Android app over to the new API — point 3
especially (`save_routes.php`) will fail silently (400 "route_id must be a
valid integer") if the request body still sends it the old way.
